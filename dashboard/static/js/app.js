const tabs = document.querySelectorAll('.nav-links li');
const sections = document.querySelectorAll('.tab');
const title = document.getElementById('page-title');

function switchTab(id) {
  tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === id));
  sections.forEach(s => s.classList.toggle('active', s.id === 'tab-' + id));
  const names = { overview:'Overview', users:'Users', roles:'Roles', birthdays:'Birthdays', guilds:'Guilds', logs:'Logs' };
  title.textContent = names[id] || 'Rolm';
}
tabs.forEach(t => t.addEventListener('click', () => switchTab(t.dataset.tab)));

// Stats
async function loadStats() {
  const r = await fetch('/api/stats');
  const d = await r.json();
  document.getElementById('stat-users').textContent = d.users;
  document.getElementById('stat-guilds').textContent = d.guilds;
  document.getElementById('stat-members').textContent = d.members;
  document.getElementById('stat-roles').textContent = d.reaction_roles;
}

// Users
async function loadUsers() {
  const q = document.getElementById('user-search').value;
  const g = document.getElementById('guild-filter').value;
  const r = await fetch(`/api/users?q=${encodeURIComponent(q)}&guild_id=${encodeURIComponent(g)}`);
  const d = await r.json();
  const tbody = document.getElementById('users-tbody');
  tbody.innerHTML = d.users.map(u => `<tr>
    <td>${u.user_id}</td>
    <td>${escapeHtml(u.username)}</td>
    <td>${u.birthday}</td>
    <td>${u.tag}</td>
    <td>${u.guilds.join(', ')}</td>
  </tr>`).join('') || '<tr><td colspan="5" style="text-align:center;color:var(--text-muted)">No users found</td></tr>';
}

// Roles
async function loadRoles() {
  const r = await fetch('/api/roles');
  const d = await r.json();
  const tbody = document.getElementById('roles-tbody');
  tbody.innerHTML = Object.entries(d).map(([emoji, rid], i) => `<tr class="editable">
    <td><input data-idx="${i}" data-field="emoji" value="${escapeHtml(emoji)}"></td>
    <td><input data-idx="${i}" data-field="role" value="${rid}"></td>
    <td><button class="btn danger" onclick="this.closest('tr').remove()">Remove</button></td>
  </tr>`).join('');
}

// Birthdays
let allBirthdays = [];
async function loadBirthdays(monthFilter) {
  const r = await fetch('/api/birthdays');
  const d = await r.json();
  allBirthdays = d.birthdays;
  renderBirthdays(monthFilter);
  // Next birthday for overview
  const today = new Date();
  const upcoming = d.birthdays.filter(b => {
    const bd = new Date(today.getFullYear(), b.month-1, b.day);
    if (bd < today) bd.setFullYear(today.getFullYear()+1);
    return bd >= today;
  });
  if (upcoming.length) {
    const b = upcoming[0];
    document.getElementById('next-birthday').innerHTML =
      `<strong>${escapeHtml(b.username)}</strong> on ${b.birthday} (ID: ${b.user_id})`;
  } else {
    document.getElementById('next-birthday').textContent = 'No upcoming birthdays found.';
  }
}
function renderBirthdays(monthFilter) {
  let list = allBirthdays;
  if (monthFilter) list = list.filter(b => b.month == monthFilter);
  const tbody = document.getElementById('birthdays-tbody');
  tbody.innerHTML = list.map(b => `<tr>
    <td>${escapeHtml(b.username)}</td>
    <td>${b.user_id}</td>
    <td>${b.birthday}</td>
    <td>${b.is_today ? '<span style="color:var(--accent-2);font-weight:700">Yes</span>' : 'No'}</td>
  </tr>`).join('') || '<tr><td colspan="4" style="text-align:center;color:var(--text-muted)">No birthdays</td></tr>';
}

// Guilds
async function loadGuilds() {
  const r = await fetch('/api/guilds');
  const d = await r.json();
  const tbody = document.getElementById('guilds-tbody');
  tbody.innerHTML = d.map(g => `<tr>
    <td>${g.id}</td>
    <td>${escapeHtml(g.name)}</td>
    <td>${g.birthday_channel}</td>
    <td>${g.birthday_role}</td>
  </tr>`).join('') || '<tr><td colspan="4" style="text-align:center;color:var(--text-muted)">No guilds configured</td></tr>';
}

// Logs
async function loadLogs() {
  const r = await fetch('/api/logs');
  const d = await r.json();
  document.getElementById('log-viewer').textContent = d.logs.join('\n') || 'No logs yet.';
}

// Events
document.getElementById('user-search').addEventListener('input', loadUsers);
document.getElementById('guild-filter').addEventListener('input', loadUsers);
document.getElementById('refresh-logs').addEventListener('click', loadLogs);
document.getElementById('save-roles').addEventListener('click', async () => {
  const rows = document.querySelectorAll('#roles-tbody tr.editable');
  const payload = {};
  rows.forEach(row => {
    const inputs = row.querySelectorAll('input');
    if (inputs[0].value) payload[inputs[0].value] = inputs[1].value || 0;
  });
  const r = await fetch('/api/roles', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({roles: payload}) });
  const d = await r.json();
  alert(d.ok ? 'Saved!' : 'Error saving');
});
document.getElementById('add-role').addEventListener('click', () => {
  const tbody = document.getElementById('roles-tbody');
  const i = tbody.querySelectorAll('tr').length;
  const tr = document.createElement('tr'); tr.className='editable';
  tr.innerHTML = `<td><input data-idx="${i}" data-field="emoji" value=""></td>
    <td><input data-idx="${i}" data-field="role" value=""></td>
    <td><button class="btn danger" onclick="this.closest('tr').remove()">Remove</button></td>`;
  tbody.appendChild(tr);
});
document.getElementById('filter-birthdays').addEventListener('click', () => {
  const m = document.getElementById('birthday-month').value;
  renderBirthdays(m);
});
document.getElementById('clear-birthday-filter').addEventListener('click', () => {
  document.getElementById('birthday-month').value = '';
  renderBirthdays(null);
});

function escapeHtml(t) {
  if (!t) return '';
  return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// Init
loadStats();
loadUsers();
loadRoles();
loadBirthdays();
loadGuilds();
loadLogs();
