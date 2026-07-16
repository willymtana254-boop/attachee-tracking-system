"""
Kilifi County ICT Attachee Tracking System — Backend API
Run: python server.py
"""

import sqlite3, hashlib, os, secrets, time, json as _json
from datetime import timedelta
from urllib.request import urlopen, Request as _UrlRequest
from urllib.parse import urlencode as _urlencode
from urllib.error import URLError, HTTPError
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)

# ── FIX: anchor paths to this script's own folder, not the process cwd ────────
# Previously static_folder='.' was a RELATIVE path resolved against whatever
# directory the process happened to be launched from. On your own machine that
# usually matched, but on Render (and some other hosts) gunicorn/uvicorn can be
# started from a different working directory, so '.' pointed somewhere that
# did NOT contain klf-logo.webp — hence the logo working under VSCode's Live
# Server (a plain static file server rooted at the folder) but not here.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=BASE_DIR, static_url_path='')
# ────────────────────────────────────────────────────────────────────────────

_SECRET_FILE = os.path.join(BASE_DIR, '.jwt_secret')
if os.environ.get('JWT_SECRET'):
    _jwt_secret = os.environ['JWT_SECRET']
elif os.path.exists(_SECRET_FILE):
    with open(_SECRET_FILE) as _f: _jwt_secret = _f.read().strip()
else:
    _jwt_secret = secrets.token_hex(32)
    with open(_SECRET_FILE, 'w') as _f: _f.write(_jwt_secret)

app.config['JWT_SECRET_KEY'] = _jwt_secret
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=12)
CORS(app)
jwt = JWTManager(app)

DB_PATH = os.environ.get('DB_PATH', os.path.join(BASE_DIR, 'kilifi.db'))

_login_attempts: dict = {}
def _check_rate_limit(ip):
    now = time.time()
    attempts = [t for t in _login_attempts.get(ip, []) if now - t < 60]
    if len(attempts) >= 10: return False
    attempts.append(now); _login_attempts[ip] = attempts; return True

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def hash_pass(p):
    return hashlib.sha256(f'kilifi2026{p}'.encode()).hexdigest()

def hash_pass_legacy(p):
    return hashlib.sha256(p.encode()).hexdigest()

def row_to_dict(row):
    return dict(row) if row else None

def rows_to_list(rows):
    return [dict(r) for r in rows]

def get_current_user(conn, uid):
    return row_to_dict(conn.execute(
        "SELECT id, role, supervisor_id, parent_user_id FROM users WHERE id=?", (uid,)).fetchone())

def requires_approval(user, action_type, target_table):
    if not user: return False
    # Stand-in users always require approval for write actions
    if user['role'] in ('stand_in_admin', 'stand_in_supervisor'):
        return True
    # If a non-main admin adds a user
    if target_table == 'users' and action_type == 'CREATE' and user['id'] != 1:
        return True
    return False

def create_pending_approval(conn, action_type, target_table, target_id, payload, creator_id):
    from datetime import datetime
    conn.execute(
        "INSERT INTO pending_approvals (action_type, target_table, target_id, payload, created_by, created_at, status) VALUES (?, ?, ?, ?, ?, ?, 'pending')",
        (action_type, target_table, target_id, _json.dumps(payload), creator_id, datetime.now().isoformat())
    )
    conn.commit()

def execute_pending_action(conn, action):
    action_type = action['action_type']
    target_table = action['target_table']
    target_id = action['target_id']
    payload = _json.loads(action['payload'])
    
    VALID_TABLES = {'users', 'attachees', 'evaluations', 'documents', 'departments', 'supervisors', 'institutions'}
    if target_table not in VALID_TABLES:
        raise ValueError("Invalid target table")
        
    if action_type == 'CREATE':
        keys = list(payload.keys())
        columns = ", ".join(keys)
        placeholders = ", ".join(["?"] * len(keys))
        values = [payload[k] for k in keys]
        query = f"INSERT INTO {target_table} ({columns}) VALUES ({placeholders})"
        conn.execute(query, values)
    elif action_type == 'UPDATE':
        keys = list(payload.keys())
        set_clause = ", ".join([f"{k}=?" for k in keys])
        values = [payload[k] for k in keys] + [target_id]
        query = f"UPDATE {target_table} SET {set_clause} WHERE id=?"
        conn.execute(query, values)
    elif action_type == 'DELETE':
        query = f"DELETE FROM {target_table} WHERE id=?"
        conn.execute(query, (target_id,))

# ─── KENYA INSTITUTIONS API (external data source) ───────────────────────────
# This wires up "Kenya Data API" (kenyaareadata.vercel.app), which exposes
# Kenyan universities/colleges/TVETs alongside its counties/constituencies/wards
# endpoint. The public key can be overridden via an env var without touching
# code. NOTE: the exact JSON field names this endpoint returns weren't
# independently confirmed, so _normalize_institution() below defensively
# checks several likely variants (name/institutionName/institution,
# type/category, county/location, contact/phone). If your real responses use
# different field names, this is the one place to adjust.
KENYA_INSTITUTIONS_API_URL = os.environ.get(
    'KENYA_INSTITUTIONS_API_URL', 'https://kenyaareadata.vercel.app/api/institutions')
KENYA_INSTITUTIONS_API_KEY = os.environ.get(
    'KENYA_INSTITUTIONS_API_KEY', 'keypubinsti1569ftyf555cfcfj88')

_kenya_inst_cache = {'data': None, 'ts': 0}
_KENYA_INST_CACHE_TTL = 3600  # seconds — institution lists barely change; avoid hammering the external API on every keystroke

def _normalize_institution(item):
    if isinstance(item, str):
        return {'name': item.strip(), 'type': '', 'county': '', 'contact': '', 'email': ''}
    if not isinstance(item, dict):
        return None
    name = (item.get('name') or item.get('institutionName') or
            item.get('institution') or item.get('title') or '').strip()
    if not name:
        return None
    return {
        'name':    name,
        'type':    item.get('type') or item.get('category') or item.get('institutionType') or '',
        'county':  item.get('county') or item.get('location') or item.get('region') or '',
        'contact': item.get('contact') or item.get('phone') or item.get('telephone') or '',
        'email':   item.get('email') or '',
    }

def _fetch_kenya_institutions_raw():
    url = KENYA_INSTITUTIONS_API_URL + '?' + _urlencode({'apiKey': KENYA_INSTITUTIONS_API_KEY})
    req = _UrlRequest(url, headers={'User-Agent': 'KilifiICTAttacheeSystem/1.0', 'Accept': 'application/json'})
    with urlopen(req, timeout=8) as resp:
        return _json.loads(resp.read().decode('utf-8'))

def get_kenya_institutions():
    """Returns a flat, normalized, cached list of institutions from the Kenya Data API."""
    now = time.time()
    if _kenya_inst_cache['data'] is not None and (now - _kenya_inst_cache['ts']) < _KENYA_INST_CACHE_TTL:
        return _kenya_inst_cache['data']

    raw = _fetch_kenya_institutions_raw()

    # The API's institutions payload shape wasn't independently confirmed, so
    # handle the common possibilities: a bare list, {"institutions": [...]},
    # {"data": [...]}, or a dict keyed by category/county with list values.
    items = []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = raw.get('institutions') or raw.get('data') or raw.get('results') or []
        if not items:
            for v in raw.values():
                if isinstance(v, list):
                    items.extend(v)

    normalized = []
    seen = set()
    for it in items:
        n = _normalize_institution(it)
        if n and n['name'].lower() not in seen:
            seen.add(n['name'].lower())
            normalized.append(n)

    _kenya_inst_cache['data'] = normalized
    _kenya_inst_cache['ts'] = now
    return normalized

