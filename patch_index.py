#!/usr/bin/env python3
"""
patch_index.py — Admin delegation UI (smart version using regex)
Handles index.html regardless of which previous patches have been applied.
Run once:  python patch_index.py
"""
import os, re, shutil

src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
if not os.path.exists(src):
    print("ERROR: index.html not found."); exit(1)

shutil.copy(src, src + ".bak")
print("Backup → index.html.bak")

with open(src, encoding="utf-8") as f:
    html = f.read()

ok, fail, skip = [], [], []

def patch_exact(label, old, new):
    global html
    if old in html:
        html = html.replace(old, new, 1); ok.append(label)
    else:
        fail.append(label)

def patch_regex(label, pattern, replacement, flags=re.DOTALL):
    global html
    if re.search(pattern, html, flags):
        html = re.sub(pattern, replacement, html, count=1, flags=flags)
        ok.append(label)
    else:
        fail.append(label)

def already_done(label, marker):
    if marker in html:
        skip.append(label); return True
    return False

# ════════════════════════════════════════════════════════════════════════════════
# 1 — Sidebar nav item (exact — already applied)
# ════════════════════════════════════════════════════════════════════════════════
if 'ndi-admin-delegates' in html:
    skip.append("1 admin-delegate nav item (already applied)")
else:
    patch_exact("1 admin-delegate nav item",
        """      <button class="sidebar-item" id="ndi-users" onclick="showPage('users')" style="display:none">
        <span class="sidebar-icon">&#128273;</span> Users
      </button>""",
        """      <button class="sidebar-item" id="ndi-users" onclick="showPage('users')" style="display:none">
        <span class="sidebar-icon">&#128273;</span> Users
      </button>
      <button class="sidebar-item" id="ndi-admin-delegates" onclick="showPage('admin-delegates')" style="display:none">
        <span class="sidebar-icon">&#128101;</span> Delegate Add Rights
        <span class="sidebar-badge" id="adminDelBadge" style="display:none">!</span>
      </button>""")

# ════════════════════════════════════════════════════════════════════════════════
# 2 — Page HTML (already applied check)
# ════════════════════════════════════════════════════════════════════════════════
if 'page-admin-delegates' in html:
    skip.append("2 admin-delegates page HTML (already applied)")
else:
    patch_exact("2 admin-delegates page HTML",
        '      <!-- ── EMAIL CONFIG',
        '''      <!-- ── ADMIN DELEGATION ──────────────────────────────────────────────────── -->
      <div id="page-admin-delegates" class="page" style="display:none">
        <div class="page-header">
          <div class="page-title">&#128101; Delegate Add Rights</div>
          <button class="btn btn-primary btn-sm" onclick="openAdminDelegateForm()">+ Grant Delegation</button>
        </div>
        <div class="card" style="background:#e8f4fd;border:1px solid #90cdf4;margin-bottom:16px">
          <div style="font-size:13.5px;color:#1a365d;line-height:1.7">
            <strong>&#9432; What this does:</strong> When both admins are away, grant a trusted supervisor
            temporary permission to <strong>add new attachees</strong> and assign them to <em>any</em> supervisor —
            the same capability an admin has. The delegation automatically expires on the date you set.
          </div>
        </div>
        <div id="adminDelegateFormArea"></div>
        <div class="card" style="padding:0">
          <div style="padding:14px 16px 8px;font-size:12px;font-weight:700;color:var(--navy);text-transform:uppercase;letter-spacing:.5px">
            Active &amp; Past Delegations
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr><th>#</th><th>Supervisor Granted</th><th>Granted By</th>
                    <th>Reason</th><th>Expires</th><th>Status</th><th>Actions</th></tr>
              </thead>
              <tbody id="adminDelegateBody"></tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- ── EMAIL CONFIG''')

# ════════════════════════════════════════════════════════════════════════════════
# 3 — showPage routing (already applied check)
# ════════════════════════════════════════════════════════════════════════════════
if 'admin-delegates' in html and 'loadAdminDelegates' in html:
    skip.append("3 admin-delegates routing (already applied)")
else:
    patch_exact("3 admin-delegates routing",
        "  else if (page === 'email-config') loadEmailConfig();",
        """  else if (page === 'email-config')     loadEmailConfig();
  else if (page === 'admin-delegates')  { await loadAdminDelegates(); }""")

