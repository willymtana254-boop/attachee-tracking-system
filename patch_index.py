#!/usr/bin/env python3
"""
Run this once in your kilifi-app folder:
  python3 patch_index.py
It will patch index.html in-place with supervisor role restrictions.
"""
import re, shutil, os

src = os.path.join(os.path.dirname(__file__), "index.html")
if not os.path.exists(src):
    print("ERROR: index.html not found in", os.path.dirname(__file__))
    exit(1)

shutil.copy(src, src + ".bak")
print("Backup saved to index.html.bak")

with open(src, encoding="utf-8") as f:
    html = f.read()

patches = [
    # 1. Give sidebar Add button an id
    (
        'class="sidebar-add-btn" onclick="showPage('add-attachee')"',
        'class="sidebar-add-btn" id="sidebarAddBtn" onclick="showPage('add-attachee')"'
    ),
    # 2. Give Attachees nav label a span id
    (
        '&#128100;</span> Attachees',
        '&#128100;</span> <span id="navAttacheesLabel">Attachees</span>'
    ),
    # 3. Give Setup sidebar label an id
    (
        '<div class="sidebar-label">Setup</div>',
        '<div class="sidebar-label" id="setupLabel">Setup</div>'
    ),
    # 4. Give Email Setup nav item an id
    (
        '<button class="sidebar-item" id="ndi-email-config"',
        '<button class="sidebar-item" id="ndi-email-config" style=""'
    ),
    # 5. Give dashboard Add button an id
    (
        'onclick="showPage('add-attachee')">+ Add Attachee</button>\n          </div>\n        </div>\n        <div class="stats-grid"',
        'id="dashAddBtn" onclick="showPage('add-attachee')">+ Add Attachee</button>\n          </div>\n        </div>\n        <div class="stats-grid"'
    ),
    # 6. Give attachees list Add button an id
    (
        'onclick="showPage('add-attachee')">+ Add Attachee</button>\n        </div>\n        <div class="filter-bar"',
        'id="listAddBtn" onclick="showPage('add-attachee')">+ Add Attachee</button>\n        </div>\n        <div class="filter-bar"'
    ),
    # 7. Give page title an id
    (
        '<div class="page-title">All Attachees</div>',
        '<div class="page-title" id="attacheePageTitle">All Attachees</div>'
    ),
]

applied = 0
for old, new in patches:
    if old in html:
        html = html.replace(old, new, 1)
        applied += 1
    else:
        print(f"WARNING: Patch not found: {old[:60]!r}")

# ── MAIN JS PATCH: replace the supervisor UI section in startApp() ──
old_startapp_block = """  const adminOn = currentUser.role === 'admin';
  document.getElementById('ndi-users').style.display   = adminOn ? '' : 'none';
  document.getElementById('ndi-export').style.display  = adminOn ? '' : 'none';
  document.getElementById('adminLabel').style.display   = adminOn ? '' : 'none';
  document.getElementById('addSupBtn').style.display   = adminOn ? '' : 'none';"""

new_startapp_block = """  const adminOn  = currentUser.role === 'admin';
  const isSupervisor = currentUser.role === 'supervisor';

  // Admin-only items
  document.getElementById('ndi-users').style.display   = adminOn ? '' : 'none';
  document.getElementById('ndi-export').style.display  = adminOn ? '' : 'none';
  document.getElementById('adminLabel').style.display   = adminOn ? '' : 'none';
  document.getElementById('addSupBtn').style.display   = adminOn ? '' : 'none';

  // Supervisor restrictions — hide Add Attachee everywhere
  const _hideForSup = el => { if (el) el.style.display = 'none'; };
  if (isSupervisor) {
    // Relabel nav
    const navLbl = document.getElementById('navAttacheesLabel');
    if (navLbl) navLbl.textContent = 'My Attachees';
    const pgTitle = document.getElementById('attacheePageTitle');
    if (pgTitle) pgTitle.textContent = 'My Attachees';

    // Hide Add Attachee buttons (sidebar + pages)
    _hideForSup(document.getElementById('sidebarAddBtn'));
    _hideForSup(document.getElementById('dashAddBtn'));
    _hideForSup(document.getElementById('listAddBtn'));

    // Hide Setup section entirely
    _hideForSup(document.getElementById('setupLabel'));
    _hideForSup(document.getElementById('ndi-institutions'));
    _hideForSup(document.getElementById('ndi-departments'));
    _hideForSup(document.getElementById('ndi-email-config'));

    // Hide Supervisors nav (a supervisor doesn't manage other supervisors)
    _hideForSup(document.getElementById('ndi-supervisors'));
  }"""

if old_startapp_block in html:
    html = html.replace(old_startapp_block, new_startapp_block, 1)
    applied += 1
    print("startApp() block patched OK")
else:
    print("WARNING: startApp() block not found — check indentation")

# ── PATCH renderAttacheeList: page title re-sync on render ──
# When renderAttacheeList() runs it should keep the right title
old_render = "function renderAttacheeList() {"
new_render = """function renderAttacheeList() {
  // Keep page title correct for supervisors
  if (currentUser && currentUser.role === 'supervisor') {
    const t = document.getElementById('attacheePageTitle');
    if (t) t.textContent = 'My Attachees';
  }"""

if old_render in html:
    html = html.replace(old_render, new_render, 1)
    applied += 1
    print("renderAttacheeList() patched OK")

with open(src, "w", encoding="utf-8") as f:
    f.write(html)

print(f"\nDone! Applied {applied} patches to index.html")
print("Open http://localhost:5000 and log in as a supervisor to verify.")
