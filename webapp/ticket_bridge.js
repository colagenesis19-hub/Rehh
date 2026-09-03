// Ticket helper layer for Mini App input workflow.
// Keeps Mini App aligned with chatbot/Sheet ticket priority:
// INSERA TODAY -> TIKET -> MANUAL.

const MINIAPP_EMPTY_TICKETS = new Set(['', '-', 'MANUAL', 'N/A', 'NA', 'NONE']);
const MINIAPP_DRAFT_LIMIT = 20;

function miniappTicket(value) {
  const raw = String(value || '').trim();
  return MINIAPP_EMPTY_TICKETS.has(raw.toUpperCase()) ? 'MANUAL' : raw;
}

function miniappIsManualTicket(value) {
  return miniappTicket(value) === 'MANUAL';
}

function draftStorageKey() {
  const telegramId = telegramUser()?.id || 'anonymous';
  return `kerja-bot-input-drafts:${telegramId}`;
}

function readWorkflowDrafts() {
  try {
    const raw = localStorage.getItem(draftStorageKey());
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    console.warn('Gagal membaca draft Mini App', error);
    return [];
  }
}

function writeWorkflowDrafts(items) {
  try {
    localStorage.setItem(draftStorageKey(), JSON.stringify(items.slice(0, MINIAPP_DRAFT_LIMIT)));
  } catch (error) {
    console.warn('Gagal menyimpan draft Mini App', error);
  }
}

function draftId(action, serviceNumber) {
  return `${String(action || '').toLowerCase()}:${String(serviceNumber || '').trim()}`;
}

function getWorkflowDraft(action, serviceNumber) {
  const id = draftId(action, serviceNumber);
  return readWorkflowDrafts().find(item => item.id === id) || null;
}

function saveWorkflowDraft(action, order, data) {
  const serviceNumber = String(order?.service_number || data?.service_number || '').trim();
  if (!serviceNumber) return;
  const id = draftId(action, serviceNumber);
  const now = new Date().toISOString();
  const cleanData = {};
  Object.entries(data || {}).forEach(([key, value]) => {
    const text = String(value ?? '').trim();
    if (text) cleanData[key] = text;
  });
  const item = {
    id,
    action,
    service_number: serviceNumber,
    customer_name: String(order?.customer_name || data?.customer_name || '').trim(),
    address: String(order?.address || data?.address || '').trim(),
    area: String(order?.area || '').trim(),
    order: { ...(order || {}) },
    data: cleanData,
    updated_at: now,
  };
  const others = readWorkflowDrafts().filter(existing => existing.id !== id);
  writeWorkflowDrafts([item, ...others]);
}

function removeWorkflowDraft(action, serviceNumber) {
  const id = draftId(action, serviceNumber);
  writeWorkflowDrafts(readWorkflowDrafts().filter(item => item.id !== id));
}

function draftTimeLabel(value) {
  try {
    return new Intl.DateTimeFormat('id-ID', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value));
  } catch (_) {
    return '-';
  }
}