# ════════════════════════════════════════════════════════════════════════════════
# 4 — startApp(): show ndi-admin-delegates for admin/superadmin
#     Use regex to find the line that shows ndi-users and add after it
# ════════════════════════════════════════════════════════════════════════════════
if already_done("4 show admin-delegate nav", "ndi-admin-delegates').style.display"):
    pass  # already patched
else:
    # Find the line that sets ndi-users display and add our line after it
    # Pattern handles both possible versions
    result = re.sub(
        r"(document\.getElementById\('ndi-users'\)\.style\.display\s*=\s*privileged[^;]+;)",
        r"""\1
  document.getElementById('ndi-admin-delegates').style.display = privileged ? '' : 'none';""",
        html, count=1, flags=re.DOTALL
    )
    if result != html:
        html = result; ok.append("4 show admin-delegate nav")
    else:
        # Try older pattern where adminOn is used instead of privileged
        result2 = re.sub(
            r"(document\.getElementById\('ndi-users'\)\.style\.display\s*=\s*adminOn[^;]+;)",
            r"""\1
  document.getElementById('ndi-admin-delegates').style.display = (currentUser.role === 'admin' || currentUser.role === 'superadmin') ? '' : 'none';""",
            html, count=1, flags=re.DOTALL
        )
        if result2 != html:
            html = result2; ok.append("4 show admin-delegate nav (adminOn variant)")
        else:
            fail.append("4 show admin-delegate nav")

# ════════════════════════════════════════════════════════════════════════════════
# 5 — startApp(): supervisor block — add admin delegation check
#     Strategy: find the isSupervisor block and inject admin delegation check
#     Uses regex to find the closing of the isSupervisor block
# ════════════════════════════════════════════════════════════════════════════════
if already_done("5 supervisor admin delegation check", "_adminDelegation"):
    pass
else:
    # Find the supervisor if-block and append admin delegation check before closing }
    # Look for the apiFetch delegates/my call that's already there and add after it
    result = re.sub(
        r"(apiFetch\('/api/delegates/my'\)\.then\(dels => \{.*?\.catch\(\(\)=>\{\}\);)",
        r"""\1

    // Check admin delegation — grants add-attachee rights
    apiFetch('/api/admin-delegates/my').then(adm => {
      if (adm && adm.is_active) {
        window._adminDelegation = adm;
        ['sidebarAddBtn','dashAddBtn','listAddBtn'].forEach(id => {
          const el = document.getElementById(id);
          if (el) el.style.display = '';
        });
        const exp = adm.expires_at ? ' until ' + adm.expires_at.slice(0,10) : '';
        const b = document.createElement('div');
        b.className = 'flash flash-warning';
        b.style.cssText = 'margin:6px 16px 0;font-size:13px;';
        b.innerHTML = '&#128274; <strong>Admin delegation active' + exp + ':</strong> You can add attachees and assign them to any supervisor. Granted by ' + adm.admin_name + '.';
        document.querySelector('.main-content .container')?.prepend(b);
      } else { window._adminDelegation = null; }
    }).catch(() => { window._adminDelegation = null; });""",
        html, count=1, flags=re.DOTALL
    )
    if result != html:
        html = result; ok.append("5 supervisor admin delegation check")
    else:
        # No existing delegates/my call — inject the whole admin delegation block
        # into the isSupervisor block by finding its closing brace
        result2 = re.sub(
            r"(if \(isSupervisor\) \{.*?)(^\s*\})",
            r"""\1
    // Check admin delegation — grants add-attachee rights
    apiFetch('/api/admin-delegates/my').then(adm => {
      if (adm && adm.is_active) {
        window._adminDelegation = adm;
        ['sidebarAddBtn','dashAddBtn','listAddBtn'].forEach(id => {
          const el = document.getElementById(id); if (el) el.style.display = '';
        });
        const exp = adm.expires_at ? ' until ' + adm.expires_at.slice(0,10) : '';
        const b = document.createElement('div');
        b.className = 'flash flash-warning';
        b.style.cssText = 'margin:6px 16px 0;font-size:13px;';
        b.innerHTML = '&#128274; <strong>Admin delegation active' + exp + ':</strong> You can add attachees and assign them to any supervisor. Granted by ' + adm.admin_name + '.';
        document.querySelector('.main-content .container')?.prepend(b);
      } else { window._adminDelegation = null; }
    }).catch(() => { window._adminDelegation = null; });
\2""",
            html, count=1, flags=re.DOTALL | re.MULTILINE
        )
        if result2 != html:
            html = result2; ok.append("5 supervisor admin delegation check (injected)")
        else:
            fail.append("5 supervisor admin delegation check")

