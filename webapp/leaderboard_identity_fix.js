// Normalize technician display names and merge conservative name aliases in Mini App.
// Example: "IMAM MAULANA" + "IMAM MAULANA SASMINTHO" are treated as one
// technician when the shorter name is an unambiguous prefix of the longer name.

function technicianDisplayName(value) {
  return String(value || '-')
    .trim()
    .toUpperCase()
    .replace(/^(?:(?:NAME|NAMA)\s*)?[-:=|]+\s*/, '')
    .trim() || '-';
}

function technicianNameKey(value) {
  return technicianDisplayName(value)
    .replace(/^(?:NAME|NAMA)\s*[-:=|]*\s*/, '')
    .replace(/[^A-Z0-9]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ');
}

function mergeTechnicianAliases(rows) {
  const source = (rows || []).map(row => ({
    ...row,
    name: technicianDisplayName(row.name),
    _keys: [row.key || (row.nik && row.nik !== '-' ? `NIK:${row.nik}` : '')].filter(Boolean),
    _nikList: [String(row.nik || '').trim()].filter(nik => nik && nik !== '-'),
  }));

  const consumed = new Set();
  const merged = [];

  for (let i = 0; i < source.length; i += 1) {
    if (consumed.has(i)) continue;
    const base = source[i];
    const baseKey = technicianNameKey(base.name);
    const baseTokens = baseKey.split(' ').filter(Boolean);
    const cluster = [i];

    // Only merge when one name is clearly the same two-or-more-word prefix.
    // Requiring an unambiguous match avoids combining unrelated technicians.
    if (baseTokens.length >= 2) {
      for (let j = i + 1; j < source.length; j += 1) {
        if (consumed.has(j)) continue;
        const otherKey = technicianNameKey(source[j].name);
        const otherTokens = otherKey.split(' ').filter(Boolean);
        if (otherTokens.length < 2) continue;
        const samePrefix = baseKey === otherKey || baseKey.startsWith(`${otherKey} `) || otherKey.startsWith(`${baseKey} `);
        if (samePrefix) cluster.push(j);
      }
    }

    cluster.forEach(index => consumed.add(index));
    const members = cluster.map(index => source[index]);
    const canonical = members.slice().sort((a, b) => technicianNameKey(b.name).length - technicianNameKey(a.name).length)[0];
    const keys = [...new Set(members.flatMap(item => item._keys || []))];
    const niks = [...new Set(members.flatMap(item => item._nikList || []))];

    merged.push({
      ...canonical,
      name: technicianDisplayName(canonical.name),
      total: members.reduce((sum, item) => sum + Number(item.total || 0), 0),
      nik: niks[0] || canonical.nik || '-',
      _keys: keys,
      _nikList: niks,
    });
  }

  return merged.sort((a, b) => Number(b.total || 0) - Number(a.total || 0) || technicianNameKey(a.name).localeCompare(technicianNameKey(b.name)));
}

function normalizeDashboardTechnicians() {
  if (!state?.payload) return;
  state.payload.leaderboard = mergeTechnicianAliases(state.payload.leaderboard || []);
  const rows = state.payload.leaderboard;
  const total = rows.reduce((sum, item) => sum + Number(item.total || 0), 0);
  if (state.payload.summary) {
    state.payload.summary.total_close = total;
    state.payload.summary.active_technicians = rows.length;
    state.payload.summary.average_close = rows.length ? Math.round((total / rows.length) * 10) / 10 : 0;
  }
}

const _loadDashboardBeforeIdentityFix = loadDashboard;
loadDashboard = async function loadDashboardWithIdentityFix() {
  await _loadDashboardBeforeIdentityFix();
  normalizeDashboardTechnicians();
  render();
};

// Override leaderboard renderer so a merged alias opens all historical rows.
renderLeaderboard = function renderLeaderboardMerged() {
  const list = document.querySelector('#leaderboard');
  const empty = document.querySelector('#emptyState');
  const tpl = document.querySelector('#leaderTemplate');
  const rows = selectedRows();
  list.replaceChildren();
  document.querySelector('#resultCount').textContent = `${rows.length} teknisi`;
  empty.classList.toggle('hidden', rows.length > 0);
  rows.slice(0, 12).forEach((item, index) => {
    const node = tpl.content.cloneNode(true);
    const btn = node.querySelector('.leader-row');
    node.querySelector('.rank').textContent = String(index + 1);
    node.querySelector('.leader-name').textContent = technicianDisplayName(item.name);
    node.querySelector('.leader-meta').textContent = `${item.nik || '-'} • ${item.area_label || item.sto || 'SEMUA'}`;
    node.querySelector('.leader-score').textContent = fmt(item.total);
    btn.addEventListener('click', () => openMergedTechnician(item));
    list.appendChild(node);
  });
};

renderRecentActivity = function renderRecentActivityUppercase() {
  const c = document.querySelector('#recentActivity');
  const rows = state.payload?.leaderboard || [];
  c.replaceChildren();
  if (!rows.length) {
    c.innerHTML = '<div class="empty"><p>Belum ada aktivitas pada filter ini.</p></div>';
    return;
  }
  rows.slice(0, 3).forEach((item, i) => {
    const r = document.createElement('div');
    r.className = 'activity-item';
    r.innerHTML = `<span class="activity-bullet">${i === 0 ? '✓' : '↗'}</span><div><strong>${esc(technicianDisplayName(item.name))}</strong><small>${fmt(item.total)} close • ${esc(item.area_label || item.sto || 'SEMUA')}</small></div>`;
    c.appendChild(r);
  });
};

async function openMergedTechnician(item) {
  try {
    const keys = item._keys?.length ? item._keys : [item.key || item.nik];
    const details = await Promise.all(keys.filter(Boolean).map(key => fetchTechnician(key, state.area)));
    const ordersByServicePeriod = new Map();
    details.forEach(detail => (detail.orders || []).forEach(order => {
      const k = `${order.service_number || ''}|${order.date_label || ''}`;
      if (!ordersByServicePeriod.has(k)) ordersByServicePeriod.set(k, order);
    }));
    const orders = [...ordersByServicePeriod.values()];
    document.querySelector('#detailName').textContent = technicianDisplayName(item.name);
    document.querySelector('#detailNik').textContent = `NIK ${(item._nikList || [item.nik]).filter(nik => nik && nik !== '-').join(' • ') || '-'}`;
    document.querySelector('#detailDaily').textContent = fmt(details.reduce((sum, d) => sum + Number(d.daily || 0), 0));
    document.querySelector('#detailWeekly').textContent = fmt(details.reduce((sum, d) => sum + Number(d.weekly || 0), 0));
    document.querySelector('#detailAll').textContent = fmt(orders.length);
    document.querySelector('#detailCount').textContent = `${orders.length} data`;
    const c = document.querySelector('#detailOrders');
    c.replaceChildren();
    orders.forEach(o => {
      const r = document.createElement('div');
      r.className = 'order-row';
      r.innerHTML = `<div><strong>${esc(o.service_number || '-')}</strong><small>${esc(o.ticket_id || 'MANUAL')} • ${esc(o.area_label || o.sto || '-')}</small></div><span class="order-date">${esc(o.date_label || '-')}</span>`;
      c.appendChild(r);
    });
    document.querySelector('#detailPanel').classList.remove('hidden');
  } catch (error) {
    showToast('Detail teknisi gagal dimuat');
  }
}

// Apply uppercase consistently to the personal identity labels as well.
const _setWelcomeBeforeIdentityFix = setWelcome;
setWelcome = function setWelcomeUppercase() {
  _setWelcomeBeforeIdentityFix();
  const el = document.querySelector('#welcomeName');
  if (el) el.textContent = technicianDisplayName(el.textContent);
};

// This enhancement is loaded dynamically after app.js. The first dashboard request
// may already have completed, so normalize the existing payload immediately too.
if (state?.payload) {
  normalizeDashboardTechnicians();
  render();
}
