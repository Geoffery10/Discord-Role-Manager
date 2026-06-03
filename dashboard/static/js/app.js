const tabs = document.querySelectorAll('.nav-links li');
const sections = document.querySelectorAll('.tab');
const title = document.getElementById('page-title');

function switchTab(id) {
  tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === id));
  sections.forEach(s => s.classList.toggle('active', s.id === 'tab-' + id));
  const names = { overview:'Overview', users:'Users', roles:'Roles', birthdays:'Birthdays', guilds:'Guilds', logs:'Logs' };
  title.textContent = names[id] || 'Rolm';
  
  // Refresh data when switching to a tab
  if (id === 'users') {
    loadUsers();
  } else if (id === 'roles') {
    loadRoles();
  } else if (id === 'birthdays') {
    loadBirthdays();
  } else if (id === 'guilds') {
    loadGuilds();
  } else if (id === 'logs') {
    loadLogs();
  }
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
let allUsers = [];
let userSort = { key: 'birthday', dir: 'asc' };
let birthdayFilterState = "both"; // "both", "has", "none"

function sortUsers(list) {
  const k = userSort.key;
  const d = userSort.dir;
  return list.slice().sort((a, b) => {
    let av = a[k], bv = b[k];
    if (k === 'user_id' || k === 'tag') { av = Number(av); bv = Number(bv); }
    if (av < bv) return d === 'asc' ? -1 : 1;
    if (av > bv) return d === 'asc' ? 1 : -1;
    return 0;
  });
}

function setUserSort(key) {
  const headers = document.querySelectorAll('#users-table th.sortable');
  headers.forEach(th => th.classList.remove('asc','desc'));
  if (userSort.key === key) {
    userSort.dir = userSort.dir === 'asc' ? 'desc' : 'asc';
  } else {
    userSort.key = key;
    userSort.dir = 'asc';
  }
  const active = document.querySelector(`#users-table th[data-sort="${key}"]`);
  if (active) active.classList.add(userSort.dir);
  renderUsers();
}

function renderUsers() {
  // Apply birthday filter
  let filteredUsers = allUsers;
  if (birthdayFilterState === "has") {
    filteredUsers = allUsers.filter(u => u.birthday !== "00-00");
  } else if (birthdayFilterState === "none") {
    filteredUsers = allUsers.filter(u => u.birthday === "00-00");
  }
  
  let list = sortUsers(filteredUsers);
  const tbody = document.getElementById('users-tbody');
  tbody.innerHTML = list.map(u => `<tr>
    <td>${u.user_id}</td>
    <td>${escapeHtml(u.username)}</td>
    <td>${u.birthday}</td>
    <td>${u.tag}</td>
    <td>${u.guilds.join(', ')}</td>
  </tr>`).join('') || '<tr><td colspan="5" style="text-align:center;color:var(--text-muted)">No users found</td></tr>';
}

async function loadUsers() {
  const q = document.getElementById('user-search').value;
  const g = document.getElementById('guild-filter').value;
  const r = await fetch(`/api/users?q=${encodeURIComponent(q)}&guild_id=${encodeURIComponent(g)}`);
  const d = await r.json();
  allUsers = d.users;
  renderUsers();
}

// Roles
let allRoles = [];
let roleSort = { key: 'role_name', dir: 'asc' };
let selectedRoleGuild = '';
let roleGuildsList = [];

function sortRoles(list) {
  const k = roleSort.key;
  const d = roleSort.dir;
  return list.slice().sort((a, b) => {
    let av = a[k] || '';
    let bv = b[k] || '';
    if (k === 'role_id') { av = Number(av); bv = Number(bv); }
    if (av < bv) return d === 'asc' ? -1 : 1;
    if (av > bv) return d === 'asc' ? 1 : -1;
    return 0;
  });
}

