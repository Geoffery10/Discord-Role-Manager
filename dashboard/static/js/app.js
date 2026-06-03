const tabs = document.querySelectorAll('.nav-links li');
const sections = document.querySelectorAll('.tab');
const title = document.getElementById('page-title');

function switchTab(id) {
  tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === id));
  sections.forEach(s => s.classList.toggle('active', s.id === 'tab-' + id));
  const names = { overview:'Overview', users:'Users', roles:'Roles', birthdays:'Birthdays', guilds:'Guilds', logs:'Logs' };
  title.textContent = names[id] || 'Rolm';

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
  } else if (id === 'overview') {
    loadStats();
  }
}
tabs.forEach(t => t.addEventListener('click', () => switchTab(t.dataset.tab)));

// Stats
async function loadStats() {
  const r = await fetch('/api/stats');
  const d = await r.json();
  document.getElementById('stat-birthdays').textContent = d.birthdays;
  document.getElementById('stat-users').textContent = d.users;
  document.getElementById('stat-members').textContent = d.members;
  document.getElementById('stat-guilds').textContent = d.guilds;
  document.getElementById('stat-roles').textContent = d.reaction_roles;
  loadNextBirthday();
  loadMeta();
}

async function loadMeta() {
  try {
    const r = await fetch('/api/meta');
    const d = await r.json();
    document.getElementById('meta-commit').textContent = d.commit || '—';
    document.getElementById('meta-ip').textContent = d.ip || '—';
  } catch (e) {
    console.error('Meta fetch failed:', e);
  }
}

// Load next birthday for overview panel
async function loadNextBirthday() {
  const r = await fetch('/api/birthdays');
  const d = await r.json();
  updateNextBirthdayPanel(d.birthdays);
}

// Users
let allUsers = [];
let userSort = { key: 'birthday', dir: 'asc' };
let birthdayFilterState = 0;

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
  let filteredUsers = allUsers;
  if (birthdayFilterState === 1) {
    filteredUsers = allUsers.filter(u => u.birthday !== "00-00");
  } else if (birthdayFilterState === 2) {
    filteredUsers = allUsers.filter(u => u.birthday === "00-00");
  }

  let list = sortUsers(filteredUsers);
  const tbody = document.getElementById('users-tbody');
  tbody.innerHTML = list.map(u => `<tr>
    <td>${renderAvatar(u.user_id, u.avatar)}</td>
    <td>${u.user_id}</td>
    <td>${escapeHtml(u.username)}</td>
    <td>${u.birthday}</td>
    <td>${u.tag}</td>
    <td>${u.guilds.join(', ')}</td>
  </tr>`).join('') || '<tr><td colspan="6" style="text-align:center;color:var(--text-muted)">No users found</td></tr>';
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
    await fetch('/api/roles/refresh', { method: 'POST' });
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
  updateNextBirthdayPanel(d.birthdays);
}

function updateNextBirthdayPanel(birthdays) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const upcoming = birthdays.filter(b => {
    const bd = new Date(today.getFullYear(), b.month-1, b.day);
    if (bd < today) bd.setFullYear(today.getFullYear()+1);
    return bd >= today;
  }).sort((a, b) => {
    const dateA = new Date(today.getFullYear(), a.month-1, a.day);
    const dateB = new Date(today.getFullYear(), b.month-1, b.day);
    if (dateA < today) dateA.setFullYear(today.getFullYear()+1);
    if (dateB < today) dateB.setFullYear(today.getFullYear()+1);
    return dateA - dateB;
  });

  const container = document.getElementById('upcoming-birthdays');
  if (upcoming.length) {
    const nextFive = upcoming.slice(0, 5);
    container.innerHTML = '<ul>' + nextFive.map(b => {
      const dateA = new Date(today.getFullYear(), b.month-1, b.day);
      if (dateA < today) dateA.setFullYear(today.getFullYear()+1);
      const diffMs = dateA - today;
      const daysUntil = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
      const daysText = daysUntil === 0
        ? '<span class="today-badge">Today!</span>'
        : `<span class="bday-meta">(${daysUntil} day${daysUntil !== 1 ? 's' : ''})</span>`;
      return `<li>
        <div class="bday-row-left">
          ${renderAvatar(b.user_id, b.avatar)}
          <span class="bday-name">${escapeHtml(b.username)}</span>
          <span class="bday-meta">${b.birthday} ${daysText}</span>
        </div>
        <span class="bday-id">(ID: ${b.user_id})</span>
      </li>`;
    }).join('') + '</ul>';
  } else {
    container.textContent = 'No upcoming birthdays found.';
  }

  renderBirthdayChart(birthdays);
}

function renderBirthdayChart(birthdays) {
  // Count birthdays per month (1-12)
  const monthCounts = Array(12).fill(0);
  birthdays.forEach(b => {
    if (b.month && b.month > 0) {
      monthCounts[b.month - 1]++;
    }
  });

  // Destroy existing chart if it exists
  if (window.birthdayChart instanceof Chart) {
    window.birthdayChart.destroy();
  }

  const ctx = document.getElementById('birthdayChart').getContext('2d');
  window.birthdayChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
      datasets: [{
        label: 'Birthdays',
        data: monthCounts,
        backgroundColor: '#5865F2',
        borderColor: '#5865F2',
        borderWidth: 1,
        borderRadius: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function(context) {
              return context.parsed.y + ' birthday' + (context.parsed.y !== 1 ? 's' : '');
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { color: '#999' }
        },
        y: {
          beginAtZero: true,
          ticks: { precision: 0, color: '#999' },
          grid: { color: 'rgba(255,255,255,0.05)' }
        }
      }
    }
  });
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
    <td>${renderAvatar(b.user_id, b.avatar)}</td>
    <td>${escapeHtml(b.username)}</td>
    <td>${b.user_id}</td>
    <td>${b.birthday}</td>
    <td>${b.days_till === 0 ? '<span style="color:var(--accent-2);font-weight:700">Today!</span>' : b.days_till}</td>
  </tr>`).join('') || '<tr><td colspan="5" style="text-align:center;color:var(--text-muted)">No birthdays</td></tr>';
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
  birthdayFilterState = (birthdayFilterState + 1) % 3;
  if (birthdayFilterState === 0) {
    this.checked = false;
    this.indeterminate = false;
  } else if (birthdayFilterState === 1) {
    this.checked = true;
    this.indeterminate = false;
  } else {
    this.checked = false;
    this.indeterminate = true;
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

function renderAvatar(userId, avatar) {
  if (avatar) {
    const isAnimated = avatar.startsWith('a_');
    const ext = isAnimated ? 'gif' : 'png';
    const url = `https://cdn.discordapp.com/avatars/${userId}/${avatar}.${ext}?size=64`;
    return `<img class="pfp" src="${url}" alt="" onerror="this.classList.add('fail');this.style.display='none'">`;
  }
  const defaultIndex = Number(BigInt(userId) >> 22n) % 6;
  const defaultUrl = `https://cdn.discordapp.com/embed/avatars/${defaultIndex}.png`;
  return `<img class="pfp" src="${defaultUrl}" alt="">`;
}

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
birthdayFilterState = 0;
birthdayFilter.checked = false;
birthdayFilter.indeterminate = false;
