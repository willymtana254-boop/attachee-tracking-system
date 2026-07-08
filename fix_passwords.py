"""
Fix / reset all login passwords for Kilifi ICT Attachee Tracking System.
Run this once in the same folder as kilifi.db:

    python fix_passwords.py

The server (server.py) hashes passwords as:
    SHA-256( "kilifi2026" + plaintext_password )

The old fix script used plain SHA-256 which is why logins were failing.
This script uses the correct salted hash to match the server.
"""

import sqlite3, hashlib, os, sys

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kilifi.db')

if not os.path.exists(DB):
    print(f"\n❌  kilifi.db not found at:\n    {DB}")
    print("Make sure this script is in the same folder as kilifi.db\n")
    sys.exit(1)

# ── This MUST match hash_pass() in server.py ──────────────────────────────────
def h(password):
    """Salted SHA-256 — same algorithm the server uses."""
    return hashlib.sha256(f'kilifi2026{password}'.encode()).hexdigest()

USERS = [
    # (id,  username,   full_name,               email,                      password,       role,         supervisor_id, must_change_password)
    (1,  'admin',   'System Administrator', 'admin@ict.local',          'Admin@1234',   'admin',      None, 0),
    (6,  'linus',   'Linus Tinga',          'linustinga254@gmail.com',  'Pass@1234',    'supervisor', 6,    1),
    (7,  'betty',   'Betty Mhache',         'b.mhache@kilifi.go.ke',    'Pass@1234',    'supervisor', 7,    1),
    (8,  'laban',   'Laban',                '',                         'Pass@1234',    'supervisor', 8,    1),
    (9,  'michael', 'Michael Chando',       '',                         'Pass@1234',    'supervisor', 9,    1),
    (10, 'owen',    'Owen Kodi',            '',                         'Pass@1234',    'supervisor', 10,   1),
    (11, 'emily',   'Emily Dama',           '',                         'Pass@1234',    'supervisor', 11,   1),
    (12, 'sharon',  'Sharon Oloo',          '',                         'Pass@1234',    'supervisor', 12,   1),
    (13, 'jemimah', 'Jemimah Idza',        '',                         'Pass@1234',    'supervisor', 13,   1),
    (14, 'bethwel', 'Bethwel Sanga',       '',                         'Pass@1234',    'supervisor', 14,   1),
    (15, 'junior',  'Junior Mbogo',         '',                         'Pass@1234',    'supervisor', 15,   1),
]

conn = sqlite3.connect(DB)

# Ensure the new columns exist (safe to run on old databases)
try:
    conn.execute("ALTER TABLE users ADD COLUMN supervisor_id INTEGER")
    print("  ℹ️  Added supervisor_id column")
except Exception:
    pass  # column already exists

try:
    conn.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0")
    print("  ℹ️  Added must_change_password column")
except Exception:
    pass  # column already exists

print("\nFixing passwords (using salted SHA-256 to match server.py)...\n")

for row in USERS:
    uid, username, full_name, email, password, role, sup_id, must_change = row
    pw_hash = h(password)
    exists = conn.execute("SELECT id FROM users WHERE id=?", (uid,)).fetchone()
    if exists:
        conn.execute(
            "UPDATE users SET username=?, full_name=?, email=?, password_hash=?, "
            "role=?, supervisor_id=?, must_change_password=? WHERE id=?",
            (username, full_name, email, pw_hash, role, sup_id, must_change, uid)
        )
        print(f"  ✅  Reset: {username:12s}  →  password: {password}")
    else:
        conn.execute(
            "INSERT INTO users(id,username,full_name,email,password_hash,role,supervisor_id,must_change_password) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (uid, username, full_name, email, pw_hash, role, sup_id, must_change)
        )
        print(f"  ➕  Created: {username:10s}  →  password: {password}")

conn.commit()
conn.close()

print("""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅  Done!  Restart server.py then log in with:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Username   Password      Role
  ─────────  ────────────  ──────────
  admin      Admin@1234    Admin
  linus      Pass@1234     Supervisor  (must change on first login)
  betty      Pass@1234     Supervisor  (must change on first login)
  laban      Pass@1234     Supervisor  (must change on first login)
  michael    Pass@1234     Supervisor  (must change on first login)
  owen       Pass@1234     Supervisor  (must change on first login)
  emily      Pass@1234     Supervisor  (must change on first login)
  sharon     Pass@1234     Supervisor  (must change on first login)
  jemimah    Pass@1234     Supervisor  (must change on first login)
  bethwel    Pass@1234     Supervisor  (must change on first login)
  junior     Pass@1234     Supervisor  (must change on first login)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOTE: Supervisor accounts will be prompted to set
a new personal password on their first login.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")