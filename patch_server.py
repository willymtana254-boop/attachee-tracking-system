#!/usr/bin/env python3
"""
patch_server.py — adds admin delegation to server.py
Run once:  python patch_server.py
"""
import os, shutil

src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")
if not os.path.exists(src):
    print("ERROR: server.py not found."); exit(1)

shutil.copy(src, src + ".bak")
print("Backup → server.py.bak")

with open(src, encoding="utf-8") as f:
    code = f.read()

ok, fail = [], []
def patch(label, old, new):
    global code
    if old in code:
        code = code.replace(old, new, 1); ok.append(label)
    else:
        fail.append(label)

# ── 1. Add admin_delegates table to SCHEMA ────────────────────────────────────
patch("1 admin_delegates table in SCHEMA",
    "CREATE TABLE IF NOT EXISTS password_resets (",
    """CREATE TABLE IF NOT EXISTS admin_delegates (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    supervisor_id INTEGER NOT NULL REFERENCES supervisors(id) ON DELETE CASCADE,
    granted_by    INTEGER REFERENCES users(id),
    reason        TEXT DEFAULT '',
    expires_at    TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT DEFAULT (datetime('now')),
    revoked_at    TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS password_resets (""")

# ── 2. Add helper: check if supervisor has active admin delegation ─────────────
patch("2 has_admin_delegation helper",
    "def is_privileged(role):",
    """def has_admin_delegation(conn, supervisor_id):
    \"\"\"True if this supervisor currently holds an active admin delegation.\"\"\"\
    today = datetime.now().isoformat()
    row = conn.execute(\"\"\"
        SELECT id FROM admin_delegates
        WHERE supervisor_id=? AND is_active=1
        AND (expires_at IS NULL OR expires_at > ?)
    \"\"\", (supervisor_id, today)).fetchone()
    return row is not None

def is_privileged(role):""")

# ── 3. In add_attachee: let admin-delegated supervisor pick any supervisor ─────
patch("3 add_attachee respects admin delegation",
    """        if me and me['role'] == 'supervisor' and me.get('supervisor_id'):
            # Supervisor can assign to themselves OR a supervisor they are delegated to cover
            req_sup = d.get('supervisorId')
            my_sup  = me['supervisor_id']
            delegated = get_active_delegations_for(conn, my_sup)
            if req_sup and req_sup in delegated:
                supervisor_id = req_sup   # adding on behalf of delegated supervisor
            else:
                supervisor_id = my_sup    # default: their own""",
    """        if me and me['role'] == 'supervisor' and me.get('supervisor_id'):
            my_sup = me['supervisor_id']
            # Check admin delegation first — grants free supervisor choice
            if has_admin_delegation(conn, my_sup):
                req_sup = d.get('supervisorId')
                supervisor_id = req_sup if req_sup else my_sup
            else:
                # Normal supervisor: own attachees OR delegated supervisor's
                req_sup   = d.get('supervisorId')
                delegated = get_active_delegations_for(conn, my_sup)
                if req_sup and req_sup in delegated:
                    supervisor_id = req_sup
                else:
                    supervisor_id = my_sup""")

# ── 4. Add admin delegation API routes before the STATIC section ──────────────
patch("4 admin delegation API routes",
    "# ─── STATIC ────────────────────────────────────────────────────────────────────",
    """# ─── ADMIN DELEGATION ─────────────────────────────────────────────────────────

@app.route('/api/admin-delegates', methods=['GET'])
@jwt_required()
def get_admin_delegates():
    uid = int(get_jwt_identity())
    with get_db() as conn:
        me = get_current_user(conn, uid)
        if not is_privileged(me['role']):
            return jsonify(error='Forbidden'), 403
        rows = rows_to_list(conn.execute(\"\"\"
            SELECT d.*,
                   s.name  AS supervisor_name,
                   u1.full_name AS admin_name,
                   u2.full_name AS granted_by_name
            FROM admin_delegates d
            JOIN supervisors s  ON s.id  = d.supervisor_id
            JOIN users u1       ON u1.id = d.admin_user_id
            LEFT JOIN users u2  ON u2.id = d.granted_by
            ORDER BY d.created_at DESC
        \"\"\").fetchall())
    return jsonify(rows)

@app.route('/api/admin-delegates', methods=['POST'])
@jwt_required()
def create_admin_delegate():
    uid = int(get_jwt_identity())
    d = request.get_json() or {}
    with get_db() as conn:
        me = get_current_user(conn, uid)
        if not is_privileged(me['role']):
            return jsonify(error='Forbidden — only admin/superadmin can grant add rights'), 403
        sup_id = d.get('supervisorId')
        if not sup_id:
            return jsonify(error='Supervisor ID is required'), 400
        expires_at = d.get('expiresAt') or None
        # Deactivate any existing active admin delegation for this supervisor
        conn.execute(\"\"\"
            UPDATE admin_delegates SET is_active=0, revoked_at=?
            WHERE supervisor_id=? AND is_active=1
        \"\"\", (datetime.now().isoformat(), sup_id))
        cur = conn.execute(\"\"\"
            INSERT INTO admin_delegates
            (admin_user_id, supervisor_id, granted_by, reason, expires_at, is_active)
            VALUES (?,?,?,?,?,1)
        \"\"\", (uid, sup_id, uid, d.get('reason',''), expires_at))
        conn.commit()
        row = row_to_dict(conn.execute(\"\"\"
            SELECT d.*, s.name AS supervisor_name, u.full_name AS admin_name
            FROM admin_delegates d
            JOIN supervisors s ON s.id = d.supervisor_id
            JOIN users u       ON u.id = d.admin_user_id
            WHERE d.id=?
        \"\"\", (cur.lastrowid,)).fetchone())
    return jsonify(row), 201

@app.route('/api/admin-delegates/<int:did>', methods=['DELETE'])
@jwt_required()
def revoke_admin_delegate(did):
    uid = int(get_jwt_identity())
    with get_db() as conn:
        me = get_current_user(conn, uid)
        if not is_privileged(me['role']):
            return jsonify(error='Forbidden'), 403
        conn.execute(\"\"\"
            UPDATE admin_delegates SET is_active=0, revoked_at=? WHERE id=?
        \"\"\", (datetime.now().isoformat(), did))
        conn.commit()
    return jsonify(ok=True)

@app.route('/api/admin-delegates/my', methods=['GET'])
@jwt_required()
def my_admin_delegation():
    \"\"\"For a supervisor: returns their active admin delegation if any.\"\"\"\
    uid = int(get_jwt_identity())
    with get_db() as conn:
        me = get_current_user(conn, uid)
        if not me or me['role'] != 'supervisor' or not me.get('supervisor_id'):
            return jsonify(None)
        today = datetime.now().isoformat()
        row = row_to_dict(conn.execute(\"\"\"
            SELECT d.*, u.full_name AS admin_name
            FROM admin_delegates d
            JOIN users u ON u.id = d.admin_user_id
            WHERE d.supervisor_id=? AND d.is_active=1
            AND (d.expires_at IS NULL OR d.expires_at > ?)
        \"\"\", (me['supervisor_id'], today)).fetchone())
    return jsonify(row)

# ─── STATIC ────────────────────────────────────────────────────────────────────""")

with open(src, "w", encoding="utf-8") as f:
    f.write(code)

print(f"\n{'='*50}")
print(f"  APPLIED : {len(ok)}")
for p in ok:   print(f"    ✓  {p}")
if fail:
    print(f"  SKIPPED : {len(fail)}")
    for p in fail: print(f"    –  {p}")
print(f"{'='*50}")
print("Done. Run: python server.py")