# ════════════════════════════════════════════════════════════════════════════════
# 6 — renderAttacheeForm: admin delegation override for supervisor dropdown
# ════════════════════════════════════════════════════════════════════════════════
if already_done("6 renderAttacheeForm admin delegation override", "_hasAdminDel"):
    pass
else:
    # Find whatever supervisorField definition exists and replace it entirely
    result = re.sub(
        r"(const _editIsSup\s*=.*?)"           # starts after supOpts
        r"(const supervisorField\s*=.*?;)",    # ends after supervisorField = ...;
        r"""const _editIsSup   = currentUser.role === 'supervisor';
  const _hasAdminDel = _editIsSup && window._adminDelegation && window._adminDelegation.is_active;
  const _mySup       = _editIsSup ? DB.supervisors.find(s => s.id === currentUser.supervisorId) : null;
  let supervisorField;
  if (!_editIsSup) {
    supervisorField = `<div class="form-group"><label>Supervisor <span class="req">*</span></label>
      <select id="f_sp"><option value="">— Select —</option>${supOpts}</select></div>`;
  } else if (_hasAdminDel) {
    supervisorField = `<div class="form-group">
      <label>Supervisor <span class="req">*</span>
        <span style="background:#fff3cd;color:#856404;font-size:10px;padding:1px 6px;border-radius:4px;margin-left:6px;font-weight:600">&#128274; Admin delegation active</span>
      </label>
      <select id="f_sp"><option value="">— Select —</option>${supOpts}</select>
    </div>`;
  } else {
    supervisorField = `<div class="form-group"><label>Supervisor</label>
      <input type="text" value="${_mySup ? _mySup.name : currentUser.fullName}" disabled
        style="background:#f1f5f9;color:#64748b;cursor:not-allowed">
      <input type="hidden" id="f_sp" value="${currentUser.supervisorId || ''}">
    </div>`;
  }""",
        html, count=1, flags=re.DOTALL
    )
    if result != html:
        html = result; ok.append("6 renderAttacheeForm admin delegation override")
    else:
        # Simpler fallback: just inject _hasAdminDel logic into whatever supervisorField exists
        result2 = re.sub(
            r"(const _editIsSup\s*=\s*currentUser\.role\s*===\s*'supervisor';)",
            r"""const _editIsSup   = currentUser.role === 'supervisor';
  const _hasAdminDel = _editIsSup && window._adminDelegation && window._adminDelegation.is_active;""",
            html, count=1
        )
        if result2 != html:
            html = result2; ok.append("6 _hasAdminDel injected (partial)")
        else:
            fail.append("6 renderAttacheeForm admin delegation override")

# ════════════════════════════════════════════════════════════════════════════════
# 7 — JS functions (already applied check)
# ════════════════════════════════════════════════════════════════════════════════
if 'loadAdminDelegates' in html:
    skip.append("7 admin delegation JS (already applied)")
