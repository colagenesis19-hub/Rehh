// Area-first workflow navigation for Mini App Input.
// Flow: workflow -> area -> INET -> fill only missing fields.
// Registered technicians can also search an OPEN INET globally when they need
// to take over an order assigned to another technician.

async function searchGlobalOpenInet(action, rawQuery) {
  const input = document.querySelector('#wfGlobalInet');
  const result = document.querySelector('#wfGlobalResult');
  const user = telegramUser();
  const q = String(rawQuery || '').replace(/\D+/g, '');

  if (!user?.id) {
    result.innerHTML = '<div class="empty"><p>❌ Mini App harus dibuka dari Telegram.</p></div>';
    return;
  }
  if (q.length < 6) {
    result.innerHTML = '<div class="empty"><p>Masukkan minimal 6 digit nomor INET.</p></div>';
    input?.focus();
    return;
  }

  result.innerHTML = '<div class="empty"><p>🔄 Mencari order OPEN di seluruh Sheet...</p></div>';
  try {
    const params = new URLSearchParams({ telegram_id: String(user.id), q, force: '1' });
    const response = await fetch(`/api/open-order-search?${params}`, { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.message || `HTTP ${response.status}`);

    result.replaceChildren();
    const orders = data.orders || [];
    if (!orders.length) {
      result.innerHTML = '<div class="empty"><p>INET OPEN tidak ditemukan.</p></div>';
      return;
    }

    orders.forEach(order => {
      const button = document.createElement('button');
      button.className = 'tool-action';
      button.innerHTML = `<div style="min-width:0"><b>🌐 ${esc(order.service_number || '-')}</b><small style="display:block;margin-top:4px;color:#758ba2;line-height:1.45">${esc(order.customer_name || '-')} • 📍 ${esc(order.area || '-')}<br>👷 Assign: ${esc(order.assigned_technician || '-')} • 🎫 ${esc(order.ticket_id || 'MANUAL')}</small></div><span>Pilih ›</span>`;
      button.addEventListener('click', () => {
        const selected = { ...order, area: order.area || 'LAINNYA' };
        state.workflow = { action, order: selected };
        renderWorkflowForm(action, selected);
      });
      result.appendChild(button);
    });
  } catch (error) {
    result.innerHTML = `<div class="empty"><p>❌ ${esc(error.message)}</p></div>`;
  }
}

function renderWorkflowAreas(action, payload) {
  const host = workflowHost();
  const areas = (payload?.areas || []).filter(area => (area.orders || []).length);
  host.innerHTML = `<article class="tool-card">
    <strong>${action.toUpperCase()} • PILIH AREA</strong>
    <small>Pilih area seperti /orderanku, atau cari INET OPEN dari seluruh teknisi.</small>

    <div class="tool-card" style="margin-top:12px;border-color:#27547a;background:linear-gradient(180deg,#0b2238,#091927)">
      <strong>🔎 CARI INET SEMUA TEKNISI</strong>
      <small>Gunakan ini jika ingin mengerjakan order yang di-assign ke teknisi lain. Hanya order berstatus OPEN yang dapat dipilih.</small>
      <div class="search-wrap" style="margin-top:10px">
        <span>⌕</span>
        <input id="wfGlobalInet" inputmode="numeric" autocomplete="off" placeholder="Masukkan nomor INET..." />
      </div>
      <button class="tool-action" id="wfGlobalSearch" type="button"><b>🔎 CARI ORDER OPEN</b><span>Sheet ›</span></button>
      <div id="wfGlobalResult" class="mini-order-list" style="margin-top:8px"></div>
    </div>

    <div id="wfAreaList" class="mini-order-list" style="margin-top:10px"></div>
    <button class="tool-action" id="wfBackHome"><b>‹ Ganti workflow</b><span>${action.toUpperCase()}</span></button>
  </article>`;

  const searchInput = document.querySelector('#wfGlobalInet');
  document.querySelector('#wfGlobalSearch')?.addEventListener('click', () => searchGlobalOpenInet(action, searchInput?.value));
  searchInput?.addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      event.preventDefault();
      searchGlobalOpenInet(action, event.currentTarget.value);
    }
  });

  const list = document.querySelector('#wfAreaList');
  if (!areas.length) {
    list.innerHTML = '<div class="empty"><p>✅ Tidak ada order OPEN milik teknisi ini. Pencarian INET global tetap dapat digunakan.</p></div>';
  } else {
    areas.forEach(area => {
      const button = document.createElement('button');
      button.className = 'tool-action';
      button.innerHTML = `<div><b>📍 ${esc(area.area)}</b><small style="display:block;margin-top:4px;color:#758ba2">🟢 Open: ${fmt(area.open || (area.orders || []).length)} | 🔴 Close: ${fmt(area.close || 0)}${area.update ? ` | 🟡 Update: ${fmt(area.update)}` : ''}</small></div><span>${fmt((area.orders || []).length)} ›</span>`;
      button.addEventListener('click', () => renderWorkflowAreaOrders(action, area));
      list.appendChild(button);
    });
  }
  document.querySelector('#wfBackHome')?.addEventListener('click', renderWorkflowHome);
}

