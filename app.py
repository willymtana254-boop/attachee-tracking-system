"""
Kilifi County ICT Attachee Tracking System — Backend API
Run: python server.py
"""

import sqlite3, hashlib, os, json
from datetime import timedelta
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)

# Always resolve paths relative to this file, not the working directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=None)
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET', 'kilifi-ict-secret-2026-change-in-prod')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=12)
CORS(app)
jwt = JWTManager(app)

DB_PATH = os.path.join(BASE_DIR, 'kilifi.db')

# ─── DB HELPERS ───────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def hash_pass(p):
    return hashlib.sha256(p.encode()).hexdigest()

def row_to_dict(row):
    return dict(row) if row else None

def rows_to_list(rows):
    return [dict(r) for r in rows]

# ─── SCHEMA + SEED ────────────────────────────────────────────────────────────

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
    role TEXT NOT NULL DEFAULT 'viewer'
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
"""

SEED_DEPARTMENTS = [
    (3, 'IT Support & Helpdesk', 'End-user support and hardware maintenance'),
    (4, 'Cybersecurity', 'Information security and compliance'),
    (6, 'Health and Sanitation', 'County health and sanitation services'),
    (7, 'Office of the Deputy Governor', 'Office of the Deputy Governor — Kilifi County'),
    (8, 'Public Service Administration, Communication & Participatory Development', 'Public service and communication'),
    (9, 'Public Works, Roads & Transport', 'Infrastructure, roads and transport'),
    (10, 'Lands, Energy, Housing, Physical Planning & Urban Development', 'Lands, housing and urban development'),
    (11, 'Mariakani Sub County Hospital', 'Mariakani Sub County Hospital ICT'),
    (12, 'Office of the County Attorney', 'County Attorney legal and ICT support'),
    (13, 'Malindi Sub County Hospital', 'Malindi Sub County Hospital ICT'),
    (14, 'Water, Environment, Forestry, Climate Change & Solid Waste Management', 'Water and environment department'),
    (15, 'Kaloleni Sub County Hospital', 'Kaloleni Sub County Hospital ICT'),
    (16, 'Agriculture, Livestock, Fisheries & Blue Economy', 'Agriculture and blue economy'),
]

SEED_INSTITUTIONS = [
    (1, 'Technical University of Mombasa', 'University', 'Mombasa', '+254 41 2492222', 'info@tum.ac.ke'),
    (2, 'Pwani University', 'University', 'Kilifi', '+254 41 2022000', 'registrar@pu.ac.ke'),
    (3, 'Kenya Coast National Polytechnic', 'Polytechnic', 'Mombasa', '+254 722 000001', 'info@kcnp.ac.ke'),
    (5, 'University of Eldoret', 'University', 'Uasin Gishu', '', 'info@ue.ac.ke'),
    (6, 'Laikipia University', 'University', 'Laikipia', '', ''),
    (7, 'University of Embu', 'University', 'Embu', '', ''),
    (8, 'Godoma Technical Training Institute', 'TVET', 'Kilifi', '', ''),
    (9, 'Kiriri University of Science and Technology', 'University', 'Nairobi', '', ''),
    (10, 'Jaramogi Oginga Odinga University of Science & Technology', 'University', 'Siaya', '', ''),
    (11, 'Taita Taveta National Polytechnic', 'Polytechnic', 'Taita Taveta', '', ''),
    (12, 'Kirinyaga University', 'University', 'Kirinyaga', '', ''),
    (13, 'Weru Technical and Vocational College', 'TVET', 'Tharaka Nithi', '', ''),
    (14, 'Machakos University', 'University', 'Machakos', '', ''),
    (15, 'Kinango Technical and Vocational College', 'TVET', 'Kwale', '', ''),
    (16, 'Shanzu Teachers Technical Training College', 'TVET', 'Mombasa', '', ''),
    (17, 'Kaloleni Technical and Vocational College', 'TVET', 'Kilifi', '', ''),
    (18, 'Bungoma National Polytechnic', 'Polytechnic', 'Bungoma', '', ''),
    (19, 'Maseno University', 'University', 'Kisumu', '', ''),
]

SEED_SUPERVISORS = [
    (6, 'Linus Tinga', 3, 'ICT Officer', '0797776367', 'linustinga254@gmail.com'),
    (7, 'Betty Mhache', 11, 'ICT Officer', '', ''),
    (8, 'Laban', 3, 'ICT Officer', '', ''),
    (9, 'Michael Chando', 7, 'ICT Officer', '', ''),
    (10, 'Owen Kodi', 6, 'ICT Officer', '', ''),
    (11, 'Emily Dama', 8, 'ICT Officer', '', ''),
    (12, 'Sharon Oloo', 9, 'ICT Officer', '', ''),
    (13, 'Jemimah Idza', 6, 'ICT Officer', '', ''),
    (14, 'Bethwel Sanga', 10, 'ICT Officer', '', ''),
    (15, 'Junior Mbogo', 12, 'ICT Officer', '', ''),
    (16, 'Malindi ICT Officer', 13, 'ICT Officer', '', ''),
    (17, 'ICT Officer Water', 14, 'ICT Officer', '', ''),
    (18, 'Chrispas Tuku', 15, 'ICT Officer', '', ''),
    (19, 'Stanley', 16, 'ICT Officer', '', ''),
]

SEED_USERS = [
    (1,  'admin',   'System Administrator',  'admin@ict.local',              hash_pass('Admin@1234'), 'admin'),
    (6,  'linus',   'Linus Tinga',           'linustinga254@gmail.com',       hash_pass('Pass@1234'), 'supervisor'),
    (7,  'betty',   'Betty Mhache',          'b.mhache@kilifi.go.ke',         hash_pass('Pass@1234'), 'supervisor'),
    (8,  'laban',   'Laban',                 '',                              hash_pass('Pass@1234'), 'supervisor'),
    (9,  'michael', 'Michael Chando',        '',                              hash_pass('Pass@1234'), 'supervisor'),
    (10, 'owen',    'Owen Kodi',             '',                              hash_pass('Pass@1234'), 'supervisor'),
    (11, 'emily',   'Emily Dama',            '',                              hash_pass('Pass@1234'), 'supervisor'),
    (12, 'sharon',  'Sharon Oloo',           '',                              hash_pass('Pass@1234'), 'supervisor'),
    (13, 'jemimah', 'Jemimah Idza',         '',                              hash_pass('Pass@1234'), 'supervisor'),
    (14, 'bethwel', 'Bethwel Sanga',        '',                              hash_pass('Pass@1234'), 'supervisor'),
    (15, 'junior',  'Junior Mbogo',          '',                              hash_pass('Pass@1234'), 'supervisor'),
]

SEED_ATTACHEES = [
    (6, 'William','Saidi','40652223','Male','2003-04-05','0716168180','willymtana254@gmail.com',5,'Computer Science',3,'COM/014/23',3,6,'2026-05-19','2026-07-31','Active','Committed'),
    (7, 'Joseph','Mwangaza','41285293','Male','2003-01-31','0792918456','josephmwangaza1@gmail.com',6,'Bachelor of Science Information Communication and Technology',4,'SC/ICT/1274/22',3,6,'2026-05-11','2026-08-11','Active','Committed'),
    (8, 'Isaac','Mwangi','41989457','Male','','0714207777','',2,'Bachelor of Science in Computer Science',3,'',3,6,'2026-05-26','2026-08-31','Active',''),
    (9, 'Samini','Kenga','39161218','Male','','','',3,'Diploma in Information Communication Technology',None,'',4,7,'2026-05-21','2026-08-21','Active',''),
    (10,'Paul','Wanjiku','29997641','Male','','','',2,'Diploma in ICT',2,'',6,8,'2026-06-08','2026-09-04','Active',''),
    (11,'Khalid','Swaleh','','Male','','','',7,'Bachelor of Science in Computer Science',3,'',7,9,'2026-05-11','2026-08-14','Active',''),
    (12,'Gladys','Salama','','Female','','','',3,'Diploma in Information Communication Technology',3,'',6,10,'2026-05-11','2026-08-14','Active',''),
    (13,'Amina','Rashid','','Female','','','',8,'Certificate in Information & Communication Technology',2,'',8,11,'2026-05-11','2026-07-31','Active',''),
    (14,'Sidi','Kahindi','','Female','','','',9,'Public Works',3,'',9,12,'2026-06-02','2026-08-28','Active',''),
    (15,'Victor','Mutembei','','Male','','','',10,'Bachelor of Science in IT',3,'',9,12,'2026-06-02','2026-08-28','Active',''),
    (16,'Salome','Kitsao','131933865','Female','','','',11,'Certificate in Information Communication and Technology',2,'',6,13,'2026-05-04','2026-07-31','Active',''),
    (17,'Jimmy','Safari','','Male','','','',12,'Degree in Software Engineering',3,'',10,14,'2026-05-05','2026-08-07','Active',''),
    (18,'Santa','Nyamawi','','Female','','','',13,'Diploma in Information and Communication Technology',2,'',8,11,'2026-05-05','2026-08-07','Active',''),
    (19,'George','Kesi','42463818','Male','','','',14,'Bachelor of Science in Computer Science',3,'',11,7,'2026-05-04','2026-07-31','Active',''),
    (20,'Grace','Wema','42522263','Female','','','',2,'Bachelor of Science in Computer Science',3,'',12,15,'2026-05-11','2026-08-15','Active',''),
    (21,'Festus','Matsitsa','42473499','Male','','','',2,'Bachelor of Science in Computer Science',3,'',10,14,'2026-05-11','2026-08-15','Active',''),
    (22,'Khamis Athman','Athman','3989272767','Male','','','',12,'Bachelor of Business Information Technology',3,'',13,16,'2026-04-06','2026-08-21','Active',''),
    (23,'Vicent','Kimathi','','','','','',15,'Diploma in ICT',2,'',7,9,'2026-05-08','2026-08-07','Active',''),
    (24,'Vicent','Odhiambo','42221117','Male','','','',2,'Bachelor of Science in Computer Science',3,'',14,17,'2026-05-11','2026-08-15','Active',''),
    (25,'Steve','Mayaka','42803982','Male','','','',2,'Bachelor of Science in Computer Science',3,'',14,17,'2026-05-11','2026-08-15','Active',''),
    (26,'Edgar','Majaliwa','40080855','Male','','','',16,'Certificate in ICT',2,'',8,11,'2026-03-23','2026-05-29','Active',''),
    (27,'Maxwel','Kazungu','42607891','Male','','','',16,'Certificate in ICT',2,'',6,10,'2026-03-02','2026-05-29','Active',''),
    (28,'Monica','Ngumbao','41046899','Female','','','',3,'Diploma in ICT',2,'',6,10,'2026-01-26','2026-04-25','Active',''),
    (29,'Eunice','Kwekwe','41611887','Female','','','',15,'Artisan in ICT',2,'',15,18,'2026-01-26','2026-04-24','Active',''),
    (30,'Sarah','Francis','','Female','','','',17,'Diploma in ICT',2,'',6,8,'2026-01-21','2026-04-20','Active',''),
    (31,'Angela','John','42526800','Female','','','',16,'Certificate in ICT',2,'',16,19,'2026-01-19','2026-04-17','Active',''),
    (32,'Rehema','Mwambire','','','','','',18,'Certificate in ICT',2,'',10,14,'2026-01-14','2026-04-12','Active',''),
    (33,'Ian','Chivatsi','39915619','Male','','','',19,'Bachelor of Science in Computer Science',4,'',6,13,'2026-01-08','2026-04-10','Active',''),
]

SEED_EVALUATIONS = [
    (7, 6, '2026-05-25', 'Weekly', 80, 'Excellent', 90, 'Database management', 'Excellent', 'Timely', 'Co-operative', 'Committed', 6),
]

def init_db():
    with get_db() as conn:
        conn.executescript(SCHEMA)
        # Only seed if tables are empty
        if conn.execute("SELECT COUNT(*) FROM departments").fetchone()[0] == 0:
            conn.executemany("INSERT OR IGNORE INTO departments(id,name,description) VALUES(?,?,?)", SEED_DEPARTMENTS)
            conn.executemany("INSERT OR IGNORE INTO institutions(id,name,type,county,contact,email) VALUES(?,?,?,?,?,?)", SEED_INSTITUTIONS)
            conn.executemany("INSERT OR IGNORE INTO supervisors(id,name,department_id,job_title,phone,email) VALUES(?,?,?,?,?,?)", SEED_SUPERVISORS)
            conn.executemany("INSERT OR IGNORE INTO users(id,username,full_name,email,password_hash,role) VALUES(?,?,?,?,?,?)", SEED_USERS)
            conn.executemany("INSERT OR IGNORE INTO attachees(id,first_name,last_name,id_number,gender,dob,phone,email,institution_id,course,year_of_study,reg_no,department_id,supervisor_id,start_date,end_date,status,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", SEED_ATTACHEES)
            conn.executemany("INSERT OR IGNORE INTO evaluations(id,attachee_id,date,type,score,performance,attendance,technical_skills,communication,punctuality,team_work,remarks,evaluated_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", SEED_EVALUATIONS)
        conn.commit()

# ─── AUTH ──────────────────────────────────────────────────────────────────────

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    with get_db() as conn:
        user = row_to_dict(conn.execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone())
    if not user or user['password_hash'] != hash_pass(password):
        return jsonify(error='Invalid username or password'), 401
    token = create_access_token(identity=str(user['id']))
    return jsonify(token=token, user={
        'id': user['id'], 'username': user['username'],
        'fullName': user['full_name'], 'email': user['email'], 'role': user['role']
    })

@app.route('/api/me', methods=['GET'])
@jwt_required()
def me():
    uid = int(get_jwt_identity())
    with get_db() as conn:
        user = row_to_dict(conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
    if not user: return jsonify(error='Not found'), 404
    return jsonify(id=user['id'], username=user['username'], fullName=user['full_name'],
                   email=user['email'], role=user['role'])

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
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name: return jsonify(error='Name required'), 400
    with get_db() as conn:
        cur = conn.execute("INSERT INTO departments(name,description) VALUES(?,?)",
                           (name, data.get('description','').strip()))
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM departments WHERE id=?", (cur.lastrowid,)).fetchone())
    return jsonify(row), 201

@app.route('/api/departments/<int:did>', methods=['PUT'])
@jwt_required()
def update_department(did):
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name: return jsonify(error='Name required'), 400
    with get_db() as conn:
        conn.execute("UPDATE departments SET name=?,description=? WHERE id=?",
                     (name, data.get('description','').strip(), did))
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM departments WHERE id=?", (did,)).fetchone())
    return jsonify(row)

@app.route('/api/departments/<int:did>', methods=['DELETE'])
@jwt_required()
def delete_department(did):
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM attachees WHERE department_id=?", (did,)).fetchone()[0]
        if count > 0:
            return jsonify(error=f'Cannot delete — {count} attachee(s) assigned'), 409
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
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name: return jsonify(error='Name required'), 400
    with get_db() as conn:
        cur = conn.execute("INSERT INTO institutions(name,type,county,contact,email) VALUES(?,?,?,?,?)",
                           (name, data.get('type',''), data.get('county',''), data.get('contact',''), data.get('email','')))
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM institutions WHERE id=?", (cur.lastrowid,)).fetchone())
    return jsonify(row), 201

@app.route('/api/institutions/<int:iid>', methods=['PUT'])
@jwt_required()
def update_institution(iid):
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name: return jsonify(error='Name required'), 400
    with get_db() as conn:
        conn.execute("UPDATE institutions SET name=?,type=?,county=?,contact=?,email=? WHERE id=?",
                     (name, data.get('type',''), data.get('county',''), data.get('contact',''), data.get('email',''), iid))
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM institutions WHERE id=?", (iid,)).fetchone())
    return jsonify(row)

@app.route('/api/institutions/<int:iid>', methods=['DELETE'])
@jwt_required()
def delete_institution(iid):
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM attachees WHERE institution_id=?", (iid,)).fetchone()[0]
        if count > 0:
            return jsonify(error=f'Cannot delete — {count} attachee(s) assigned'), 409
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
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name: return jsonify(error='Name required'), 400
    with get_db() as conn:
        cur = conn.execute("INSERT INTO supervisors(name,department_id,job_title,phone,email) VALUES(?,?,?,?,?)",
                           (name, data.get('departmentId'), data.get('jobTitle','ICT Officer'), data.get('phone',''), data.get('email','')))
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM supervisors WHERE id=?", (cur.lastrowid,)).fetchone())
    return jsonify(row), 201

@app.route('/api/supervisors/<int:sid>', methods=['DELETE'])
@jwt_required()
def delete_supervisor(sid):
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM attachees WHERE supervisor_id=?", (sid,)).fetchone()[0]
        if count > 0:
            return jsonify(error=f'Cannot delete — {count} attachee(s) assigned'), 409
        conn.execute("DELETE FROM supervisors WHERE id=?", (sid,))
        conn.commit()
    return jsonify(ok=True)

# ─── ATTACHEES ─────────────────────────────────────────────────────────────────

@app.route('/api/attachees', methods=['GET'])
@jwt_required()
def get_attachees():
    with get_db() as conn:
        rows = rows_to_list(conn.execute("SELECT * FROM attachees ORDER BY first_name,last_name").fetchall())
    return jsonify(rows)

@app.route('/api/attachees', methods=['POST'])
@jwt_required()
def add_attachee():
    d = request.get_json()
    fn = (d.get('firstName') or '').strip()
    ln = (d.get('lastName') or '').strip()
    if not fn or not ln or not d.get('startDate') or not d.get('endDate'):
        return jsonify(error='First name, last name, start and end date are required'), 400
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO attachees(first_name,last_name,id_number,gender,dob,phone,email,
            institution_id,course,year_of_study,reg_no,department_id,supervisor_id,
            start_date,end_date,status,notes)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (fn, ln, d.get('idNumber',''), d.get('gender',''), d.get('dob',''),
             d.get('phone',''), d.get('email',''), d.get('institutionId'),
             d.get('course',''), d.get('yearOfStudy'), d.get('regNo',''),
             d.get('departmentId'), d.get('supervisorId'),
             d['startDate'], d['endDate'], d.get('status','Active'), d.get('notes','')))
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM attachees WHERE id=?", (cur.lastrowid,)).fetchone())
    return jsonify(row), 201

@app.route('/api/attachees/<int:aid>', methods=['GET'])
@jwt_required()
def get_attachee(aid):
    with get_db() as conn:
        row = row_to_dict(conn.execute("SELECT * FROM attachees WHERE id=?", (aid,)).fetchone())
    if not row: return jsonify(error='Not found'), 404
    return jsonify(row)

@app.route('/api/attachees/<int:aid>', methods=['PUT'])
@jwt_required()
def update_attachee(aid):
    d = request.get_json()
    fn = (d.get('firstName') or '').strip()
    ln = (d.get('lastName') or '').strip()
    if not fn or not ln: return jsonify(error='Name required'), 400
    with get_db() as conn:
        conn.execute("""
            UPDATE attachees SET first_name=?,last_name=?,id_number=?,gender=?,dob=?,
            phone=?,email=?,institution_id=?,course=?,year_of_study=?,reg_no=?,
            department_id=?,supervisor_id=?,start_date=?,end_date=?,status=?,notes=?
            WHERE id=?""",
            (fn, ln, d.get('idNumber',''), d.get('gender',''), d.get('dob',''),
             d.get('phone',''), d.get('email',''), d.get('institutionId'),
             d.get('course',''), d.get('yearOfStudy'), d.get('regNo',''),
             d.get('departmentId'), d.get('supervisorId'),
             d.get('startDate'), d.get('endDate'), d.get('status','Active'), d.get('notes',''), aid))
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM attachees WHERE id=?", (aid,)).fetchone())
    return jsonify(row)

@app.route('/api/attachees/<int:aid>', methods=['DELETE'])
@jwt_required()
def delete_attachee(aid):
    with get_db() as conn:
        conn.execute("DELETE FROM attachees WHERE id=?", (aid,))
        conn.commit()
    return jsonify(ok=True)

# ─── EVALUATIONS ───────────────────────────────────────────────────────────────

@app.route('/api/attachees/<int:aid>/evaluations', methods=['GET'])
@jwt_required()
def get_evals(aid):
    with get_db() as conn:
        rows = rows_to_list(conn.execute(
            "SELECT * FROM evaluations WHERE attachee_id=? ORDER BY date DESC", (aid,)).fetchall())
    return jsonify(rows)

@app.route('/api/attachees/<int:aid>/evaluations', methods=['POST'])
@jwt_required()
def add_eval(aid):
    d = request.get_json()
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO evaluations(attachee_id,date,type,score,performance,attendance,
            technical_skills,communication,punctuality,team_work,remarks,evaluated_by)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (aid, d.get('date'), d.get('type','Monthly'), d.get('score',0),
             d.get('performance','Good'), d.get('attendance',100),
             d.get('technicalSkills',''), d.get('communication',''),
             d.get('punctuality',''), d.get('teamWork',''),
             d.get('remarks',''), d.get('evaluatedBy')))
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM evaluations WHERE id=?", (cur.lastrowid,)).fetchone())
    return jsonify(row), 201

# ─── DOCUMENTS ─────────────────────────────────────────────────────────────────

@app.route('/api/attachees/<int:aid>/documents', methods=['GET'])
@jwt_required()
def get_docs(aid):
    with get_db() as conn:
        rows = rows_to_list(conn.execute(
            "SELECT * FROM documents WHERE attachee_id=? ORDER BY issued_date DESC", (aid,)).fetchall())
    return jsonify(rows)

@app.route('/api/attachees/<int:aid>/documents', methods=['POST'])
@jwt_required()
def add_doc(aid):
    d = request.get_json()
    name = (d.get('fileName') or '').strip()
    if not name: return jsonify(error='File name required'), 400
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO documents(attachee_id,doc_type,file_name,issued_date,notes) VALUES(?,?,?,?,?)",
            (aid, d.get('docType',''), name, d.get('issuedDate',''), d.get('notes','')))
        conn.commit()
        row = row_to_dict(conn.execute("SELECT * FROM documents WHERE id=?", (cur.lastrowid,)).fetchone())
    return jsonify(row), 201

# ─── USERS ─────────────────────────────────────────────────────────────────────

@app.route('/api/users', methods=['GET'])
@jwt_required()
def get_users():
    uid = int(get_jwt_identity())
    with get_db() as conn:
        me = row_to_dict(conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone())
        if me['role'] != 'admin': return jsonify(error='Forbidden'), 403
        rows = rows_to_list(conn.execute(
            "SELECT id,username,full_name,email,role FROM users ORDER BY username").fetchall())
    return jsonify(rows)

@app.route('/api/users', methods=['POST'])
@jwt_required()
def add_user():
    uid = int(get_jwt_identity())
    with get_db() as conn:
        me = row_to_dict(conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone())
        if me['role'] != 'admin': return jsonify(error='Forbidden'), 403
        d = request.get_json()
        username = (d.get('username') or '').strip()
        full_name = (d.get('fullName') or '').strip()
        password = d.get('password') or ''
        if not username or not full_name or not password:
            return jsonify(error='Username, name and password required'), 400
        try:
            cur = conn.execute(
                "INSERT INTO users(username,full_name,email,password_hash,role) VALUES(?,?,?,?,?)",
                (username, full_name, d.get('email',''), hash_pass(password), d.get('role','viewer')))
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
        me = row_to_dict(conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone())
        if me['role'] != 'admin': return jsonify(error='Forbidden'), 403
        conn.execute("DELETE FROM users WHERE id=?", (uid2,))
        conn.commit()
    return jsonify(ok=True)

# ─── CHANGE PASSWORD ──────────────────────────────────────────────────────────

@app.route('/api/change-password', methods=['POST'])
@jwt_required()
def change_password():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    current = data.get('currentPassword') or ''
    new_pw  = data.get('newPassword') or ''
    confirm = data.get('confirmPassword') or ''

    if not current or not new_pw or not confirm:
        return jsonify(error='All fields are required'), 400
    if new_pw != confirm:
        return jsonify(error='New passwords do not match'), 400
    if len(new_pw) < 6:
        return jsonify(error='New password must be at least 6 characters'), 400

    with get_db() as conn:
        user = row_to_dict(conn.execute(
            "SELECT * FROM users WHERE id=?", (uid,)
        ).fetchone())
        if not user or user['password_hash'] != hash_pass(current):
            return jsonify(error='Current password is incorrect'), 401
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (hash_pass(new_pw), uid)
        )
        conn.commit()
    return jsonify(ok=True, message='Password changed successfully')

# ─── STATIC (serve the frontend HTML) ─────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/styles.css')
def styles():
    return send_from_directory(BASE_DIR, 'styles.css')

@app.route('/app.js')
def appjs():
    return send_from_directory(BASE_DIR, 'app.js')

@app.route('/klf-logo.webp')
def logo():
    return send_from_directory(BASE_DIR, '/klf-logo.webp')

# ─── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    print(f"\n✅  Kilifi ICT Attachee Server running → http://localhost:{port}\n")
    app.run(host='0.0.0.0', port=port, debug=False)