function renderDraftHistory() {
  const host = workflowHost();
  if (!host || document.querySelector('#wfDraftHistory')) return;
  const drafts = readWorkflowDrafts();
  if (!drafts.length) return;

  const card = document.createElement('article');
  card.className = 'tool-card';
  card.id = 'wfDraftHistory';
  card.style.borderColor = '#5a4721';
  card.style.background = 'linear-gradient(180deg,#1a1b20,#0d1824)';
  card.innerHTML = `
    <strong>🕘 HISTORY / PROSES TERTUNDA</strong>
    <small>Input yang belum selesai tersimpan otomatis. Pilih untuk melanjutkan dari data terakhir.</small>
    <div id="wfDraftList" class="mini-order-list" style="margin-top:10px"></div>`;

  const list = card.querySelector('#wfDraftList');
  drafts.forEach(item => {
    const row = document.createElement('div');
    row.className = 'mini-order';
    row.innerHTML = `
      <div style="display:flex;justify-content:space-between;gap:8px;align-items:flex-start">
        <div style="min-width:0;flex:1">
          <strong>${esc(String(item.action || '').toUpperCase())} • ${esc(item.service_number || '-')}</strong>
          <small>${esc(item.customer_name || '-')} ${item.area ? `• ${esc(item.area)}` : ''}<br>Terakhir: ${esc(draftTimeLabel(item.updated_at))}</small>
        </div>
        <button type="button" data-draft-remove="${esc(item.id)}" style="border:0;background:transparent;color:#ff7b85;font-size:12px;padding:4px">✕</button>
      </div>
      <button class="tool-action" type="button" data-draft-resume="${esc(item.id)}"><b>LANJUTKAN</b><span>›</span></button>`;
    list.appendChild(row);
  });
  host.prepend(card);

  card.querySelectorAll('[data-draft-resume]').forEach(button => {
    button.addEventListener('click', () => {
      const item = readWorkflowDrafts().find(draft => draft.id === button.dataset.draftResume);
      if (!item) return;
      renderWorkflowForm(item.action, item.order || { service_number: item.service_number });
      showToast(`Melanjutkan ${String(item.action || '').toUpperCase()} ${item.service_number}`);
    });
  });
  card.querySelectorAll('[data-draft-remove]').forEach(button => {
    button.addEventListener('click', event => {
      event.stopPropagation();
      const draftsNow = readWorkflowDrafts().filter(draft => draft.id !== button.dataset.draftRemove);
      writeWorkflowDrafts(draftsNow);
      renderWorkflowHome();
      showToast('History dihapus');
    });
  });
}

// Override the original seed so a missing ticket is represented as MANUAL,
// rather than being treated as another field the technician must type.
workflowSeed = function workflowSeedWithTicketFallback(order) {
  return {
    ticket_id: miniappTicket(order.ticket_id),
    service_number: order.service_number || '',
    customer_name: order.customer_name || '',
    address: order.address || '',
    customer_phone: order.customer_phone || '',
    voip_number: order.voip_number || '',
    old_sn: order.old_sn || '',
    new_sn: order.new_sn || '',
    ont_type: order.ont_type || '',
    sto: order.sto || state.myOpenOrders?.technician?.sto || '',
    valins_id: order.valins_id || '',
    result: order.result || '',
    config_description: order.config_description || '',
    report_description: order.report_description || '',
  };
};

function findFreshOpenOrder(serviceNumber) {
  const target = String(serviceNumber || '').trim();
  for (const area of state.myOpenOrders?.areas || []) {
    for (const order of area.orders || []) {
      if (String(order.service_number || '').trim() === target) {
        return { ...order, area: area.area };
      }
    }
  }
  return null;
}

async function refreshWorkflowTicket(action, serviceNumber) {
  showToast('Mengecek tiket terbaru...');
  try {
    await fetchMyOpenOrders(true);
    const fresh = findFreshOpenOrder(serviceNumber);
    if (!fresh) {
      showToast('Order tidak ditemukan pada Sheet terbaru');
      return;
    }
    state.workflow = { action, order: fresh };
    if (miniappIsManualTicket(fresh.ticket_id)) {
      renderWorkflowForm(action, fresh);
      showToast('Tiket masih MANUAL');
      return;
    }
    renderWorkflowForm(action, fresh);
    showToast(`Tiket ditemukan: ${fresh.ticket_id}`);
  } catch (error) {
    console.error('Gagal refresh tiket Mini App', error);
    showToast('Gagal mengecek tiket terbaru');
  }
}

function ticketHelperMarkup(order) {
  if (!miniappIsManualTicket(order.ticket_id)) {
    return `<div class="info-box" style="margin-top:12px"><span>🎫</span><p><strong style="color:#eef6ff">Tiket: ${esc(order.ticket_id)}</strong><br>Prioritas sumber: INSERA TODAY → TIKET → MANUAL.</p></div>`;
  }
  return `
    <div class="tool-card" style="margin-top:12px;border-color:#6b5425;background:linear-gradient(180deg,#191b20,#101820)">
      <strong>⚠ TIKET MASIH MANUAL</strong>
      <small>INSERA TODAY dan TIKET pada Order Sheet belum berisi tiket. Gunakan helper di bawah, lalu cek ulang Sheet.</small>
      <button class="tool-action" type="button" id="wfReqOpenTicket"><b>🎫 #REQOPENTIKET</b><span>Salin ›</span></button>
      <button class="tool-action" type="button" id="wfInfoTicket"><b>🔎 /infotiket</b><span>Salin ›</span></button>
      <button class="tool-action" type="button" id="wfRefreshTicket"><b>↻ CEK TIKET TERBARU</b><span>Sheet ›</span></button>
    </div>`;
}