function renderWorkflowAreaOrders(action, area) {
  const rows = (area.orders || []).map(order => ({ ...order, area: area.area }));
  renderWorkflowOrders(action, rows);
  const card = workflowHost().querySelector('.tool-card');
  if (!card) return;

  const heading = card.querySelector('strong');
  if (heading) heading.textContent = `${action.toUpperCase()} • ${area.area}`;
  const small = card.querySelector('small');
  if (small) small.textContent = `${rows.length} order OPEN • pilih INET yang akan dikerjakan`;

  const back = card.querySelector('#wfBack');
  if (back) {
    back.innerHTML = `<b>‹ Kembali ke area</b><span>📍 ${esc(area.area)}</span>`;
    back.replaceWith(back.cloneNode(true));
    card.querySelector('#wfBack')?.addEventListener('click', () => renderWorkflowAreas(action, state.myOpenOrders));
  }
}

// Replace the previous direct workflow -> INET jump.
startWorkflow = async function startWorkflowAreaFirst(action) {
  state.workflow = { action, order: null };
  const host = workflowHost();
  host.innerHTML = '<div class="empty"><p>🔄 Membaca order OPEN dari Google Sheet...</p></div>';
  try {
    const payload = state.myOpenOrders || await fetchMyOpenOrders(false);
    renderWorkflowAreas(action, payload);
  } catch (error) {
    host.innerHTML = `<div class="empty"><p>❌ ${esc(error.message)}</p><button class="tool-action" id="wfBack"><b>Kembali</b><span>‹</span></button></div>`;
    document.querySelector('#wfBack')?.addEventListener('click', renderWorkflowHome);
  }
};

// ticket_bridge.js owns the final form renderer. Wrap it to show operational
// Sheet context such as ONU RX without turning ONU RX into a required field.
const _renderWorkflowFormWithTicket = renderWorkflowForm;
renderWorkflowForm = function renderWorkflowFormWithAreaContext(action, order) {
  _renderWorkflowFormWithTicket(action, order);
  const article = workflowHost()?.querySelector('.tool-card');
  if (!article) return;

  const ticketBlock = article.querySelector('.info-box, .tool-card');
  const context = document.createElement('div');
  context.className = 'info-box';
  context.style.marginTop = '12px';
  context.innerHTML = `<span>📡</span><p><strong style="color:#eef6ff">Data jaringan dari Sheet</strong><br>ONU RX: <b>${esc(order.onu_rx || '-')}</b>${order.package ? ` • Paket: <b>${esc(order.package)}</b>` : ''}${order.rca ? ` • RCA: <b>${esc(order.rca)}</b>` : ''}${order.assigned_technician ? `<br>Assign Sheet: <b>${esc(order.assigned_technician)}</b>` : ''}</p>`;

  if (ticketBlock?.parentNode === article) ticketBlock.insertAdjacentElement('afterend', context);
  else article.insertBefore(context, article.querySelector('form'));
};
