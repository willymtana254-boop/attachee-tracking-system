#!/usr/bin/env python3
"""
patch_index.py  —  Kilifi ICT Attachee System
Applies ALL cumulative frontend fixes to index.html in one shot:

  Fix A  Supervisor role restrictions (hide Add, relabel nav, hide Setup)
  Fix B  Evaluated By auto-selects logged-in supervisor (read-only for supervisors)
  Fix C  Institution manual entry saved automatically to DB
  Fix D  Edit form: supervisor dropdown hidden/locked for supervisor users
  Fix E  Edit form: phone field pre-filled from existing record; clear error shown
  Fix F  After save: DB cache updated AND detail view refreshed reliably
  Fix G  doSaveEdit / doSaveAdd both call resolveInstitutionId() before submitting

Run once:
    python patch_index.py
"""
import os, shutil

src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
if not os.path.exists(src):
    print("ERROR: index.html not found alongside this script.")
    exit(1)

shutil.copy(src, src + ".bak")
print("Backup saved → index.html.bak")

with open(src, encoding="utf-8") as f:
    html = f.read()

ok = []
fail = []

def patch(label, old, new):
    global html
    if old in html:
        html = html.replace(old, new, 1)
        ok.append(label)
    else:
        fail.append(label)

# ═══════════════════════════════════════════════════════════════════════════════
# A — Sidebar IDs so JS can toggle visibility
# ═══════════════════════════════════════════════════════════════════════════════
patch("A1 sidebar-add-btn id",
    'class="sidebar-add-btn" onclick="showPage(\'add-attachee\')"',
    'class="sidebar-add-btn" id="sidebarAddBtn" onclick="showPage(\'add-attachee\')"')

patch("A2 nav attachees label span",
    '&#128100;</span> Attachees',
    '&#128100;</span> <span id="navAttacheesLabel">Attachees</span>')

patch("A3 Setup label id",
    '<div class="sidebar-label">Setup</div>',
    '<div class="sidebar-label" id="setupLabel">Setup</div>')

patch("A4 dashboard add btn id",
    'onclick="showPage(\'add-attachee\')">+ Add Attachee</button>\n          </div>\n        </div>\n        <div class="stats-grid"',
    'id="dashAddBtn" onclick="showPage(\'add-attachee\')">+ Add Attachee</button>\n          </div>\n        </div>\n        <div class="stats-grid"')

patch("A5 list add btn id",
    'onclick="showPage(\'add-attachee\')">+ Add Attachee</button>\n        </div>\n        <div class="filter-bar"',
    'id="listAddBtn" onclick="showPage(\'add-attachee\')">+ Add Attachee</button>\n        </div>\n        <div class="filter-bar"')

patch("A6 page-title id",
    '<div class="page-title">All Attachees</div>',
    '<div class="page-title" id="attacheePageTitle">All Attachees</div>')

# ═══════════════════════════════════════════════════════════════════════════════
# B — Evaluated By: auto-select + lock for supervisors
# ═══════════════════════════════════════════════════════════════════════════════
patch("B evaluated_by field",
    """  const supOpts = DB.supervisors.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
  document.getElementById('evalFormWrap').innerHTML = `
    <div class="form-grid">
      <div class="form-group"><label>Date <span class="req">*</span></label><input type="date" id="e_dt" value="${todayStr()}"></div>
      <div class="form-group"><label>Type</label><select id="e_tp"><option>Weekly</option><option selected>Monthly</option><option>Mid-term</option><option>Final</option><option>Ad-hoc</option></select></div>
      <div class="form-group"><label>Score: <strong id="eScoreVal">70</strong>/100</label>
        <input type="range" id="e_sc" min="0" max="100" value="70" oninput="document.getElementById('eScoreVal').textContent=this.value;autoPerf()"></div>
      <div class="form-group"><label>Performance</label><select id="e_pf"><option>Excellent</option><option selected>Good</option><option>Average</option><option>Poor</option></select></div>
      <div class="form-group"><label>Attendance: <strong id="eAttVal">90</strong>%</label>
        <input type="range" id="e_at" min="0" max="100" value="90" oninput="document.getElementById('eAttVal').textContent=this.value"></div>
      <div class="form-group"><label>Evaluated By</label><select id="e_by"><option value="">— Select —</option>${supOpts}</select></div>
    </div>""",
    """  const _loggedSupId = currentUser.supervisorId || null;
  const _isSup       = currentUser.role === 'supervisor';
  const supOpts = DB.supervisors.map(s =>
    `<option value="${s.id}" ${s.id === _loggedSupId ? 'selected' : ''}>${s.name}</option>`
  ).join('');
  const evalByField = _isSup
    ? (() => {
        const sup = DB.supervisors.find(s => s.id === _loggedSupId);
        return `<div class="form-group">
          <label>Evaluated By</label>
          <input type="text" value="${sup ? sup.name : currentUser.fullName}" disabled
            style="background:#f1f5f9;color:#64748b;cursor:not-allowed">
          <input type="hidden" id="e_by" value="${_loggedSupId || ''}">
        </div>`;
      })()
    : `<div class="form-group"><label>Evaluated By</label>
        <select id="e_by"><option value="">— Select —</option>${supOpts}</select>
       </div>`;
  document.getElementById('evalFormWrap').innerHTML = `
    <div class="form-grid">
      <div class="form-group"><label>Date <span class="req">*</span></label><input type="date" id="e_dt" value="${todayStr()}"></div>
      <div class="form-group"><label>Type</label><select id="e_tp"><option>Weekly</option><option selected>Monthly</option><option>Mid-term</option><option>Final</option><option>Ad-hoc</option></select></div>
      <div class="form-group"><label>Score: <strong id="eScoreVal">70</strong>/100</label>
        <input type="range" id="e_sc" min="0" max="100" value="70" oninput="document.getElementById('eScoreVal').textContent=this.value;autoPerf()"></div>
      <div class="form-group"><label>Performance</label><select id="e_pf"><option>Excellent</option><option selected>Good</option><option>Average</option><option>Poor</option></select></div>
      <div class="form-group"><label>Attendance: <strong id="eAttVal">90</strong>%</label>
        <input type="range" id="e_at" min="0" max="100" value="90" oninput="document.getElementById('eAttVal').textContent=this.value"></div>
      ${evalByField}
    </div>""")