function reqOpenTicketText(order) {
  const sto = String(order.sto || state.myOpenOrders?.technician?.sto || '').trim().toUpperCase() || '-';
  const inet = String(order.service_number || '').trim() || '-';
  return `#REQOPENTIKET\nSTO: ${sto}\n\nNOMER INET:\n${inet}\n\nmoban create tiket`;
}

function waGreeting() {
  const hour = new Date().getHours();
  if (hour < 11) return 'Selamat pagi';
  if (hour < 15) return 'Selamat siang';
  if (hour < 18) return 'Selamat sore';
  return 'Selamat malam';
}

function whatsappCustomerText(order) {
  const technician = String(state.myOpenOrders?.technician?.name || telegramName() || 'Teknisi').trim();
  const customer = String(order.customer_name || 'Bapak/Ibu').trim();
  const inet = String(order.service_number || '-').trim();
  const address = String(order.address || '-').trim();
  const phone = String(order.customer_phone || '-').trim();
  return `${waGreeting()} Bapak/Ibu ${customer}.\n\nPerkenalkan, saya ${technician}, teknisi resmi IndiHome.\n\nMohon maaf mengganggu waktunya. Saya mendapat penugasan dari pihak Telkom untuk melakukan penggantian ONT/Modem pada layanan Bapak/Ibu sebagai bagian dari pembaruan perangkat jaringan.\n\nNo. Internet: ${inet}\nAlamat: ${address}\nNo. HP: ${phone}\n\nDengan penggantian perangkat ini, Bapak/Ibu akan mendapatkan beberapa benefit:\n• Jaringan lebih stabil\n• Perangkat kompatibel dengan jaringan WiFi 5 GHz\n• Biaya langganan tetap, tidak berubah\n• Tidak ada biaya pemasangan / GRATIS\n\nSeluruh proses penggantian dilakukan oleh teknisi resmi dan tidak mengubah paket maupun biaya langganan Bapak/Ibu.\n\nApabila Bapak/Ibu berkenan, mohon konfirmasi waktu yang sesuai agar saya dapat melakukan kunjungan.\n\nJika terdapat kendala atau membutuhkan konfirmasi terkait layanan, Bapak/Ibu dapat menghubungi layanan resmi Telkom melalui 188.\n\nTerima kasih atas perhatian dan kerja sama Bapak/Ibu. 🙏🏼`;
}

function whatsappHelperMarkup(order) {
  return `<div class="tool-card" style="margin-top:12px;border-color:#255c4b;background:linear-gradient(180deg,#0d2925,#0b1c26)">
    <strong>💬 FORMAT WHATSAPP PELANGGAN</strong>
    <small>Data nama, INET, alamat, nomor HP, dan nama teknisi diambil otomatis dari order/akun teknisi.</small>
    <button class="tool-action" type="button" id="wfCopyWhatsapp"><b>💬 SALIN FORMAT WA</b><span>Salin ›</span></button>
  </div>`;
}

function bindTicketHelpers(action, order) {
  document.querySelector('#wfReqOpenTicket')?.addEventListener('click', async () => {
    await copyText(reqOpenTicketText(order), '#REQOPENTIKET lengkap tersalin');
  });
  document.querySelector('#wfInfoTicket')?.addEventListener('click', async () => {
    await copyText(`/infotiket ${order.service_number}`, '/infotiket tersalin');
  });
  document.querySelector('#wfRefreshTicket')?.addEventListener('click', () => {
    refreshWorkflowTicket(action, order.service_number);
  });
  document.querySelector('#wfCopyWhatsapp')?.addEventListener('click', async () => {
    await copyText(whatsappCustomerText(order), 'Format WhatsApp pelanggan tersalin');
  });
}

