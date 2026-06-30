from flask import Flask, send_from_directory, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)
import os, json, uuid, hashlib
from datetime import timedelta

app = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app)

app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'kilifi-ict-secret-2024')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=8)
jwt = JWTManager(app)

# ─── SIMPLE FILE-BASED DATABASE ───────────────────────────────────────────────
DB_FILE = 'db.json'

def load_db():
    if not os.path.exists(DB_FILE):
        return init_db()
    with open(DB_FILE, 'r') as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, 'w') as f:
        json.dump(db, f, indent=2)

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def init_db():
    db = {
        "users": [
            {
                "id": "user-1",
                "username": "admin",
                "fullName": "System Administrator",
                "email": "admin@kilifi.go.ke",
                "password": hash_pw("admin123"),
                "role": "admin"
            }
        ],
        "attachees": [],
        "evaluations": [],
        "documents": [],
        "supervisors": [
            {"id": "sup-1", "name": "Faith Kadenge", "department": "ICT", "email": "kadengefaith022@gmail.com"}
        ],
        "institutions": [
            {"id": "inst-1", "name": "University of Nairobi"},
            {"id": "inst-2", "name": "Moi University"},
            {"id": "inst-3", "name": "Kilifi National Polytechnic"},
            {"id": "inst-4", "name": "Kenya Medical Training College"}
        ],
        "departments": [
            {"id": "dept-1", "name": "ICT"},
            {"id": "dept-2", "name": "Finance"},
            {"id": "dept-3", "name": "Health"},
            {"id": "dept-4", "name": "Education"},
            {"id": "dept-5", "name": "Agriculture"}
        ]
    }
    save_db(db)
    return db

def new_id(prefix=''):
    return prefix + str(uuid.uuid4())[:8]

# ─── STATIC FILES ─────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/klf-logo.webp')
def logo():
    return send_from_directory('static', 'klf-logo.webp')

# ─── AUTH ─────────────────────────────────────────────────────────────────────
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    db = load_db()
    user = next((u for u in db['users']
                 if u['username'] == data.get('username')
                 and u['password'] == hash_pw(data.get('password', ''))), None)
    if not user:
        return jsonify({"msg": "Invalid username or password"}), 401
    token = create_access_token(identity=user['id'])
    safe = {k: v for k, v in user.items() if k != 'password'}
    return jsonify({"token": token, "user": safe})

@app.route('/api/me', methods=['GET'])
@jwt_required()
def me():
    db = load_db()
    uid = get_jwt_identity()
    user = next((u for u in db['users'] if u['id'] == uid), None)
    if not user:
        return jsonify({"msg": "Not found"}), 404
    return jsonify({k: v for k, v in user.items() if k != 'password'})

@app.route('/api/change-password', methods=['POST'])
@jwt_required()
def change_password():
    data = request.get_json()
    db = load_db()
    uid = get_jwt_identity()
    user = next((u for u in db['users'] if u['id'] == uid), None)
    if not user:
        return jsonify({"msg": "Not found"}), 404
    if user['password'] != hash_pw(data.get('currentPassword', '')):
        return jsonify({"msg": "Current password is incorrect"}), 400
    if data.get('newPassword') != data.get('confirmPassword'):
        return jsonify({"msg": "Passwords do not match"}), 400
    user['password'] = hash_pw(data['newPassword'])
    save_db(db)
    return jsonify({"msg": "Password changed successfully"})

# ─── USERS ────────────────────────────────────────────────────────────────────
@app.route('/api/users', methods=['GET'])
@jwt_required()
def get_users():
    db = load_db()
    return jsonify([{k: v for k, v in u.items() if k != 'password'} for u in db['users']])

@app.route('/api/users', methods=['POST'])
@jwt_required()
def create_user():
    data = request.get_json()
    db = load_db()
    if any(u['username'] == data['username'] for u in db['users']):
        return jsonify({"msg": "Username already exists"}), 400
    user = {
        "id": new_id("user-"),
        "username": data['username'],
        "fullName": data.get('fullName', ''),
        "email": data.get('email', ''),
        "password": hash_pw(data.get('password', '')),
        "role": data.get('role', 'viewer')
    }
    db['users'].append(user)
    save_db(db)
    return jsonify({k: v for k, v in user.items() if k != 'password'}), 201

@app.route('/api/users/<uid>', methods=['DELETE'])
@jwt_required()
def delete_user(uid):
    db = load_db()
    db['users'] = [u for u in db['users'] if u['id'] != uid]
    save_db(db)
    return jsonify({"msg": "Deleted"})

# ─── DEPARTMENTS ──────────────────────────────────────────────────────────────
@app.route('/api/departments', methods=['GET'])
@jwt_required()
def get_departments():
    return jsonify(load_db()['departments'])

@app.route('/api/departments', methods=['POST'])
@jwt_required()
def create_department():
    db = load_db()
    dept = {"id": new_id("dept-"), **request.get_json()}
    db['departments'].append(dept)
    save_db(db)
    return jsonify(dept), 201

@app.route('/api/departments/<did>', methods=['PUT'])
@jwt_required()
def update_department(did):
    db = load_db()
    dept = next((d for d in db['departments'] if d['id'] == did), None)
    if not dept: return jsonify({"msg": "Not found"}), 404
    dept.update(request.get_json())
    save_db(db)
    return jsonify(dept)

