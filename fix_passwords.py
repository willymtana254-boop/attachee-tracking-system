"""
Run this once in the same folder as kilifi.db to fix all login passwords.
Usage:  python fix_passwords.py
"""
import sqlite3, hashlib, os, sys

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kilifi.db')

if not os.path.exists(DB):
    print(f"ERROR: kilifi.db not found at {DB}")
    print("Make sure this script is in the same folder as kilifi.db")
    sys.exit(1)

def h(p):
    return hashlib.sha256(p.encode()).hexdigest()

USERS = [
    (1,  'admin',   'System Administrator',  'admin@ict.local',        h('Admin@1234'), 'admin'),
    (6,  'linus',   'Linus Tinga',           'linustinga254@gmail.com', h('Pass@1234'),  'supervisor'),
    (7,  'betty',   'Betty Mhache',          'b.mhache@kilifi.go.ke',  h('Pass@1234'),  'supervisor'),
    (8,  'laban',   'Laban',                 '',                       h('Pass@1234'),  'supervisor'),
    (9,  'michael', 'Michael Chando',        '',                       h('Pass@1234'),  'supervisor'),
    (10, 'owen',    'Owen Kodi',             '',                       h('Pass@1234'),  'supervisor'),
    (11, 'emily',   'Emily Dama',            '',                       h('Pass@1234'),  'supervisor'),
    (12, 'sharon',  'Sharon Oloo',           '',                       h('Pass@1234'),  'supervisor'),
    (13, 'jemimah', 'Jemimah Idza',          '',                       h('Pass@1234'),  'supervisor'),
    (14, 'bethwel', 'Bethwel Sanga',         '',                       h('Pass@1234'),  'supervisor'),
    (15, 'junior',  'Junior Mbogo',          '',                       h('Pass@1234'),  'supervisor'),
]

conn = sqlite3.connect(DB)
for uid, username, full_name, email, pw_hash, role in USERS:
    exists = conn.execute("SELECT id FROM users WHERE id=?", (uid,)).fetchone()
    if exists:
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (pw_hash, uid))
        print(f"  ✅ Reset password for: {username}")
    else:
        conn.execute(
            "INSERT INTO users(id,username,full_name,email,password_hash,role) VALUES(?,?,?,?,?,?)",
            (uid, username, full_name, email, pw_hash, role)
        )
        print(f"  ➕ Created user: {username}")
conn.commit()
conn.close()

print()
print("Done! Restart server.py and log in with:")
print("  admin   / Admin@1234")
print("  linus   / Pass@1234  (and all other supervisors)")