def attachee_visible_to(conn, uid, aid):
    user = get_current_user(conn, uid)
    if not user: return None
    row = row_to_dict(conn.execute("SELECT * FROM attachees WHERE id=?", (aid,)).fetchone())
    if not row: return None
    if user['role'] in ('supervisor', 'stand_in_supervisor') and user.get('supervisor_id'):
        if row.get('supervisor_id') != user['supervisor_id']: return None
    return row

# ─── SCHEMA ───────────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS institutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT DEFAULT '',
    county TEXT DEFAULT '',
    contact TEXT DEFAULT '',
    email TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS supervisors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    department_id INTEGER REFERENCES departments(id),
    job_title TEXT DEFAULT 'ICT Officer',
    phone TEXT DEFAULT '',
    email TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    email TEXT DEFAULT '',
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    supervisor_id INTEGER REFERENCES supervisors(id),
    must_change_password INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS attachees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    id_number TEXT DEFAULT '',
    gender TEXT DEFAULT '',
    dob TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    email TEXT DEFAULT '',
    institution_id INTEGER REFERENCES institutions(id),
    course TEXT DEFAULT '',
    year_of_study INTEGER,
    reg_no TEXT DEFAULT '',
    department_id INTEGER REFERENCES departments(id),
    supervisor_id INTEGER REFERENCES supervisors(id),
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT DEFAULT 'Active',
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attachee_id INTEGER NOT NULL REFERENCES attachees(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    type TEXT DEFAULT 'Monthly',
    score INTEGER DEFAULT 0,
    performance TEXT DEFAULT 'Good',
    attendance INTEGER DEFAULT 100,
    technical_skills TEXT DEFAULT '',
    communication TEXT DEFAULT '',
    punctuality TEXT DEFAULT '',
    team_work TEXT DEFAULT '',
    remarks TEXT DEFAULT '',
    evaluated_by INTEGER REFERENCES supervisors(id)
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attachee_id INTEGER NOT NULL REFERENCES attachees(id) ON DELETE CASCADE,
    doc_type TEXT DEFAULT '',
    file_name TEXT NOT NULL,
    issued_date TEXT DEFAULT '',
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS password_resets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    token TEXT NOT NULL UNIQUE,
    temp_password TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    created_at TEXT NOT NULL,
    resolved_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS pending_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL,
    target_table TEXT NOT NULL,
    target_id INTEGER,
    payload TEXT NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    resolved_by INTEGER REFERENCES users(id),
    resolved_at TEXT,
    rejection_reason TEXT DEFAULT ''
);
"""

SEED_DEPARTMENTS = [
    (3,'IT Support & Helpdesk','End-user support and hardware maintenance'),
    (4,'Cybersecurity','Information security and compliance'),
    (6,'Health and Sanitation','County health and sanitation services'),
    (7,'Office of the Deputy Governor','Office of the Deputy Governor — Kilifi County'),
    (8,'Public Service Administration, Communication & Participatory Development','Public service and communication'),
    (9,'Public Works, Roads & Transport','Infrastructure, roads and transport'),
    (10,'Lands, Energy, Housing, Physical Planning & Urban Development','Lands, housing and urban development'),
    (11,'Mariakani Sub County Hospital','Mariakani Sub County Hospital ICT'),
    (12,'Office of the County Attorney','County Attorney legal and ICT support'),
    (13,'Malindi Sub County Hospital','Malindi Sub County Hospital ICT'),
    (14,'Water, Environment, Forestry, Climate Change & Solid Waste Management','Water and environment department'),
    (15,'Kaloleni Sub County Hospital','Kaloleni Sub County Hospital ICT'),
    (16,'Agriculture, Livestock, Fisheries & Blue Economy','Agriculture and blue economy'),
]
SEED_INSTITUTIONS = [
    (1,'Technical University of Mombasa','University','Mombasa','+254 41 2492222','info@tum.ac.ke'),
    (2,'Pwani University','University','Kilifi','+254 41 2022000','registrar@pu.ac.ke'),
    (3,'Kenya Coast National Polytechnic','Polytechnic','Mombasa','+254 722 000001','info@kcnp.ac.ke'),
    (5,'University of Eldoret','University','Uasin Gishu','','info@ue.ac.ke'),
    (6,'Laikipia University','University','Laikipia','',''),
    (7,'University of Embu','University','Embu','',''),
    (8,'Godoma Technical Training Institute','TVET','Kilifi','',''),
    (9,'Kiriri University of Science and Technology','University','Nairobi','',''),
    (10,'Jaramogi Oginga Odinga University of Science & Technology','University','Siaya','',''),
    (11,'Taita Taveta National Polytechnic','Polytechnic','Taita Taveta','',''),
    (12,'Kirinyaga University','University','Kirinyaga','',''),
    (13,'Weru Technical and Vocational College','TVET','Tharaka Nithi','',''),
    (14,'Machakos University','University','Machakos','',''),
    (15,'Kinango Technical and Vocational College','TVET','Kwale','',''),
    (16,'Shanzu Teachers Technical Training College','TVET','Mombasa','',''),
    (17,'Kaloleni Technical and Vocational College','TVET','Kilifi','',''),
    (18,'Bungoma National Polytechnic','Polytechnic','Bungoma','',''),
    (19,'Maseno University','University','Kisumu','',''),
]
SEED_SUPERVISORS = [
    (6,'Linus Tinga',3,'ICT Officer','0797776367','linustinga254@gmail.com'),
    (7,'Betty Mhache',11,'ICT Officer','',''),
    (8,'Laban',3,'ICT Officer','',''),
    (9,'Michael Chando',7,'ICT Officer','',''),
    (10,'Owen Kodi',6,'ICT Officer','',''),
    (11,'Emily Dama',8,'ICT Officer','',''),
    (12,'Sharon Oloo',9,'ICT Officer','',''),
    (13,'Jemimah Idza',6,'ICT Officer','',''),
    (14,'Bethwel Sanga',10,'ICT Officer','',''),
    (15,'Junior Mbogo',12,'ICT Officer','',''),
    (16,'Malindi ICT Officer',13,'ICT Officer','',''),
    (17,'ICT Officer Water',14,'ICT Officer','',''),
    (18,'Chrispas Tuku',15,'ICT Officer','',''),
    (19,'Stanley',16,'ICT Officer','',''),
]
SEED_USERS = [
    (1,'admin','System Administrator','admin@ict.local',hash_pass('Admin@1234'),'admin',None,0),
    (6,'linus','Linus Tinga','linustinga254@gmail.com',hash_pass('Pass@1234'),'supervisor',6,1),
    (7,'betty','Betty Mhache','b.mhache@kilifi.go.ke',hash_pass('Pass@1234'),'supervisor',7,1),
    (8,'laban','Laban','',hash_pass('Pass@1234'),'supervisor',8,1),
    (9,'michael','Michael Chando','',hash_pass('Pass@1234'),'supervisor',9,1),
    (10,'owen','Owen Kodi','',hash_pass('Pass@1234'),'supervisor',10,1),
    (11,'emily','Emily Dama','',hash_pass('Pass@1234'),'supervisor',11,1),
    (12,'sharon','Sharon Oloo','',hash_pass('Pass@1234'),'supervisor',12,1),
    (13,'jemimah','Jemimah Idza','',hash_pass('Pass@1234'),'supervisor',13,1),
    (14,'bethwel','Bethwel Sanga','',hash_pass('Pass@1234'),'supervisor',14,1),
    (15,'junior','Junior Mbogo','',hash_pass('Pass@1234'),'supervisor',15,1),
]
SEED_ATTACHEES = [
    (6,'William','Saidi','40652223','Male','2003-04-05','0716168180','willymtana254@gmail.com',5,'Computer Science',3,'COM/014/23',3,6,'2026-05-19','2026-07-31','Active','Committed'),
    (7,'Joseph','Mwangaza','41285293','Male','2003-01-31','0792918456','josephmwangaza1@gmail.com',6,'Bachelor of Science Information Communication and Technology',4,'SC/ICT/1274/22',3,6,'2026-05-11','2026-08-11','Active','Committed'),
    (8,'Isaac','Mwangi','41989457','Male','','0714207777','',2,'Bachelor of Science in Computer Science',3,'',3,6,'2026-05-26','2026-08-31','Active',''),
    (9,'Samini','Kenga','39161218','Male','','0700000009','',3,'Diploma in Information Communication Technology',None,'',4,7,'2026-05-21','2026-08-21','Active',''),
    (10,'Paul','Wanjiku','29997641','Male','','0700000010','',2,'Diploma in ICT',2,'',6,8,'2026-06-08','2026-09-04','Active',''),
    (11,'Khalid','Swaleh','','Male','','0700000011','',7,'Bachelor of Science in Computer Science',3,'',7,9,'2026-05-11','2026-08-14','Active',''),
    (12,'Gladys','Salama','','Female','','0700000012','',3,'Diploma in Information Communication Technology',3,'',6,10,'2026-05-11','2026-08-14','Active',''),
    (13,'Amina','Rashid','','Female','','0700000013','',8,'Certificate in Information & Communication Technology',2,'',8,11,'2026-05-11','2026-07-31','Active',''),
    (14,'Sidi','Kahindi','','Female','','0700000014','',9,'Public Works',3,'',9,12,'2026-06-02','2026-08-28','Active',''),
    (15,'Victor','Mutembei','','Male','','0700000015','',10,'Bachelor of Science in IT',3,'',9,12,'2026-06-02','2026-08-28','Active',''),
    (16,'Salome','Kitsao','131933865','Female','','0700000016','',11,'Certificate in Information Communication and Technology',2,'',6,13,'2026-05-04','2026-07-31','Active',''),
    (17,'Jimmy','Safari','','Male','','0700000017','',12,'Degree in Software Engineering',3,'',10,14,'2026-05-05','2026-08-07','Active',''),
    (18,'Santa','Nyamawi','','Female','','0700000018','',13,'Diploma in Information and Communication Technology',2,'',8,11,'2026-05-05','2026-08-07','Active',''),
    (19,'George','Kesi','42463818','Male','','0700000019','',14,'Bachelor of Science in Computer Science',3,'',11,7,'2026-05-04','2026-07-31','Active',''),
    (20,'Grace','Wema','42522263','Female','','0700000020','',2,'Bachelor of Science in Computer Science',3,'',12,15,'2026-05-11','2026-08-15','Active',''),
    (21,'Festus','Matsitsa','42473499','Male','','0700000021','',2,'Bachelor of Science in Computer Science',3,'',10,14,'2026-05-11','2026-08-15','Active',''),
    (22,'Khamis Athman','Athman','3989272767','Male','','0700000022','',12,'Bachelor of Business Information Technology',3,'',13,16,'2026-04-06','2026-08-21','Active',''),
    (23,'Vicent','Kimathi','','','','0700000023','',15,'Diploma in ICT',2,'',7,9,'2026-05-08','2026-08-07','Active',''),
    (24,'Vicent','Odhiambo','42221117','Male','','0700000024','',2,'Bachelor of Science in Computer Science',3,'',14,17,'2026-05-11','2026-08-15','Active',''),
    (25,'Steve','Mayaka','42803982','Male','','0700000025','',2,'Bachelor of Science in Computer Science',3,'',14,17,'2026-05-11','2026-08-15','Active',''),
    (26,'Edgar','Majaliwa','40080855','Male','','0700000026','',16,'Certificate in ICT',2,'',8,11,'2026-03-23','2026-05-29','Active',''),
    (27,'Maxwel','Kazungu','42607891','Male','','0700000027','',16,'Certificate in ICT',2,'',6,10,'2026-03-02','2026-05-29','Active',''),
    (28,'Monica','Ngumbao','41046899','Female','','0700000028','',3,'Diploma in ICT',2,'',6,10,'2026-01-26','2026-04-25','Active',''),
    (29,'Eunice','Kwekwe','41611887','Female','','0700000029','',15,'Artisan in ICT',2,'',15,18,'2026-01-26','2026-04-24','Active',''),
    (30,'Sarah','Francis','','Female','','0700000030','',17,'Diploma in ICT',2,'',6,8,'2026-01-21','2026-04-20','Active',''),
    (31,'Angela','John','42526800','Female','','0700000031','',16,'Certificate in ICT',2,'',16,19,'2026-01-19','2026-04-17','Active',''),
    (32,'Rehema','Mwambire','','','','0700000032','',18,'Certificate in ICT',2,'',10,14,'2026-01-14','2026-04-12','Active',''),
    (33,'Ian','Chivatsi','39915619','Male','','0700000033','',19,'Bachelor of Science in Computer Science',4,'',6,13,'2026-01-08','2026-04-10','Active',''),
]
SEED_EVALUATIONS = [
    (7,6,'2026-05-25','Weekly',80,'Excellent',90,'Database management','Excellent','Timely','Co-operative','Committed',6),
]

def init_db():
    with get_db() as conn:
        conn.executescript(SCHEMA)
        for col_sql in [
            "ALTER TABLE users ADD COLUMN supervisor_id INTEGER REFERENCES supervisors(id)",
            "ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN parent_user_id INTEGER REFERENCES users(id)",
            # ── FIX: drop NOT NULL constraint on phone so old records can be edited ──
            # SQLite can't ALTER column constraints; we leave the column as DEFAULT ''
            # and handle it in application logic (phone optional on PUT, required on POST)
        ]:
            try: conn.execute(col_sql); conn.commit()
            except Exception: pass
        fresh = conn.execute("SELECT COUNT(*) FROM departments").fetchone()[0] == 0
        if fresh:
            conn.executemany("INSERT OR IGNORE INTO departments(id,name,description) VALUES(?,?,?)", SEED_DEPARTMENTS)
            conn.executemany("INSERT OR IGNORE INTO institutions(id,name,type,county,contact,email) VALUES(?,?,?,?,?,?)", SEED_INSTITUTIONS)
            conn.executemany("INSERT OR IGNORE INTO supervisors(id,name,department_id,job_title,phone,email) VALUES(?,?,?,?,?,?)", SEED_SUPERVISORS)
            conn.executemany("INSERT OR IGNORE INTO users(id,username,full_name,email,password_hash,role,supervisor_id,must_change_password) VALUES(?,?,?,?,?,?,?,?)", SEED_USERS)
            conn.executemany("INSERT OR IGNORE INTO attachees(id,first_name,last_name,id_number,gender,dob,phone,email,institution_id,course,year_of_study,reg_no,department_id,supervisor_id,start_date,end_date,status,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", SEED_ATTACHEES)
            conn.executemany("INSERT OR IGNORE INTO evaluations(id,attachee_id,date,type,score,performance,attendance,technical_skills,communication,punctuality,team_work,remarks,evaluated_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", SEED_EVALUATIONS)
        else:
            for u in SEED_USERS:
                uid,username,full_name,email,pw_hash,role,sup_id,must_change = u
                if conn.execute("SELECT id FROM users WHERE id=?", (uid,)).fetchone():
                    conn.execute("UPDATE users SET username=?,full_name=?,role=?,supervisor_id=? WHERE id=?",
                                 (username,full_name,role,sup_id,uid))
                else:
                    conn.execute("INSERT OR IGNORE INTO users(id,username,full_name,email,password_hash,role,supervisor_id,must_change_password) VALUES(?,?,?,?,?,?,?,?)", u)
        conn.commit()

# ─── AUTH ──────────────────────────────────────────────────────────────────────

@app.route('/api/login', methods=['POST'])
def login():
    ip = request.remote_addr
    if not _check_rate_limit(ip):
        return jsonify(error='Too many login attempts. Please wait 1 minute.'), 429
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        return jsonify(error='Username and password are required'), 400
    with get_db() as conn:
        user = row_to_dict(conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone())
        if user:
            salted = hash_pass(password)
            legacy = hash_pass_legacy(password)
            if user['password_hash'] in (salted, legacy):
                if user['password_hash'] == legacy:
                    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (salted, user['id']))
                    conn.commit()
                token = create_access_token(identity=str(user['id']))
                return jsonify(token=token, user={
                    'id': user['id'], 'username': user['username'],
                    'fullName': user['full_name'], 'email': user['email'],
                    'role': user['role'],
                    'supervisorId': user.get('supervisor_id'),
                    'mustChangePassword': bool(user.get('must_change_password'))
                })
    return jsonify(error='Invalid username or password'), 401

@app.route('/api/me', methods=['GET'])
@jwt_required()
def me():
    uid = int(get_jwt_identity())
    with get_db() as conn:
        user = row_to_dict(conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
    if not user: return jsonify(error='Not found'), 404
    return jsonify(id=user['id'], username=user['username'], fullName=user['full_name'],
                   email=user['email'], role=user['role'],
                   supervisorId=user.get('supervisor_id'),
                   mustChangePassword=bool(user.get('must_change_password')))

@app.route('/api/me/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    uid = int(get_jwt_identity())
    d = request.get_json() or {}
    username   = (d.get('username') or '').strip()
    current_pw = d.get('currentPassword') or ''
    new_pw     = d.get('newPassword') or ''
    if not username:   return jsonify(error='Username cannot be empty'), 400
    if not current_pw: return jsonify(error='Current password is required to confirm changes'), 400
    with get_db() as conn:
        user = row_to_dict(conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
        if not user: return jsonify(error='User not found'), 404
        if user['password_hash'] not in (hash_pass(current_pw), hash_pass_legacy(current_pw)):
            return jsonify(error='Current password is incorrect'), 401
        taken = row_to_dict(conn.execute(
            "SELECT id FROM users WHERE username=? AND id!=?", (username, uid)).fetchone())
        if taken: return jsonify(error='Username already taken by another user'), 409
        if new_pw:
            if len(new_pw) < 6: return jsonify(error='New password must be at least 6 characters'), 400
            conn.execute("UPDATE users SET username=?,password_hash=?,must_change_password=0 WHERE id=?",
                         (username, hash_pass(new_pw), uid))
        else:
            conn.execute("UPDATE users SET username=? WHERE id=?", (username, uid))
        conn.commit()
        updated = row_to_dict(conn.execute(
            "SELECT id,username,full_name,email,role,supervisor_id FROM users WHERE id=?", (uid,)).fetchone())
    return jsonify(updated)

@app.route('/api/change-password', methods=['POST'])
@jwt_required()
def change_password():
    uid = int(get_jwt_identity())
    d = request.get_json() or {}
    current_pw = d.get('currentPassword') or ''
    new_pw     = d.get('newPassword') or ''
    if not current_pw or not new_pw:
        return jsonify(error='Both current and new password are required'), 400
    if len(new_pw) < 6:
        return jsonify(error='New password must be at least 6 characters'), 400
    with get_db() as conn:
        user = row_to_dict(conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
        if not user: return jsonify(error='User not found'), 404
        if user['password_hash'] not in (hash_pass(current_pw), hash_pass_legacy(current_pw)):
            return jsonify(error='Current password is incorrect'), 401
        conn.execute("UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?",
                     (hash_pass(new_pw), uid))
        conn.commit()
    return jsonify(ok=True, message='Password changed successfully')

# ─── DEPARTMENTS ───────────────────────────────────────────────────────────────

@app.route('/api/departments', methods=['GET'])
@jwt_required()
def get_departments():
    with get_db() as conn:
        rows = rows_to_list(conn.execute("SELECT * FROM departments ORDER BY name").fetchall())
    return jsonify(rows)

@app.route('/api/departments', methods=['POST'])
@jwt_required()
def add_department():
    uid = int(get_jwt_identity())
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name: return jsonify(error='Name required'), 400
    with get_db() as conn:
        me = get_current_user(conn, uid)
        payload = {'name': name, 'description': data.get('description','').strip()}
        if requires_approval(me, 'CREATE', 'departments'):
            create_pending_approval(conn, 'CREATE', 'departments', None, payload, uid)
            return jsonify(pending=True, message='Action submitted for approval.'), 202
        cur = conn.execute("INSERT INTO departments(name,description) VALUES(?,?)",
                           (name, payload['description']))
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM departments WHERE id=?", (cur.lastrowid,)).fetchone())
    return jsonify(row), 201

@app.route('/api/departments/<int:did>', methods=['PUT'])
@jwt_required()
def update_department(did):
    uid = int(get_jwt_identity())
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name: return jsonify(error='Name required'), 400
    with get_db() as conn:
        me = get_current_user(conn, uid)
        payload = {'name': name, 'description': data.get('description','').strip()}
        if requires_approval(me, 'UPDATE', 'departments'):
            create_pending_approval(conn, 'UPDATE', 'departments', did, payload, uid)
            return jsonify(pending=True, message='Action submitted for approval.'), 202
        conn.execute("UPDATE departments SET name=?,description=? WHERE id=?",
                     (name, payload['description'], did))
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM departments WHERE id=?", (did,)).fetchone())
    return jsonify(row)

@app.route('/api/departments/<int:did>', methods=['DELETE'])
@jwt_required()
def delete_department(did):
    uid = int(get_jwt_identity())
    with get_db() as conn:
        me = get_current_user(conn, uid)
        if requires_approval(me, 'DELETE', 'departments'):
            create_pending_approval(conn, 'DELETE', 'departments', did, {}, uid)
            return jsonify(pending=True, message='Action submitted for approval.'), 202
        count = conn.execute("SELECT COUNT(*) FROM attachees WHERE department_id=?", (did,)).fetchone()[0]
        if count > 0: return jsonify(error=f'Cannot delete — {count} attachee(s) assigned'), 409
        conn.execute("DELETE FROM departments WHERE id=?", (did,))
        conn.commit()
    return jsonify(ok=True)

# ─── INSTITUTIONS ──────────────────────────────────────────────────────────────

@app.route('/api/institutions', methods=['GET'])
@jwt_required()
def get_institutions():
    with get_db() as conn:
        rows = rows_to_list(conn.execute("SELECT * FROM institutions ORDER BY name").fetchall())
    return jsonify(rows)

@app.route('/api/institutions', methods=['POST'])
@jwt_required()
def add_institution():
    uid = int(get_jwt_identity())
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name: return jsonify(error='Name required'), 400
    with get_db() as conn:
        me = get_current_user(conn, uid)
        payload = {
            'name': name,
            'type': data.get('type',''),
            'county': data.get('county',''),
            'contact': data.get('contact',''),
            'email': data.get('email','')
        }
        if requires_approval(me, 'CREATE', 'institutions'):
            create_pending_approval(conn, 'CREATE', 'institutions', None, payload, uid)
            return jsonify(pending=True, message='Action submitted for approval.'), 202
            
        # Return existing row if name already exists (prevents duplicates from manual entry)
        existing = row_to_dict(conn.execute(
            "SELECT * FROM institutions WHERE LOWER(name)=LOWER(?)", (name,)).fetchone())
        if existing:
            return jsonify(existing), 200
        cur = conn.execute(
            "INSERT INTO institutions(name,type,county,contact,email) VALUES(?,?,?,?,?)",
            (name, payload['type'], payload['county'],
             payload['contact'], payload['email']))
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM institutions WHERE id=?", (cur.lastrowid,)).fetchone())
    return jsonify(row), 201

@app.route('/api/institutions/<int:iid>', methods=['PUT'])
@jwt_required()
def update_institution(iid):
    uid = int(get_jwt_identity())
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name: return jsonify(error='Name required'), 400
    with get_db() as conn:
        me = get_current_user(conn, uid)
        payload = {
            'name': name,
            'type': data.get('type',''),
            'county': data.get('county',''),
            'contact': data.get('contact',''),
            'email': data.get('email','')
        }
        if requires_approval(me, 'UPDATE', 'institutions'):
            create_pending_approval(conn, 'UPDATE', 'institutions', iid, payload, uid)
            return jsonify(pending=True, message='Action submitted for approval.'), 202
        conn.execute("UPDATE institutions SET name=?,type=?,county=?,contact=?,email=? WHERE id=?",
                     (name, payload['type'], payload['county'],
                      payload['contact'], payload['email'], iid))
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM institutions WHERE id=?", (iid,)).fetchone())
    return jsonify(row)

@app.route('/api/external/institutions', methods=['GET'])
@jwt_required()
def search_external_institutions():
    """Search Kenyan universities/colleges/TVETs from the Kenya Data API.
    Used to power the autocomplete in the 'Institution' field when adding
    an attachee. This never writes to our own database — picking a result
    (or typing a brand-new name) is saved via POST /api/institutions, which
    already de-duplicates by name."""
    q = (request.args.get('q') or '').strip().lower()
    try:
        items = get_kenya_institutions()
    except (URLError, HTTPError, TimeoutError, ValueError, OSError):
        # Best-effort: if the external API is unreachable, fail quietly so the
        # person can still type the institution name in by hand.
        return jsonify([])
    if q:
        items = [i for i in items if q in i['name'].lower()]
    return jsonify(items[:25])

@app.route('/api/institutions/<int:iid>', methods=['DELETE'])
@jwt_required()
def delete_institution(iid):
    uid = int(get_jwt_identity())
    with get_db() as conn:
        me = get_current_user(conn, uid)
        if requires_approval(me, 'DELETE', 'institutions'):
            create_pending_approval(conn, 'DELETE', 'institutions', iid, {}, uid)
            return jsonify(pending=True, message='Action submitted for approval.'), 202
        count = conn.execute("SELECT COUNT(*) FROM attachees WHERE institution_id=?", (iid,)).fetchone()[0]
        if count > 0: return jsonify(error=f'Cannot delete — {count} attachee(s) assigned'), 409
        conn.execute("DELETE FROM institutions WHERE id=?", (iid,))
        conn.commit()
    return jsonify(ok=True)

# ─── SUPERVISORS ───────────────────────────────────────────────────────────────

@app.route('/api/supervisors', methods=['GET'])
@jwt_required()
def get_supervisors():
    with get_db() as conn:
        rows = rows_to_list(conn.execute("SELECT * FROM supervisors ORDER BY name").fetchall())
    return jsonify(rows)

@app.route('/api/supervisors', methods=['POST'])
@jwt_required()
def add_supervisor():
    uid = int(get_jwt_identity())
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name: return jsonify(error='Name required'), 400
    with get_db() as conn:
        me = get_current_user(conn, uid)
        payload = {
            'name': name,
            'department_id': data.get('departmentId'),
            'job_title': data.get('jobTitle','ICT Officer'),
            'phone': data.get('phone',''),
            'email': data.get('email','')
        }
        if requires_approval(me, 'CREATE', 'supervisors'):
            create_pending_approval(conn, 'CREATE', 'supervisors', None, payload, uid)
            return jsonify(pending=True, message='Action submitted for approval.'), 202
        cur = conn.execute(
            "INSERT INTO supervisors(name,department_id,job_title,phone,email) VALUES(?,?,?,?,?)",
            (name, payload['department_id'], payload['job_title'],
             payload['phone'], payload['email']))
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM supervisors WHERE id=?", (cur.lastrowid,)).fetchone())
    return jsonify(row), 201

@app.route('/api/supervisors/<int:sid>', methods=['DELETE'])
@jwt_required()
def delete_supervisor(sid):
    uid = int(get_jwt_identity())
    with get_db() as conn:
        me = get_current_user(conn, uid)
        if requires_approval(me, 'DELETE', 'supervisors'):
            create_pending_approval(conn, 'DELETE', 'supervisors', sid, {}, uid)
            return jsonify(pending=True, message='Action submitted for approval.'), 202
        count = conn.execute("SELECT COUNT(*) FROM attachees WHERE supervisor_id=?", (sid,)).fetchone()[0]
        if count > 0: return jsonify(error=f'Cannot delete — {count} attachee(s) assigned'), 409
        conn.execute("DELETE FROM supervisors WHERE id=?", (sid,))
        conn.commit()
    return jsonify(ok=True)

# ─── ATTACHEES ─────────────────────────────────────────────────────────────────

@app.route('/api/attachees', methods=['GET'])
@jwt_required()
def get_attachees():
    from datetime import date
    today = date.today().isoformat()
    uid = int(get_jwt_identity())
    with get_db() as conn:
        conn.execute("UPDATE attachees SET status='Completed' WHERE end_date < ? AND status='Active'", (today,))
        conn.execute("UPDATE attachees SET status='Active' WHERE end_date >= ? AND start_date <= ? AND status='Completed'", (today, today))
        conn.commit()
        user = row_to_dict(conn.execute("SELECT role, supervisor_id FROM users WHERE id=?", (uid,)).fetchone())
        if user['role'] in ('supervisor', 'stand_in_supervisor') and user.get('supervisor_id'):
            rows = rows_to_list(conn.execute(
                "SELECT * FROM attachees WHERE supervisor_id=? ORDER BY first_name,last_name",
                (user['supervisor_id'],)).fetchall())
        else:
            rows = rows_to_list(conn.execute(
                "SELECT * FROM attachees ORDER BY first_name,last_name").fetchall())
    return jsonify(rows)

@app.route('/api/attachees', methods=['POST'])
@jwt_required()
def add_attachee():
    uid = int(get_jwt_identity())
    d = request.get_json()
    fn    = (d.get('firstName') or '').strip()
    ln    = (d.get('lastName')  or '').strip()
    phone = (d.get('phone')     or '').strip()
    if not fn or not ln or not d.get('startDate') or not d.get('endDate'):
        return jsonify(error='First name, last name, start and end date are required'), 400
    # Phone required on new record creation
    if not phone:
        return jsonify(error='Phone number is required'), 400
    with get_db() as conn:
        me = get_current_user(conn, uid)
        supervisor_id = d.get('supervisorId')
        if me and me['role'] in ('supervisor', 'stand_in_supervisor') and me.get('supervisor_id'):
            supervisor_id = me['supervisor_id']
            
        payload = {
            'first_name': fn,
            'last_name': ln,
            'gender': d.get('gender',''),
            'dob': d.get('dob',''),
            'phone': phone,
            'email': d.get('email',''),
            'institution_id': d.get('institutionId'),
            'course': d.get('course',''),
            'year_of_study': d.get('yearOfStudy'),
            'reg_no': d.get('regNo',''),
            'department_id': d.get('departmentId'),
            'supervisor_id': supervisor_id,
            'start_date': d['startDate'],
            'end_date': d['endDate'],
            'status': d.get('status','Active'),
            'notes': d.get('notes','')
        }
        
        if requires_approval(me, 'CREATE', 'attachees'):
            create_pending_approval(conn, 'CREATE', 'attachees', None, payload, uid)
            return jsonify(pending=True, message='Action submitted for approval.'), 202
            
        cur = conn.execute("""
            INSERT INTO attachees(first_name,last_name,gender,dob,phone,email,
            institution_id,course,year_of_study,reg_no,department_id,supervisor_id,
            start_date,end_date,status,notes)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (fn, ln, payload['gender'], payload['dob'], phone, payload['email'],
             payload['institution_id'], payload['course'], payload['year_of_study'],
             payload['reg_no'], payload['department_id'], supervisor_id,
             payload['start_date'], payload['end_date'], payload['status'], payload['notes']))
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM attachees WHERE id=?", (cur.lastrowid,)).fetchone())
    return jsonify(row), 201