# ═══════════════════════════════════════════════════════════════════════════════
# C — Institution manual entry + resolveInstitutionId helper
# ═══════════════════════════════════════════════════════════════════════════════
patch("C1 institution select with manual option",
    '      <div class="form-group"><label>Institution</label><select id="f_inst"><option value="">— Select —</option>${instOpts}</select></div>',
    '''      <div class="form-group">
        <label>Institution</label>
        <select id="f_inst" onchange="toggleManualInst(this.value)">
          <option value="">— Select —</option>${instOpts}
          <option value="__new__">&#9998; Type manually (not in list)…</option>
        </select>
        <div id="manualInstWrap" style="display:none;margin-top:6px">
          <input id="f_inst_manual" placeholder="Type full institution name…"
            style="border:1.5px dashed var(--blue);"
            oninput="document.getElementById('manualInstNote').style.display=this.value.trim()?'block':'none'">
          <div id="manualInstNote" style="display:none;font-size:11px;color:var(--green);margin-top:3px">
            &#10003; This institution will be saved to the database automatically on submit.
          </div>
        </div>
      </div>''')

patch("C2 resolveInstitutionId helper before getFormVals",
    "function getFormVals(isEdit) {",
    """function toggleManualInst(val) {
  const wrap = document.getElementById('manualInstWrap');
  if (wrap) wrap.style.display = val === '__new__' ? 'block' : 'none';
  if (val !== '__new__') {
    const m = document.getElementById('f_inst_manual');
    if (m) m.value = '';
    const n = document.getElementById('manualInstNote');
    if (n) n.style.display = 'none';
  }
}

async function resolveInstitutionId() {
  const sel = document.getElementById('f_inst');
  if (!sel) return null;
  if (sel.value !== '__new__') return parseInt(sel.value) || null;
  const name = (document.getElementById('f_inst_manual')?.value || '').trim();
  if (!name) {
    showFlash('Please type the institution name or select one from the list.', 'danger');
    return undefined;
  }
  const existing = DB.institutions.find(i => i.name.toLowerCase() === name.toLowerCase());
  if (existing) {
    sel.value = existing.id;
    document.getElementById('manualInstWrap').style.display = 'none';
    return existing.id;
  }
  try {
    const newInst = await apiFetch('/api/institutions', {
      method: 'POST', body: { name, type: '', county: '', contact: '', email: '' }
    });
    DB.institutions.push(newInst);
    sel.innerHTML =
      '<option value="">— Select —</option>' +
      DB.institutions.map(i => `<option value="${i.id}" ${i.id === newInst.id ? 'selected' : ''}>${i.name}</option>`).join('') +
      '<option value="__new__">&#9998; Type manually (not in list)…</option>';
    document.getElementById('manualInstWrap').style.display = 'none';
    showFlash(`Institution "${name}" saved to database.`, 'success');
    return newInst.id;
  } catch (e) {
    showFlash('Could not save institution: ' + e.message, 'danger');
    return undefined;
  }
}

function getFormVals(isEdit) {""")

