// Personal report page: completed-work recap + 7-day acquisition trend.

function reportPeriodFilter(orders, mode) {
  if (mode === 'all') return orders;
  const today = new Date();
  const todayKey = today.toISOString().slice(0,10);
  if (mode === 'daily') {
    return orders.filter(order => String(order.raw_day || order.date || '').slice(0,10) === todayKey || String(order.date_label || '').includes(String(today.getDate())));
  }
  const start = new Date(today);
  const day = start.getDay();
  const diff = (day + 2) % 7; // Friday-based operational week.
  start.setDate(start.getDate() - diff);
  start.setHours(0,0,0,0);
  return orders.filter(order => {
    const raw = String(order.raw_day || order.date || '').slice(0,10);
    if (!raw) return true;
    const d = new Date(`${raw}T00:00:00`);
    return d >= start && d <= today;
  });
}

function renderPersonalTrend(trend) {
  const rows = Array.isArray(trend) ? trend : [];
  const max = Math.max(1, ...rows.map(x => Number(x.total || 0)));
  return `<section class="panel" style="margin-top:12px">
    <div class="panel-head"><div><span class="panel-icon">⌁</span><strong>GRAFIK PEROLEHAN</strong></div><span class="panel-meta">7 hari</span></div>
    <div class="trend-chart" style="margin-top:14px">
      ${rows.map(item => {
        const h = Math.max(4, Math.round(Number(item.total || 0) / max * 100));
        return `<div class="trend-col"><span class="trend-value">${fmt(item.total)}</span><div class="trend-bar-wrap"><div class="trend-bar" style="height:${h}%"></div></div><span class="trend-label">${esc(String(item.label || '').slice(0,3).toUpperCase())}</span></div>`;
      }).join('')}
    </div>
  </section>`;
}

function reportOrderCard(order) {
  return `<div class="mini-order">
    <strong>🌐 ${esc(order.service_number || '-')}</strong>
    <small style="line-height:1.65">
      🎫 ${esc(order.ticket_id || 'MANUAL')}<br>
      📍 ${esc(order.area_label || order.sto || '-')}<br>
      📅 ${esc(order.date_label || '-')}
    </small>
  </div>`;
}

function renderPersonalRecap(data) {
  const page = document.querySelector('#reportsPage');
  const oldPanel = page?.querySelector('.panel');
  if (!page || !oldPanel) return;

  const trendHtml = renderPersonalTrend(data.trend || []);
  oldPanel.outerHTML = `${trendHtml}
    <section class="panel" id="personalRecapPanel" style="margin-top:12px">
      <div class="panel-head"><div><span class="panel-icon">✓</span><strong>REKAP SUDAH DIKERJAKAN</strong></div><span id="personalRecapCount" class="panel-meta">${fmt((data.orders || []).length)} data</span></div>
      <div class="segmented" style="margin:12px 0">
        <button class="report-filter active" data-report-period="daily">HARI INI</button>
        <button class="report-filter" data-report-period="weekly">MINGGU</button>
        <button class="report-filter" data-report-period="all">SEMUA</button>
      </div>
      <div id="personalRecapList" class="mini-order-list"></div>
    </section>`;

  const draw = mode => {
    const list = document.querySelector('#personalRecapList');
    const rows = mode === 'daily'
      ? (data.orders || []).filter(o => String(o.date_label || '') === new Intl.DateTimeFormat('id-ID',{day:'numeric',month:'short',year:'numeric'}).format(new Date()).replace('.', ''))
      : mode === 'weekly'
        ? (data.orders || []).slice(0, Number(data.weekly || 0))
        : (data.orders || []);
    document.querySelector('#personalRecapCount').textContent = `${fmt(rows.length)} data`;
    list.innerHTML = rows.length ? rows.map(reportOrderCard).join('') : '<div class="empty"><p>Belum ada pekerjaan pada periode ini.</p></div>';
  };

  document.querySelectorAll('[data-report-period]').forEach(button => button.addEventListener('click', () => {
    document.querySelectorAll('[data-report-period]').forEach(x => x.classList.toggle('active', x === button));
    draw(button.dataset.reportPeriod);
  }));
  draw('daily');
}

loadReportData = async function loadReportDataUpgraded() {
  const candidate = state.me || resolveMeFromPayload();
  const el = document.querySelector('#reportIdentity');
  if (!candidate) {
    el.textContent = 'Data akun Telegram ini belum cocok dengan nama teknisi pada REPORT.';
    return;
  }
  try {
    const data = await fetchTechnician(candidate.key || candidate.nik, 'ALL');
    el.textContent = `${data.name || candidate.name} • NIK ${data.nik || candidate.nik || '-'}`;
    document.querySelectorAll('#reportSummary strong').forEach((x,i) => x.textContent = fmt([data.daily, data.weekly, data.all][i]));
    renderPersonalRecap(data);
  } catch (error) {
    el.textContent = 'Gagal memuat rekapan pekerjaan.';
  }
};