@app.route('/api/attachees/<int:aid>', methods=['GET'])
@jwt_required()
def get_attachee(aid):
    uid = int(get_jwt_identity())
    with get_db() as conn:
        row = attachee_visible_to(conn, uid, aid)
    if not row: return jsonify(error='Not found'), 404
    return jsonify(row)

@app.route('/api/attachees/<int:aid>', methods=['PUT'])
@jwt_required()
def update_attachee(aid):
    uid = int(get_jwt_identity())
    d     = request.get_json()
    fn    = (d.get('firstName') or '').strip()
    ln    = (d.get('lastName')  or '').strip()
    if not fn or not ln: return jsonify(error='Name required'), 400

    with get_db() as conn:
        existing = attachee_visible_to(conn, uid, aid)
        if not existing: return jsonify(error='Not found'), 404

        me = get_current_user(conn, uid)
        supervisor_id = d.get('supervisorId')
        if me and me['role'] in ('supervisor', 'stand_in_supervisor') and me.get('supervisor_id'):
            supervisor_id = me['supervisor_id']

        phone = (d.get('phone') or '').strip()
        if not phone:
            phone = existing.get('phone') or ''

        payload = {
            'first_name': fn,
            'last_name': ln,
            'gender': d.get('gender',''),
            'dob': d.get('dob',''),
            'phone': phone,
            'email': d.get('email',''),
            'institution_id': d.get('institutionId'),
            'course': d.get('course',''),
            'year_of_study': d.get('yearOfStudy'),
            'reg_no': d.get('regNo',''),
            'department_id': d.get('departmentId'),
            'supervisor_id': supervisor_id,
            'start_date': d.get('startDate'),
            'end_date': d.get('endDate'),
            'status': d.get('status','Active'),
            'notes': d.get('notes','')
        }

        if requires_approval(me, 'UPDATE', 'attachees'):
            create_pending_approval(conn, 'UPDATE', 'attachees', aid, payload, uid)
            return jsonify(pending=True, message='Action submitted for approval.'), 202

        conn.execute("""
            UPDATE attachees SET first_name=?,last_name=?,gender=?,dob=?,phone=?,email=?,
            institution_id=?,course=?,year_of_study=?,reg_no=?,department_id=?,supervisor_id=?,
            start_date=?,end_date=?,status=?,notes=? WHERE id=?""",
            (fn, ln, payload['gender'], payload['dob'], phone, payload['email'],
             payload['institution_id'], payload['course'], payload['year_of_study'],
             payload['reg_no'], payload['department_id'], supervisor_id,
             payload['start_date'], payload['end_date'], payload['status'],
             payload['notes'], aid))
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM attachees WHERE id=?", (aid,)).fetchone())
    return jsonify(row)