# ═══════════════════════════════════════════════════════════════════════════════
# D + E + F + G — Edit form: lock supervisor field, fix phone, fix save flow
# ═══════════════════════════════════════════════════════════════════════════════

# D: Hide supervisor select for supervisors in renderAttacheeForm
patch("D lock supervisor field in form",
    "  const deptOpts   = DB.departments.map(d  => `<option value=\"${d.id}\"${deptId === d.id ? ' selected' : ''}>${d.name}</option>`).join('');\n  const instOpts   = DB.institutions.map(i  => `<option value=\"${i.id}\"${instId === i.id ? ' selected' : ''}>${i.name}</option>`).join('');\n  const supOpts    = DB.supervisors.map(s   => `<option value=\"${s.id}\"${supId  === s.id ? ' selected' : ''}>${s.name}</option>`).join('');",
    """  const deptOpts = DB.departments.map(d => `<option value="${d.id}"${deptId === d.id ? ' selected' : ''}>${d.name}</option>`).join('');
  const instOpts = DB.institutions.map(i => `<option value="${i.id}"${instId === i.id ? ' selected' : ''}>${i.name}</option>`).join('');
  const supOpts  = DB.supervisors.map(s => `<option value="${s.id}"${supId  === s.id ? ' selected' : ''}>${s.name}</option>`).join('');
  // For supervisors: show their name as read-only, hidden input carries the value
  const _editIsSup = currentUser.role === 'supervisor';
  const _mySup = _editIsSup ? DB.supervisors.find(s => s.id === currentUser.supervisorId) : null;
  const supervisorField = _editIsSup
    ? `<div class="form-group"><label>Supervisor</label>
        <input type="text" value="${_mySup ? _mySup.name : currentUser.fullName}" disabled
          style="background:#f1f5f9;color:#64748b;cursor:not-allowed">
        <input type="hidden" id="f_sp" value="${currentUser.supervisorId || ''}">
       </div>`
    : `<div class="form-group"><label>Supervisor <span class="req">*</span></label>
        <select id="f_sp"><option value="">— Select —</option>${supOpts}</select>
       </div>`;""")

# Replace the supervisor field line in the form HTML template
patch("D2 use supervisorField in form template",
    '      <div class="form-group"><label>Supervisor <span class="req">*</span></label><select id="f_sp"><option value="">— Select —</option>${supOpts}</select></div>',
    '      ${supervisorField}')

# ═══════════════════════════════════════════════════════════════════════════════
# G — doSaveAdd: resolve institution first
# ═══════════════════════════════════════════════════════════════════════════════
patch("G1 doSaveAdd resolves institution",
    """async function doSaveAdd() {
  const v = getFormVals(false);
  if (!v.firstName || !v.lastName || !v.startDate || !v.endDate) { showFlash('Fill all required fields.', 'danger'); return; }
  if (!v.phone) { showFlash('Phone number is required.', 'danger'); return; }
  try {
    const newA = await apiFetch('/api/attachees', { method: 'POST', body: v });""",
    """async function doSaveAdd() {
  const instId = await resolveInstitutionId();
  if (instId === undefined) return;
  const v = getFormVals(false);
  v.institutionId = instId;
  if (!v.firstName || !v.lastName || !v.startDate || !v.endDate) { showFlash('Fill all required fields.', 'danger'); return; }
  if (!v.phone) { showFlash('Phone number is required.', 'danger'); return; }
  try {
    const newA = await apiFetch('/api/attachees', { method: 'POST', body: v });""")