function setRoleSort(key) {
  const headers = document.querySelectorAll('#roles-table th.sortable');
  headers.forEach(th => th.classList.remove('asc','desc'));
  if (roleSort.key === key) {
    roleSort.dir = roleSort.dir === 'asc' ? 'desc' : 'asc';
  } else {
    roleSort.key = key;
    roleSort.dir = 'asc';
  }
  const active = document.querySelector(`#roles-table th[data-sort="${key}"]`);
  if (active) active.classList.add(roleSort.dir);
  renderRoles();
}

function extractEmojiId(name) {
  if (!name) return null;
  const m = name.match(/:(\d+)$/);
  return m ? m[1] : null;
}

function renderRoles() {
  let list = sortRoles(allRoles);
  const tbody = document.getElementById('roles-tbody');
  tbody.innerHTML = list.map((item, i) => {
    const eid = extractEmojiId(item.emoji);
    const defaultChar = DEFAULT_EMOJI_MAP[item.emoji];
    let emojiCell;
    if (eid) {
      const ext = item.emoji.startsWith('a:') ? 'gif' : 'png';
      const imgUrl = `https://cdn.discordapp.com/emojis/${eid}.${ext}`;
      emojiCell = `<img class="emoji-img" src="${imgUrl}" alt="${escapeHtml(item.emoji)}" onerror="this.classList.add('fail');this.nextElementSibling.style.display=''"><span class="emoji-placeholder" style="display:none">⚠️</span>`;
    } else if (defaultChar) {
      emojiCell = `<span class="emoji-placeholder" style="font-size:24px">${defaultChar}</span>`;
    } else {
      emojiCell = `<span class="emoji-placeholder">⚠️</span>`;
    }
    const name = item.role_name ? escapeHtml(item.role_name) : '';
    const nameClass = item.role_name ? 'role-name' : 'role-name missing';
    return `<tr class="editable">
    <td>${emojiCell}</td>
    <td class="${nameClass}">${name || '—'}</td>
    <td><input data-idx="${i}" data-field="emoji" value="${escapeHtml(item.emoji)}"></td>
    <td><input data-idx="${i}" data-field="role" value="${item.role_id}"></td>
    <td><button class="btn danger" onclick="this.closest('tr').remove()">Remove</button></td>
  </tr>`;
  }).join('');
}

async function loadRoleGuilds() {
  const r = await fetch('/api/guilds');
  const d = await r.json();
  roleGuildsList = d;
  const sel = document.getElementById('role-guild-select');
  sel.innerHTML = '<option value="" disabled selected>Select Guild</option>';
  d.forEach(g => {
    const opt = document.createElement('option');
    opt.value = g.id;
    opt.textContent = `${g.name} (${g.id})`;
    sel.appendChild(opt);
  });
}

async function onRoleGuildChange() {
  const sel = document.getElementById('role-guild-select');
  selectedRoleGuild = sel.value;
  if (!selectedRoleGuild) return;
  const r = await fetch(`/api/roles?guild_id=${encodeURIComponent(selectedRoleGuild)}`);
  const d = await r.json();
  allRoles = d.roles || [];
  renderRoles();
}