@app.route('/api/departments/<did>', methods=['DELETE'])
@jwt_required()
def delete_department(did):
    db = load_db()
    db['departments'] = [d for d in db['departments'] if d['id'] != did]
    save_db(db)
    return jsonify({"msg": "Deleted"})

# ─── INSTITUTIONS ─────────────────────────────────────────────────────────────
@app.route('/api/institutions', methods=['GET'])
@jwt_required()
def get_institutions():
    return jsonify(load_db()['institutions'])

@app.route('/api/institutions', methods=['POST'])
@jwt_required()
def create_institution():
    db = load_db()
    inst = {"id": new_id("inst-"), **request.get_json()}
    db['institutions'].append(inst)
    save_db(db)
    return jsonify(inst), 201

@app.route('/api/institutions/<iid>', methods=['PUT'])
@jwt_required()
def update_institution(iid):
    db = load_db()
    inst = next((i for i in db['institutions'] if i['id'] == iid), None)
    if not inst: return jsonify({"msg": "Not found"}), 404
    inst.update(request.get_json())
    save_db(db)
    return jsonify(inst)

@app.route('/api/institutions/<iid>', methods=['DELETE'])
@jwt_required()
def delete_institution(iid):
    db = load_db()
    db['institutions'] = [i for i in db['institutions'] if i['id'] != iid]
    save_db(db)
    return jsonify({"msg": "Deleted"})

# ─── SUPERVISORS ──────────────────────────────────────────────────────────────
@app.route('/api/supervisors', methods=['GET'])
@jwt_required()
def get_supervisors():
    return jsonify(load_db()['supervisors'])

@app.route('/api/supervisors', methods=['POST'])
@jwt_required()
def create_supervisor():
    db = load_db()
    sup = {"id": new_id("sup-"), **request.get_json()}
    db['supervisors'].append(sup)
    save_db(db)
    return jsonify(sup), 201

@app.route('/api/supervisors/<sid>', methods=['DELETE'])
@jwt_required()
def delete_supervisor(sid):
    db = load_db()
    db['supervisors'] = [s for s in db['supervisors'] if s['id'] != sid]
    save_db(db)
    return jsonify({"msg": "Deleted"})

# ─── ATTACHEES ────────────────────────────────────────────────────────────────
@app.route('/api/attachees', methods=['GET'])
@jwt_required()
def get_attachees():
    return jsonify(load_db()['attachees'])

@app.route('/api/attachees', methods=['POST'])
@jwt_required()
def create_attachee():
    db = load_db()
    attachee = {"id": new_id("att-"), **request.get_json()}
    db['attachees'].append(attachee)
    save_db(db)
    return jsonify(attachee), 201

@app.route('/api/attachees/<aid>', methods=['GET'])
@jwt_required()
def get_attachee(aid):
    db = load_db()
    attachee = next((a for a in db['attachees'] if a['id'] == aid), None)
    if not attachee: return jsonify({"msg": "Not found"}), 404
    return jsonify(attachee)

@app.route('/api/attachees/<aid>', methods=['PUT'])
@jwt_required()
def update_attachee(aid):
    db = load_db()
    attachee = next((a for a in db['attachees'] if a['id'] == aid), None)
    if not attachee: return jsonify({"msg": "Not found"}), 404
    attachee.update(request.get_json())
    save_db(db)
    return jsonify(attachee)

@app.route('/api/attachees/<aid>', methods=['DELETE'])
@jwt_required()
def delete_attachee(aid):
    db = load_db()
    db['attachees'] = [a for a in db['attachees'] if a['id'] != aid]
    db['evaluations'] = [e for e in db['evaluations'] if e.get('attacheeId') != aid]
    db['documents'] = [d for d in db['documents'] if d.get('attacheeId') != aid]
    save_db(db)
    return jsonify({"msg": "Deleted"})

# ─── EVALUATIONS ──────────────────────────────────────────────────────────────
@app.route('/api/attachees/<aid>/evaluations', methods=['GET'])
@jwt_required()
def get_evaluations(aid):
    db = load_db()
    evals = [e for e in db['evaluations'] if e.get('attacheeId') == aid]
    return jsonify(sorted(evals, key=lambda e: e.get('date', ''), reverse=True))

@app.route('/api/attachees/<aid>/evaluations', methods=['POST'])
@jwt_required()
def create_evaluation(aid):
    db = load_db()
    ev = {"id": new_id("eval-"), "attacheeId": aid, **request.get_json()}
    db['evaluations'].append(ev)
    save_db(db)
    return jsonify(ev), 201

# ─── DOCUMENTS ────────────────────────────────────────────────────────────────
@app.route('/api/attachees/<aid>/documents', methods=['GET'])
@jwt_required()
def get_documents(aid):
    db = load_db()
    return jsonify([d for d in db['documents'] if d.get('attacheeId') == aid])

@app.route('/api/attachees/<aid>/documents', methods=['POST'])
@jwt_required()
def create_document(aid):
    db = load_db()
    doc = {"id": new_id("doc-"), "attacheeId": aid, **request.get_json()}
    db['documents'].append(doc)
    save_db(db)
    return jsonify(doc), 201

# ─── RUN ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=False)