# ═══════════════════════════════════════════════════════════════════════════════
# F + G — doSaveEdit: resolve institution, fix cache update, refresh detail
# ═══════════════════════════════════════════════════════════════════════════════
patch("FG doSaveEdit full fix",
    """async function doSaveEdit(id) {
  const v = getFormVals(true);
  if (!v.firstName || !v.lastName) { showFlash('Name required.', 'danger'); return; }
  if (!v.phone) { showFlash('Phone number is required.', 'danger'); return; }
  const oldStatus = DB.attachees.find(a => a.id === id)?.status;
  try {
    const updated = await apiFetch(`/api/attachees/${id}`, { method: 'PUT', body: v });
    DB.attachees = DB.attachees.map(a => a.id === id ? updated : a);
    if (v.status !== oldStatus && (v.status === 'Terminated' || v.status === 'Completed')) {
      triggerStatusEmail(id, v.status);
    }
    showFlash('Record updated successfully.');
    openDetail(id);
  } catch (e) { showFlash(e.message, 'danger'); }
}""",
    """async function doSaveEdit(id) {
  // Resolve institution first (handles manual entry if selected)
  const instId = await resolveInstitutionId();
  if (instId === undefined) return;   // manual entry validation failed
  const v = getFormVals(true);
  v.institutionId = instId;           // override with resolved (possibly new) id

  if (!v.firstName || !v.lastName) { showFlash('Name required.', 'danger'); return; }

  // Phone: if blank, try to carry forward the existing value from DB
  // (prevents server rejecting edits when phone was never filled in)
  if (!v.phone) {
    const existing = DB.attachees.find(a => a.id === id);
    const savedPhone = existing?.phone || existing?.phone_number || '';
    if (savedPhone) {
      v.phone = savedPhone;
      // Back-fill the visible field so the user sees it
      const phEl = document.getElementById('f_ph');
      if (phEl) phEl.value = savedPhone;
    } else {
      showFlash('Phone number is required to save changes.', 'danger');
      document.getElementById('f_ph')?.focus();
      return;
    }
  }

  const oldStatus = DB.attachees.find(a => a.id === id)?.status;
  try {
    const updated = await apiFetch(`/api/attachees/${id}`, { method: 'PUT', body: v });

    // ── Update local cache with what the server returned ──────────────────────
    DB.attachees = DB.attachees.map(a => a.id === id ? { ...a, ...updated } : a);

    if (v.status !== oldStatus && (v.status === 'Terminated' || v.status === 'Completed')) {
      triggerStatusEmail(id, v.status);
    }
    showFlash('Record updated successfully.');

    // ── Navigate to detail view; it re-fetches fresh data from server ─────────
    await openDetail(id);
  } catch (e) {
    showFlash(e.message || 'Save failed — please try again.', 'danger');
  }
}""")

# ═══════════════════════════════════════════════════════════════════════════════
# A (JS) — startApp: apply all supervisor UI restrictions
# ═══════════════════════════════════════════════════════════════════════════════
patch("A JS startApp supervisor block",
    """  const adminOn = currentUser.role === 'admin';
  document.getElementById('ndi-users').style.display   = adminOn ? '' : 'none';
  document.getElementById('ndi-export').style.display  = adminOn ? '' : 'none';
  document.getElementById('adminLabel').style.display   = adminOn ? '' : 'none';
  document.getElementById('addSupBtn').style.display   = adminOn ? '' : 'none';""",
    """  const adminOn      = currentUser.role === 'admin';
  const isSupervisor = currentUser.role === 'supervisor';

  document.getElementById('ndi-users').style.display  = adminOn ? '' : 'none';
  document.getElementById('ndi-export').style.display = adminOn ? '' : 'none';
  document.getElementById('adminLabel').style.display  = adminOn ? '' : 'none';
  document.getElementById('addSupBtn').style.display  = adminOn ? '' : 'none';

  if (isSupervisor) {
    const _h = id => { const el = document.getElementById(id); if (el) el.style.display = 'none'; };
    // Relabel nav + page title
    const nl = document.getElementById('navAttacheesLabel');
    if (nl) nl.textContent = 'My Attachees';
    const pt = document.getElementById('attacheePageTitle');
    if (pt) pt.textContent = 'My Attachees';
    // Hide Add Attachee everywhere
    _h('sidebarAddBtn'); _h('dashAddBtn'); _h('listAddBtn');
    // Hide Setup section
    _h('setupLabel'); _h('ndi-institutions'); _h('ndi-departments'); _h('ndi-email-config');
    // Hide Supervisors nav
    _h('ndi-supervisors');
  }""")

# ═══════════════════════════════════════════════════════════════════════════════
# Keep page title correct when renderAttacheeList re-renders
# ═══════════════════════════════════════════════════════════════════════════════
patch("A3 renderAttacheeList retains title",
    "function renderAttacheeList() {",
    """function renderAttacheeList() {
  if (currentUser && currentUser.role === 'supervisor') {
    const t = document.getElementById('attacheePageTitle');
    if (t) t.textContent = 'My Attachees';
  }""")

# ── Write & report ────────────────────────────────────────────────────────────
with open(src, "w", encoding="utf-8") as f:
    f.write(html)

print(f"\n{'='*55}")
print(f"  APPLIED : {len(ok)}")
for p in ok:   print(f"    ✓  {p}")
if fail:
    print(f"  SKIPPED : {len(fail)} (already applied or text changed)")
    for p in fail: print(f"    –  {p}")
print(f"{'='*55}")
print(f"\nDone. Restart server.py and test supervisor edit.\n")