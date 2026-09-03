(() => {
  if (window.__reportSupervisorInstalled) return;
  window.__reportSupervisorInstalled = true;

  // First request must not force ALL. The backend decides whether the viewer
  // is a supervisor (blank target => ALL) or a normal technician (own report).
  let selectedNik = '';

  function ensureStyles() {
    if (document.querySelector('#reportSupervisorStyles')) return;
    const style = document.createElement('style');
    style.id = 'reportSupervisorStyles';
    style.textContent = `
      .supervisor-filter{margin:12px 0;border:1px solid #2b4968;background:linear-gradient(180deg,#0d2035,#091827);border-radius:18px;padding:13px}
      .supervisor-filter-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:9px}.supervisor-filter-head strong{font-size:12px}.supervisor-filter-head span{font-size:9px;color:#50d7ff;border:1px solid #275777;border-radius:999px;padding:4px 8px;background:#0b2538}
      .supervisor-filter label{display:block;color:#7f96ad;font-size:9px;margin-bottom:6px}.supervisor-filter select{width:100%;border:1px solid #31506f;background:#081827;color:#eef7ff;border-radius:12px;padding:11px 12px;font-size:12px;outline:none}.supervisor-filter select:focus{border-color:#2e91ff;box-shadow:0 0 0 3px rgba(46,145,255,.12)}
      .supervisor-order-tech{display:block;margin:5px 0 0;color:#55d9ff;font-size:9px;font-weight:800}
    `;
    document.head.appendChild(style);
  }

  function ensureFilter(data) {
    const identity = document.querySelector('#reportIdentity');
    if (!identity) return;
    let box = document.querySelector('#supervisorReportFilter');
    if (!data?.can_filter_nik) {
      box?.remove();
      selectedNik = '';
      return;
    }
    if (!box) {
      box = document.createElement('section');
      box.id = 'supervisorReportFilter';
      box.className = 'supervisor-filter';
      box.innerHTML = `
        <div class="supervisor-filter-head"><strong>👁 MODE ATASAN</strong><span>READ ONLY</span></div>
        <label for="supervisorNikSelect">FILTER NIK TEKNISI</label>
        <select id="supervisorNikSelect"></select>`;
      identity.insertAdjacentElement('afterend', box);
      box.querySelector('select').addEventListener('change', event => {
        selectedNik = String(event.target.value || 'ALL');
        loadReportData();
      });
    }
    const select = box.querySelector('select');
    const technicians = Array.isArray(data.technicians) ? data.technicians : [];
    const options = [{nik:'ALL',name:'SEMUA TEKNISI'}, ...technicians];
    select.innerHTML = options.map(t => `<option value="${esc(t.nik)}">${esc(t.nik)} • ${esc(t.name || '-')}</option>`).join('');
    selectedNik = String(data.selected_nik || selectedNik || 'ALL');
    if ([...select.options].some(o => o.value === selectedNik)) select.value = selectedNik;
    else { selectedNik = 'ALL'; select.value = 'ALL'; }
  }

  function renderSupervisorOrders() {
    const box = document.querySelector('#reportOrders');
    const count = document.querySelector('#reportOrderCount');
    if (!box || !count) return;
    const orders = (reportPayload?.orders || []).filter(reportOrderMatchesPeriod);
    count.textContent = `${orders.length} data`;
    box.replaceChildren();
    if (!orders.length) {
      box.innerHTML = '<div class="empty"><p>Belum ada pekerjaan pada periode ini.</p></div>';
      return;
    }
    orders.forEach((order,index) => {
      const row = document.createElement('div');
      row.className = 'mini-order';
      const tech = reportPayload?.supervisor && order.technician_name
        ? `<span class="supervisor-order-tech">👷 ${esc(order.technician_name)} • NIK ${esc(order.technician_nik || '-')}</span>` : '';
      row.innerHTML = `<strong>${index+1}. 🌐 ${esc(order.service_number||'-')}</strong>${tech}<small style="line-height:1.7">🎫 ${esc(order.ticket_id||'MANUAL')}<br>📍 ${esc(order.area_label||order.sto||'-')}<br>📅 ${esc(order.date_label||'-')}</small>`;
      box.appendChild(row);
    });
  }

  renderPersonalReportOrders = renderSupervisorOrders;

  loadReportData = async function loadSupervisorAwareReportData() {
    const identity = document.querySelector('#reportIdentity');
    const user = telegramUser();
    if (!identity || !user?.id) {
      if (identity) identity.textContent = 'Mini App harus dibuka dari Telegram.';
      return;
    }
    identity.textContent = '🔄 Memuat rekap pekerjaan...';
    try {
      const params = new URLSearchParams({telegram_id:String(user.id)});
      if (selectedNik) params.set('target_nik', selectedNik);
      const response = await fetch(`/api/my-report?${params}`, {cache:'no-store'});
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.message || `HTTP ${response.status}`);
      reportPayload = data;
      ensureFilter(data);
      if (data.can_filter_nik) {
        identity.textContent = data.selected_nik === 'ALL'
          ? `SEMUA TEKNISI • Filter NIK: SEMUA • ${data.all || 0} pekerjaan`
          : `${data.technician.name} • NIK ${data.technician.nik || '-'}${data.technician.sto ? ` • ${data.technician.sto}` : ''}`;
      } else {
        identity.textContent = `${data.technician.name} • NIK ${data.technician.nik||'-'}${data.technician.sto?` • ${data.technician.sto}`:''}`;
      }
      const totals=[data.daily,data.weekly,data.all];
      document.querySelectorAll('#reportSummary strong').forEach((node,i)=>node.textContent=fmt(totals[i]||0));
      renderPersonalTrend();
      renderSupervisorOrders();
    } catch (error) {
      reportPayload = null;
      identity.textContent = `❌ ${error.message}`;
      document.querySelectorAll('#reportSummary strong').forEach(node=>node.textContent='0');
      renderPersonalTrend();
      renderSupervisorOrders();
    }
  };

  ensureStyles();
})();