else:
    patch_exact("7 admin delegation JS",
        "// ─── BOOT ─────────────────────────────────────────────────────────────────────",
        """// ─── ADMIN DELEGATION ─────────────────────────────────────────────────────────
let DB_adminDelegates = [];

async function loadAdminDelegates() {
  try {
    DB_adminDelegates = await apiFetch('/api/admin-delegates');
    renderAdminDelegates();
  } catch(e) { showFlash(e.message, 'danger'); }
}

function renderAdminDelegates() {
  const today = new Date().toISOString();
  document.getElementById('adminDelegateBody').innerHTML = DB_adminDelegates.map((d, i) => {
    const expired = d.expires_at && d.expires_at < today;
    const active  = d.is_active && !expired;
    const badge   = active
      ? '<span class="badge badge-green">Active</span>'
      : expired ? '<span class="badge badge-amber">Expired</span>'
      : '<span class="badge badge-gray">Revoked</span>';
    return `<tr>
      <td>${i+1}</td>
      <td><strong>${d.supervisor_name}</strong></td>
      <td>${d.admin_name || '—'}</td>
      <td style="font-size:12px;color:var(--gray)">${d.reason || '—'}</td>
      <td style="font-size:12px">${d.expires_at ? d.expires_at.slice(0,10) : '—'}</td>
      <td>${badge}</td>
      <td>${active ? `<button class="btn btn-danger btn-sm" onclick="revokeAdminDelegate(${d.id})">Revoke</button>` : '—'}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="7" class="empty">No delegations yet</td></tr>';
}

function openAdminDelegateForm() {
  const supOpts = DB.supervisors.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
  const defExp  = new Date(Date.now() + 7*86400000).toISOString().slice(0,10);
  document.getElementById('adminDelegateFormArea').innerHTML = `
    <div class="card" style="border-left:4px solid var(--amber);margin-bottom:16px">
      <div class="card-title">&#43; Grant Temporary Add Rights</div>
      <div class="form-grid">
        <div class="form-group">
          <label>Supervisor to Grant Rights To <span class="req">*</span></label>
          <select id="adel_sup"><option value="">— Choose supervisor —</option>${supOpts}</select>
        </div>
        <div class="form-group">
          <label>Expires On <span class="req">*</span></label>
          <input type="date" id="adel_exp" value="${defExp}">
        </div>
        <div class="form-group" style="grid-column:1/-1">
          <label>Reason <span class="req">*</span></label>
          <input id="adel_reason" placeholder="e.g. Admin on annual leave 14–21 July, Linus to handle new intakes">
        </div>
      </div>
      <div style="margin-top:10px;padding:10px 14px;background:#fff3cd;border-radius:6px;font-size:12.5px;color:#856404;line-height:1.6">
        &#9888; The selected supervisor will be able to add attachees and assign them to <em>any</em> supervisor — same as admin.
        Only grant this to a trusted supervisor for a short period. Any previous active delegation for this supervisor is replaced.
      </div>
      <div class="btn-group" style="margin-top:14px">
        <button class="btn btn-warning" onclick="saveAdminDelegate()">&#128274; Grant Add Rights</button>
        <button class="btn btn-ghost" onclick="document.getElementById('adminDelegateFormArea').innerHTML=''">Cancel</button>
      </div>
    </div>`;
  document.getElementById('adminDelegateFormArea').scrollIntoView({ behavior:'smooth' });
}

async function saveAdminDelegate() {
  const supId  = parseInt(document.getElementById('adel_sup').value);
  const exp    = document.getElementById('adel_exp').value;
  const reason = document.getElementById('adel_reason').value.trim();
  if (!supId)  { showFlash('Please select a supervisor.', 'danger'); return; }
  if (!exp)    { showFlash('Please set an expiry date.', 'danger'); return; }
  if (!reason) { showFlash('Please provide a reason.', 'danger'); return; }
  try {
    const result = await apiFetch('/api/admin-delegates', { method:'POST', body:{
      supervisorId: supId, reason, expiresAt: exp + 'T23:59:59'
    }});
    DB_adminDelegates.unshift(result);
    renderAdminDelegates();
    document.getElementById('adminDelegateFormArea').innerHTML = '';
    const supName = DB.supervisors.find(s => s.id === supId)?.name || 'Supervisor';
    showFlash(`&#128274; Add rights granted to ${supName} until ${exp}.`, 'success');
    const badge = document.getElementById('adminDelBadge');
    if (badge) { badge.style.display = ''; badge.textContent = '!'; }
  } catch(e) { showFlash(e.message, 'danger'); }
}

async function revokeAdminDelegate(id) {
  const d = DB_adminDelegates.find(x => x.id === id);
  if (!confirm(`Revoke add rights from ${d?.supervisor_name}? They will immediately lose the ability to add attachees.`)) return;
  try {
    await apiFetch(`/api/admin-delegates/${id}`, { method:'DELETE' });
    await loadAdminDelegates();
    showFlash('Add rights revoked.', 'warning');
  } catch(e) { showFlash(e.message, 'danger'); }
}

// ─── BOOT ─────────────────────────────────────────────────────────────────────""")

# ── Write & report ────────────────────────────────────────────────────────────
with open(src, "w", encoding="utf-8") as f:
    f.write(html)

print(f"\n{'='*55}")
print(f"  APPLIED  : {len(ok)}")
for p in ok:   print(f"    ✓  {p}")
if skip:
    print(f"  SKIPPED  : {len(skip)} (already applied)")
    for p in skip: print(f"    –  {p}")
if fail:
    print(f"  FAILED   : {len(fail)}")
    for p in fail: print(f"    ✗  {p}")
print(f"{'='*55}")
if not fail:
    print("\n✅  All done. Run: python server.py\n")
else:
    print(f"\n⚠  {len(fail)} patch(es) failed — share the output above for help.\n")