@app.route('/api/attachees/<int:aid>', methods=['DELETE'])
@jwt_required()
def delete_attachee(aid):
    uid = int(get_jwt_identity())
    with get_db() as conn:
        me = get_current_user(conn, uid)
        if not me or me['role'] not in ('admin', 'stand_in_admin'): return jsonify(error='Forbidden'), 403
        
        if requires_approval(me, 'DELETE', 'attachees'):
            create_pending_approval(conn, 'DELETE', 'attachees', aid, {}, uid)
            return jsonify(pending=True, message='Action submitted for approval.'), 202
            
        conn.execute("DELETE FROM attachees WHERE id=?", (aid,))
        conn.commit()
    return jsonify(ok=True)

# ─── EVALUATIONS ───────────────────────────────────────────────────────────────

@app.route('/api/attachees/<int:aid>/evaluations', methods=['GET'])
@jwt_required()
def get_evals(aid):
    uid = int(get_jwt_identity())
    with get_db() as conn:
        if not attachee_visible_to(conn, uid, aid): return jsonify(error='Not found'), 404
        rows = rows_to_list(conn.execute(
            "SELECT * FROM evaluations WHERE attachee_id=? ORDER BY date DESC", (aid,)).fetchall())
    return jsonify(rows)

@app.route('/api/attachees/<int:aid>/evaluations', methods=['POST'])
@jwt_required()
def add_eval(aid):
    uid = int(get_jwt_identity())
    d = request.get_json()
    with get_db() as conn:
        if not attachee_visible_to(conn, uid, aid): return jsonify(error='Not found'), 404
        me = get_current_user(conn, uid)
        evaluated_by = d.get('evaluatedBy')
        if me and me['role'] in ('supervisor', 'stand_in_supervisor') and me.get('supervisor_id'):
            evaluated_by = me['supervisor_id']
            
        payload = {
            'attachee_id': aid,
            'date': d.get('date'),
            'type': d.get('type','Monthly'),
            'score': d.get('score',0),
            'performance': d.get('performance','Good'),
            'attendance': d.get('attendance',100),
            'technical_skills': d.get('technicalSkills',''),
            'communication': d.get('communication',''),
            'punctuality': d.get('punctuality',''),
            'team_work': d.get('teamWork',''),
            'remarks': d.get('remarks',''),
            'evaluated_by': evaluated_by
        }
        
        if requires_approval(me, 'CREATE', 'evaluations'):
            create_pending_approval(conn, 'CREATE', 'evaluations', None, payload, uid)
            return jsonify(pending=True, message='Action submitted for approval.'), 202
            
        cur = conn.execute("""
            INSERT INTO evaluations(attachee_id,date,type,score,performance,attendance,
            technical_skills,communication,punctuality,team_work,remarks,evaluated_by)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (aid, payload['date'], payload['type'], payload['score'],
             payload['performance'], payload['attendance'],
             payload['technical_skills'], payload['communication'],
             payload['punctuality'], payload['team_work'],
             payload['remarks'], evaluated_by))
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM evaluations WHERE id=?", (cur.lastrowid,)).fetchone())
    return jsonify(row), 201

@app.route('/api/attachees/<int:aid>/evaluations/<int:eid>', methods=['PUT'])
@jwt_required()
def update_eval(aid, eid):
    uid = int(get_jwt_identity())
    d = request.get_json()
    with get_db() as conn:
        if not attachee_visible_to(conn, uid, aid): return jsonify(error='Not found'), 404
        me = get_current_user(conn, uid)
        evaluated_by = d.get('evaluatedBy')
        if me and me['role'] in ('supervisor', 'stand_in_supervisor') and me.get('supervisor_id'):
            evaluated_by = me['supervisor_id']
            
        payload = {
            'date': d.get('date'),
            'type': d.get('type','Monthly'),
            'score': d.get('score',0),
            'performance': d.get('performance','Good'),
            'attendance': d.get('attendance',100),
            'technical_skills': d.get('technicalSkills',''),
            'communication': d.get('communication',''),
            'punctuality': d.get('punctuality',''),
            'team_work': d.get('teamWork',''),
            'remarks': d.get('remarks',''),
            'evaluated_by': evaluated_by
        }
        
        if requires_approval(me, 'UPDATE', 'evaluations'):
            create_pending_approval(conn, 'UPDATE', 'evaluations', eid, payload, uid)
            return jsonify(pending=True, message='Action submitted for approval.'), 202
            
        conn.execute("""UPDATE evaluations SET date=?,type=?,score=?,performance=?,attendance=?,
            technical_skills=?,communication=?,punctuality=?,team_work=?,remarks=?,evaluated_by=?
            WHERE id=? AND attachee_id=?""",
            (payload['date'], payload['type'], payload['score'],
             payload['performance'], payload['attendance'],
             payload['technical_skills'], payload['communication'],
             payload['punctuality'], payload['team_work'],
             payload['remarks'], evaluated_by, eid, aid))
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM evaluations WHERE id=?", (eid,)).fetchone())
    return jsonify(row)

@app.route('/api/attachees/<int:aid>/evaluations/<int:eid>', methods=['DELETE'])
@jwt_required()
def delete_eval(aid, eid):
    uid = int(get_jwt_identity())
    with get_db() as conn:
        if not attachee_visible_to(conn, uid, aid): return jsonify(error='Not found'), 404
        me = get_current_user(conn, uid)
        if requires_approval(me, 'DELETE', 'evaluations'):
            create_pending_approval(conn, 'DELETE', 'evaluations', eid, {}, uid)
            return jsonify(pending=True, message='Action submitted for approval.'), 202
            
        conn.execute("DELETE FROM evaluations WHERE id=? AND attachee_id=?", (eid, aid))
        conn.commit()
    return jsonify(ok=True)

# ─── DOCUMENTS ─────────────────────────────────────────────────────────────────

@app.route('/api/attachees/<int:aid>/documents', methods=['GET'])
@jwt_required()
def get_docs(aid):
    uid = int(get_jwt_identity())
    with get_db() as conn:
        if not attachee_visible_to(conn, uid, aid): return jsonify(error='Not found'), 404
        rows = rows_to_list(conn.execute(
            "SELECT * FROM documents WHERE attachee_id=? ORDER BY issued_date DESC", (aid,)).fetchall())
    return jsonify(rows)

@app.route('/api/attachees/<int:aid>/documents', methods=['POST'])
@jwt_required()
def add_doc(aid):
    uid = int(get_jwt_identity())
    d = request.get_json()
    name = (d.get('fileName') or '').strip()
    if not name: return jsonify(error='File name required'), 400
    with get_db() as conn:
        if not attachee_visible_to(conn, uid, aid): return jsonify(error='Not found'), 404
        me = get_current_user(conn, uid)
        payload = {
            'attachee_id': aid,
            'doc_type': d.get('docType',''),
            'file_name': name,
            'issued_date': d.get('issuedDate',''),
            'notes': d.get('notes','')
        }
        if requires_approval(me, 'CREATE', 'documents'):
            create_pending_approval(conn, 'CREATE', 'documents', None, payload, uid)
            return jsonify(pending=True, message='Action submitted for approval.'), 202
            
        cur = conn.execute(
            "INSERT INTO documents(attachee_id,doc_type,file_name,issued_date,notes) VALUES(?,?,?,?,?)",
            (aid, payload['doc_type'], payload['file_name'],
             payload['issued_date'], payload['notes']))
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM documents WHERE id=?", (cur.lastrowid,)).fetchone())
    return jsonify(row), 201

# ─── USERS ─────────────────────────────────────────────────────────────────────

@app.route('/api/users', methods=['GET'])
@jwt_required()
def get_users():
    uid = int(get_jwt_identity())
    with get_db() as conn:
        me = get_current_user(conn, uid)
        if me['role'] not in ('admin', 'stand_in_admin'): return jsonify(error='Forbidden'), 403
        rows = rows_to_list(conn.execute(
            "SELECT id,username,full_name,email,role FROM users ORDER BY username").fetchall())
    return jsonify(rows)

@app.route('/api/users', methods=['POST'])
@jwt_required()
def add_user():
    uid = int(get_jwt_identity())
    with get_db() as conn:
        me = get_current_user(conn, uid)
        d         = request.get_json()
        username  = (d.get('username')  or '').strip()
        full_name = (d.get('fullName')  or '').strip()
        password  = d.get('password')   or ''
        role      = d.get('role', 'viewer')
        
        is_admin_or_stand_in_admin = me['role'] in ('admin', 'stand_in_admin')
        is_supervisor_adding_stand_in = (me['role'] == 'supervisor' and role == 'stand_in_supervisor')
        is_main_admin_adding_stand_in_admin = (me['role'] == 'admin' and me['id'] == 1 and role == 'stand_in_admin')

        if role == 'stand_in_admin':
            # Only the main admin (id 1) may create a stand-in admin
            if not is_main_admin_adding_stand_in_admin:
                return jsonify(error='Forbidden: only the main admin can add a stand-in admin'), 403
        else:
            # Any admin or stand-in admin can add a viewer or supervisor; a supervisor can add their own stand-in
            if not is_admin_or_stand_in_admin and not is_supervisor_adding_stand_in:
                return jsonify(error='Forbidden'), 403
            
        if not username or not full_name or not password:
            return jsonify(error='Username, name and password required'), 400
            
        parent_user_id = uid
        supervisor_id = d.get('supervisorId')
        if me['role'] == 'supervisor':
            supervisor_id = me['supervisor_id']
            
        payload = {
            'username': username,
            'full_name': full_name,
            'email': d.get('email', ''),
            'password_hash': hash_pass(password),
            'role': role,
            'supervisor_id': supervisor_id,
            'must_change_password': 1,
            'parent_user_id': parent_user_id
        }
        
        if requires_approval(me, 'CREATE', 'users'):
            # Check unique username first to prevent duplicate entries in draft
            existing_user = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            if existing_user:
                return jsonify(error='Username already exists'), 409
            create_pending_approval(conn, 'CREATE', 'users', None, payload, uid)
            return jsonify(pending=True, message='User creation request submitted for admin approval.'), 202
            
        try:
            cur = conn.execute(
                "INSERT INTO users(username,full_name,email,password_hash,role,must_change_password,supervisor_id,parent_user_id) VALUES(?,?,?,?,?,?,?,?)",
                (username, full_name, payload['email'], payload['password_hash'], role, 1, supervisor_id, parent_user_id))
            conn.commit()
            row = row_to_dict(conn.execute(
                "SELECT id,username,full_name,email,role FROM users WHERE id=?", (cur.lastrowid,)).fetchone())
        except sqlite3.IntegrityError:
            return jsonify(error='Username already exists'), 409
    return jsonify(row), 201

@app.route('/api/users/<int:uid2>', methods=['DELETE'])
@jwt_required()
def delete_user(uid2):
    uid = int(get_jwt_identity())
    if uid == uid2: return jsonify(error='Cannot delete yourself'), 400
    with get_db() as conn:
        me = get_current_user(conn, uid)
        if me['role'] not in ('admin', 'stand_in_admin'): return jsonify(error='Forbidden'), 403
        
        if requires_approval(me, 'DELETE', 'users'):
            create_pending_approval(conn, 'DELETE', 'users', uid2, {}, uid)
            return jsonify(pending=True, message='User deletion request submitted for admin approval.'), 202
            
        conn.execute("DELETE FROM users WHERE id=?", (uid2,))
        conn.commit()
    return jsonify(ok=True)

# ─── FORGOT PASSWORD ──────────────────────────────────────────────────────────

@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    from datetime import datetime
    d = request.get_json() or {}
    username = (d.get('username') or '').strip()
    if not username: return jsonify(error='Username is required'), 400
    with get_db() as conn:
        user = row_to_dict(conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone())
        if not user:
            return jsonify(ok=True, message='If that username exists, a reset request has been submitted.')
        if conn.execute("SELECT id FROM password_resets WHERE username=? AND status='pending'", (username,)).fetchone():
            return jsonify(ok=True, message='A reset request is already pending. Please contact your admin.')
        token = secrets.token_hex(16)
        conn.execute("INSERT INTO password_resets(username,token,status,created_at) VALUES(?,?,'pending',?)",
                     (username, token, datetime.now().isoformat()))
        conn.commit()
    return jsonify(ok=True, message='Reset request submitted. Please contact your admin to approve it.')

@app.route('/api/forgot-password/requests', methods=['GET'])
@jwt_required()
def get_reset_requests():
    uid = int(get_jwt_identity())
    with get_db() as conn:
        me = row_to_dict(conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone())
        if me['role'] != 'admin': return jsonify(error='Forbidden'), 403
        rows = rows_to_list(conn.execute("SELECT * FROM password_resets ORDER BY created_at DESC").fetchall())
    return jsonify(rows)

@app.route('/api/forgot-password/resolve/<int:rid>', methods=['POST'])
@jwt_required()
def resolve_reset(rid):
    from datetime import datetime
    uid = int(get_jwt_identity())
    with get_db() as conn:
        me = row_to_dict(conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone())
        if me['role'] != 'admin': return jsonify(error='Forbidden'), 403
        req = row_to_dict(conn.execute("SELECT * FROM password_resets WHERE id=?", (rid,)).fetchone())
        if not req: return jsonify(error='Request not found'), 404
        d = request.get_json() or {}
        temp_pw = (d.get('tempPassword') or '').strip()
        if not temp_pw or len(temp_pw) < 6:
            return jsonify(error='Temporary password must be at least 6 characters'), 400
        conn.execute("UPDATE users SET password_hash=?,must_change_password=1 WHERE username=?",
                     (hash_pass(temp_pw), req['username']))
        conn.execute("UPDATE password_resets SET status='resolved',temp_password=?,resolved_at=? WHERE id=?",
                     (temp_pw, datetime.now().isoformat(), rid))
        conn.commit()
    return jsonify(ok=True, tempPassword=temp_pw)

@app.route('/api/forgot-password/dismiss/<int:rid>', methods=['DELETE'])
@jwt_required()
def dismiss_reset(rid):
    uid = int(get_jwt_identity())
    with get_db() as conn:
        me = row_to_dict(conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone())
        if me['role'] != 'admin': return jsonify(error='Forbidden'), 403
        conn.execute("DELETE FROM password_resets WHERE id=?", (rid,))
        conn.commit()
    return jsonify(ok=True)

# ─── APPROVALS SYSTEM ─────────────────────────────────────────────────────────

@app.route('/api/approvals', methods=['GET'])
@jwt_required()
def get_approvals():
    uid = int(get_jwt_identity())
    with get_db() as conn:
        me = get_current_user(conn, uid)
        if not me: return jsonify(error='Not found'), 404
        
        # Determine query based on role
        if me['role'] == 'admin' and me['id'] == 1:
            # Main Admin sees all
            rows = conn.execute("""
                SELECT p.*, u.full_name AS creator_name, u.role AS creator_role
                FROM pending_approvals p
                JOIN users u ON u.id = p.created_by
                ORDER BY p.created_at DESC
            """).fetchall()
        elif me['role'] == 'supervisor':
            # Main Supervisor sees approvals from their stand-ins
            rows = conn.execute("""
                SELECT p.*, u.full_name AS creator_name, u.role AS creator_role
                FROM pending_approvals p
                JOIN users u ON u.id = p.created_by
                WHERE u.parent_user_id = ?
                ORDER BY p.created_at DESC
            """, (uid,)).fetchall()
        else:
            # Stand-in users see their own submissions
            rows = conn.execute("""
                SELECT p.*, u.full_name AS creator_name, u.role AS creator_role
                FROM pending_approvals p
                JOIN users u ON u.id = p.created_by
                WHERE p.created_by = ?
                ORDER BY p.created_at DESC
            """, (uid,)).fetchall()
            
        res = []
        for r in rows:
            d = dict(r)
            # Try to enrich payload for preview
            try:
                d['parsed_payload'] = _json.loads(d['payload'])
            except Exception:
                d['parsed_payload'] = {}
            res.append(d)
            
    return jsonify(res)

@app.route('/api/approvals/<int:apid>/resolve', methods=['POST'])
@jwt_required()
def resolve_approval(apid):
    from datetime import datetime
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    status = data.get('status')
    rejection_reason = data.get('rejectionReason', '').strip()
    
    if status not in ('approved', 'rejected'):
        return jsonify(error='Status must be approved or rejected'), 400
        
    with get_db() as conn:
        me = get_current_user(conn, uid)
        if not me: return jsonify(error='Not found'), 404
        
        approval = row_to_dict(conn.execute("SELECT * FROM pending_approvals WHERE id=?", (apid,)).fetchone())
        if not approval:
            return jsonify(error='Approval request not found'), 404
            
        if approval['status'] != 'pending':
            return jsonify(error='Approval request already resolved'), 400
            
        creator = row_to_dict(conn.execute("SELECT id, role, parent_user_id FROM users WHERE id=?", (approval['created_by'],)).fetchone())
        if not creator:
            return jsonify(error='Creator not found'), 404
            
        # Check permissions:
        # Main Admin (ID=1) can resolve anything.
        # Main Supervisor can resolve if they are the parent of the creator.
        is_authorized = False
        if me['role'] == 'admin' and me['id'] == 1:
            is_authorized = True
        elif me['role'] == 'supervisor' and creator['parent_user_id'] == uid:
            is_authorized = True
            
        if not is_authorized:
            return jsonify(error='Forbidden'), 403
            
        resolved_at = datetime.now().isoformat()
        if status == 'approved':
            try:
                execute_pending_action(conn, approval)
                conn.execute(
                    "UPDATE pending_approvals SET status='approved', resolved_by=?, resolved_at=? WHERE id=?",
                    (uid, resolved_at, apid)
                )
            except Exception as e:
                return jsonify(error=f"Error executing action: {str(e)}"), 500
        else:
            conn.execute(
                "UPDATE pending_approvals SET status='rejected', resolved_by=?, resolved_at=?, rejection_reason=? WHERE id=?",
                (uid, resolved_at, rejection_reason, apid)
            )
            
        conn.commit()
    return jsonify(ok=True)

# ─── STATIC ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    # ── FIX: use BASE_DIR (absolute, anchored to this file) instead of '.' ────
    return send_from_directory(BASE_DIR, 'index.html')

# NOTE: klf-logo.webp and any other static assets sitting next to index.html
# and server.py are now served automatically because static_folder=BASE_DIR
# and static_url_path='' were set on the Flask app above — no extra route
# is needed for them. If you add more assets (css/js/images) in this same
# folder, they'll be reachable at "/<filename>" the same way.

# ─── MAIN ──────────────────────────────────────────────────────────────────────

init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n✅  Kilifi ICT Attachee Server running → http://localhost:{port}\n")
    app.run(host='0.0.0.0', port=port, debug=False)