// Extend the existing form while retaining exactly the same CONFIG/REPORT/STO
// field requirements and output generator as the normal Mini App workflow.
renderWorkflowForm = function renderWorkflowFormWithTicketTools(action, order) {
  state.workflow = { action, order };
  const draft = getWorkflowDraft(action, order.service_number);
  const data = { ...workflowSeed(order), ...(draft?.data || {}) };
  const required = WF_REQUIRED[action];
  const missing = required.filter(k => !String(data[k] || '').trim());
  const host = workflowHost();

  // Create/update draft as soon as the technician opens an order so the
  // process is still recoverable even if Telegram closes before any typing.
  saveWorkflowDraft(action, order, data);

  const known = required
    .filter(k => String(data[k] || '').trim())
    .map(k => `<div style="display:flex;justify-content:space-between;gap:10px;padding:7px 0;border-bottom:1px solid rgba(87,119,153,.13);font-size:10px"><span style="color:#8298b2">${WF_LABELS[k]}</span><strong style="text-align:right">${esc(data[k])}</strong></div>`)
    .join('');

  const fields = missing
    .map(k => `<label style="display:block;margin:11px 0"><span style="display:block;color:#9cb0c5;font-size:10px;margin-bottom:5px">${WF_LABELS[k]}</span><input name="${k}" required value="${esc(data[k] || '')}" placeholder="Isi ${WF_LABELS[k]}${['valins_id','voip_number'].includes(k) ? ' atau -' : ''}" style="width:100%;border:1px solid #2a496b;border-radius:12px;background:#081727;color:#fff;padding:12px;outline:none" /></label>`)
    .join('');

  host.innerHTML = `<article class="tool-card">
    <strong>${action.toUpperCase()} • ${esc(order.service_number)}</strong>
    <small>${esc(order.customer_name || '-')} • ${esc(order.address || '-')}</small>
    <div class="info-box" style="margin-top:12px;border-color:#5a4721"><span>🕘</span><p><strong style="color:#eef6ff">Tersimpan otomatis</strong><br>Kalau proses ditutup atau pindah halaman, lanjutkan dari HISTORY / PROSES TERTUNDA di menu Input.</p></div>
    ${whatsappHelperMarkup(order)}
    ${ticketHelperMarkup(order)}
    ${known ? `<div style="margin-top:12px">${known}</div>` : ''}
    <form id="wfForm" style="margin-top:10px">
      ${fields || '<div class="info-box"><span>✓</span><p>Semua data yang dibutuhkan sudah tersedia.</p></div>'}
      <button class="tool-action" type="submit"><b>BUAT ${action.toUpperCase()}</b><span>Proses ›</span></button>
    </form>
    <button class="tool-action" id="wfBackOrders"><b>‹ Pilih order lain</b><span>🌐</span></button>
  </article>`;

  bindTicketHelpers(action, order);
  const form = document.querySelector('#wfForm');
  form?.querySelectorAll('input').forEach(input => {
    input.addEventListener('input', () => {
      const formData = new FormData(form);
      missing.forEach(k => {
        const current = String(formData.get(k) || '').trim();
        if (current) data[k] = current;
        else delete data[k];
      });
      data.ticket_id = miniappTicket(data.ticket_id);
      saveWorkflowDraft(action, order, data);
    });
  });

  document.querySelector('#wfBackOrders').addEventListener('click', () => startWorkflow(action));
  form.addEventListener('submit', event => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    missing.forEach(k => {
      data[k] = String(formData.get(k) || '').trim() || '-';
    });
    // Never let an empty/placeholder Sheet ticket disappear from the output.
    data.ticket_id = miniappTicket(data.ticket_id);
    removeWorkflowDraft(action, order.service_number);
    renderWorkflowResult(action, order, data);
  });
};

// Add draft/history cards to the normal Input home without changing the
// existing LENGKAP / CONFIG / REPORT / STO buttons.
const _renderWorkflowHomeWithNoDrafts = renderWorkflowHome;
renderWorkflowHome = function renderWorkflowHomeWithDraftHistory() {
  _renderWorkflowHomeWithNoDrafts();
  renderDraftHistory();
};