async function loadRoles() {
  await loadRoleGuilds();
  const sel = document.getElementById('role-guild-select');
  if (roleGuildsList.length) {
    sel.value = roleGuildsList[0].id;
    selectedRoleGuild = roleGuildsList[0].id;
    await onRoleGuildChange();
  } else {
    allRoles = [];
    renderRoles();
  }
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
let birthdaySort = { key: 'days_till', dir: 'asc' };

function sortBirthdays(list) {
  const k = birthdaySort.key;
  const d = birthdaySort.dir;
  return list.slice().sort((a, b) => {
    let av = a[k], bv = b[k];
    if (k === 'days_till' || k === 'user_id') { av = Number(av); bv = Number(bv); }
    if (av < bv) return d === 'asc' ? -1 : 1;
    if (av > bv) return d === 'asc' ? 1 : -1;
    return 0;
  });
}

function setSort(key) {
  const headers = document.querySelectorAll('#birthdays-table th.sortable');
  headers.forEach(th => th.classList.remove('asc','desc'));
  if (birthdaySort.key === key) {
    birthdaySort.dir = birthdaySort.dir === 'asc' ? 'desc' : 'asc';
  } else {
    birthdaySort.key = key;
    birthdaySort.dir = 'asc';
  }
  const active = document.querySelector(`#birthdays-table th[data-sort="${key}"]`);
  if (active) active.classList.add(birthdaySort.dir);
  renderBirthdays(document.getElementById('birthday-month').value || null);
}

function renderBirthdays(monthFilter) {
  let list = allBirthdays;
  if (monthFilter) list = list.filter(b => b.month == monthFilter);
  list = sortBirthdays(list);
  const tbody = document.getElementById('birthdays-tbody');
  tbody.innerHTML = list.map(b => `<tr>
    <td>${escapeHtml(b.username)}</td>
    <td>${b.user_id}</td>
    <td>${b.birthday}</td>
    <td>${b.days_till === 0 ? '<span style="color:var(--accent-2);font-weight:700">Today!</span>' : b.days_till}</td>
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

// Tristate checkbox for birthday filter
const birthdayFilter = document.getElementById('birthday-filter');
birthdayFilter.addEventListener('click', function() {
  // Cycle through states: unchecked (both) -> checked (has) -> indeterminate (none) -> unchecked (both)
  if (!this.checked && !this.indeterminate) {
    // Unchecked to checked (has)
    this.checked = true;
    this.indeterminate = false;
    birthdayFilterState = "has";
  } else if (this.checked && !this.indeterminate) {
    // Checked to indeterminate (none)
    this.checked = true;
    this.indeterminate = true;
    birthdayFilterState = "none";
  } else {
    // Indeterminate to unchecked (both)
    this.checked = false;
    this.indeterminate = false;
    birthdayFilterState = "both";
  }
  renderUsers();
});

document.getElementById('refresh-logs').addEventListener('click', loadLogs);
document.getElementById('role-guild-select').addEventListener('change', onRoleGuildChange);
document.getElementById('refresh-role-names').addEventListener('click', async () => {
  const r = await fetch('/api/roles/refresh', { method: 'POST' });
  const d = await r.json();
  if (d.ok) {
    await onRoleGuildChange();
  } else {
    alert('Failed to refresh role names');
  }
});
document.getElementById('save-roles').addEventListener('click', async () => {
  const rows = document.querySelectorAll('#roles-tbody tr.editable');
  const payload = {};
  rows.forEach(row => {
    const inputs = row.querySelectorAll('input');
    if (inputs[0].value) payload[inputs[0].value] = inputs[1].value || 0;
  });
  const gid = selectedRoleGuild || '254779349352448001';
  const r = await fetch('/api/roles', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({roles: {[gid]: payload}})
  });
  const d = await r.json();
  alert(d.ok ? 'Saved!' : 'Error saving');
  if (d.ok) await onRoleGuildChange();
});
document.getElementById('add-role').addEventListener('click', () => {
  const tbody = document.getElementById('roles-tbody');
  const i = tbody.querySelectorAll('tr').length;
  const tr = document.createElement('tr'); tr.className='editable';
  tr.innerHTML = `<td></td>
    <td></td>
    <td><input data-idx="${i}" data-field="emoji" value=""></td>
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

// Sortable headers
document.querySelectorAll('#birthdays-table th.sortable').forEach(th => {
  th.addEventListener('click', () => setSort(th.dataset.sort));
});
document.querySelectorAll('#users-table th.sortable').forEach(th => {
  th.addEventListener('click', () => setUserSort(th.dataset.sort));
});
document.querySelectorAll('#roles-table th.sortable').forEach(th => {
  th.addEventListener('click', () => setRoleSort(th.dataset.sort));
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

// Initialize birthday filter state
birthdayFilter.checked = false;
birthdayFilter.indeterminate = false;
