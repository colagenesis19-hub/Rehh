// Persistent Mini App input history.
// Drafts are stored in the bot SQLite database so unfinished work can be resumed
// after closing Telegram or switching devices.

const draftState = { items: [], timer: null, pending: null };

function draftTelegramId() {
  return String(telegramUser()?.id || '').trim();
}

function draftKey(action, service) {
  return `${String(action || '').toLowerCase()}:${String(service || '').trim()}`;
}

function buildDraftPayload(action, order, data, status = 'draft') {
  const telegramId = draftTelegramId();
  if (!telegramId || !order?.service_number) return null;
  return {
    telegram_id: telegramId,
    action,
    service_number: order.service_number,
    order,
    data,
    status,
  };
}

async function loadDraftHistory() {
  const telegramId = draftTelegramId();
  if (!telegramId) return [];
  try {
    const response = await fetch(`/api/workflow-drafts?${new URLSearchParams({ telegram_id: telegramId })}`, { cache: 'no-store' });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.message || `HTTP ${response.status}`);
    draftState.items = (payload.items || []).filter(item => item.status !== 'completed');
    return draftState.items;
  } catch (error) {
    console.error('Gagal membaca history input', error);
    draftState.items = [];
    return [];
  }
}

function findDraft(action, service) {
  const key = draftKey(action, service);
  return draftState.items.find(item => draftKey(item.action, item.service_number) === key) || null;
}

async function saveDraft(action, order, data, status = 'draft') {
  const payload = buildDraftPayload(action, order, data, status);
  if (!payload) return;
  draftState.pending = payload;
  try {
    const response = await fetch('/api/workflow-drafts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      keepalive: true,
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.message || `HTTP ${response.status}`);
    const item = { ...payload, updated_at: result.updated_at };
    const key = draftKey(action, order.service_number);
    if (status === 'completed') {
      draftState.items = draftState.items.filter(row => draftKey(row.action, row.service_number) !== key);
    } else {
      draftState.items = [item, ...draftState.items.filter(row => draftKey(row.action, row.service_number) !== key)].slice(0, 30);
    }
    if (draftState.pending && draftKey(draftState.pending.action, draftState.pending.service_number) === key) {
      draftState.pending = null;
    }
  } catch (error) {
    console.error('Gagal menyimpan history input', error);
  }
}

function flushPendingDraft() {
  const payload = draftState.pending;
  if (!payload) return;
  try {
    const body = JSON.stringify(payload);
    if (navigator.sendBeacon) {
      navigator.sendBeacon('/api/workflow-drafts', new Blob([body], { type: 'application/json' }));
    } else {
      fetch('/api/workflow-drafts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        keepalive: true,
      }).catch(() => {});
    }
  } catch (error) {
    console.warn('Gagal flush draft saat Mini App ditutup', error);
  }
}

window.addEventListener('pagehide', flushPendingDraft);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') flushPendingDraft();
});

async function deleteDraft(action, service) {
  const telegramId = draftTelegramId();
  if (!telegramId) return;
  try {
    const params = new URLSearchParams({ telegram_id: telegramId, action, service_number: service });
    const response = await fetch(`/api/workflow-drafts?${params}`, { method: 'DELETE' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const key = draftKey(action, service);
    draftState.items = draftState.items.filter(item => draftKey(item.action, item.service_number) !== key);
    renderWorkflowHome();
    showToast('History input dihapus');
  } catch (error) {
    console.error('Gagal menghapus history input', error);
    showToast('Gagal menghapus history');
  }
}

function draftDateLabel(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('id-ID', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(date);
}

function historyMarkup(items) {
  if (!items.length) return '';
  const rows = items.slice(0, 10).map((item, index) => {
    const order = item.order || {};
    return `<div class="mini-order" style="margin-top:8px">
      <div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start">
        <div style="min-width:0;flex:1">
          <strong>${esc(String(item.action || '').toUpperCase())} • ${esc(item.service_number || '-')}</strong>
          <small>${esc(order.customer_name || '-')} • ${esc(order.area || '-')}<br>🟡 BELUM SELESAI • ${esc(draftDateLabel(item.updated_at))}</small>
        </div>
        <span style="color:#55d9ff;font-size:10px;white-space:nowrap">${index + 1}</span>
      </div>
      <button class="tool-action" type="button" data-resume-draft="${index}"><b>↻ LANJUTKAN</b><span>Resume ›</span></button>
      <button class="tool-action" type="button" data-delete-draft="${index}" style="border-color:#59313a"><b>Hapus history</b><span>✕</span></button>
    </div>`;
  }).join('');
  return `<article class="tool-card" id="workflowHistoryCard" style="border-color:#37506d">
    <strong>🕘 HISTORY INPUT</strong>
    <small>Proses yang belum selesai tersimpan di database bot. Jika VALINS atau data lain belum ada, teknisi dapat menutup Mini App lalu melanjutkan lagi tanpa mengulang dari awal.</small>
    <div style="margin-top:8px">${rows}</div>
  </article>`;
}

function bindHistoryButtons() {
  document.querySelectorAll('[data-resume-draft]').forEach(button => {
    button.addEventListener('click', () => {
      const item = draftState.items[Number(button.dataset.resumeDraft)];
      if (!item) return;
      state.workflow = { action: item.action, order: item.order || {} };
      renderWorkflowForm(item.action, { ...(item.order || {}), __draftData: item.data || {} });
      showToast(`Melanjutkan ${String(item.action || '').toUpperCase()} ${item.service_number}`);
    });
  });
  document.querySelectorAll('[data-delete-draft]').forEach(button => {
    button.addEventListener('click', () => {
      const item = draftState.items[Number(button.dataset.deleteDraft)];
      if (item) deleteDraft(item.action, item.service_number);
    });
  });
}

const _renderWorkflowHomeBeforeHistory = renderWorkflowHome;
renderWorkflowHome = function renderWorkflowHomeWithHistory() {
  _renderWorkflowHomeBeforeHistory();
  loadDraftHistory().then(items => {
    const host = workflowHost();
    if (!host || !items.length || document.querySelector('#workflowHistoryCard')) return;
    host.insertAdjacentHTML('afterbegin', historyMarkup(items));
    bindHistoryButtons();
  });
};

const _renderWorkflowFormBeforeHistory = renderWorkflowForm;
renderWorkflowForm = function renderWorkflowFormWithDrafts(action, order) {
  const inlineDraft = order?.__draftData || null;
  const cleanOrder = { ...(order || {}) };
  delete cleanOrder.__draftData;
  _renderWorkflowFormBeforeHistory(action, cleanOrder);

  const baseData = workflowSeed(cleanOrder);
  const draft = inlineDraft || findDraft(action, cleanOrder.service_number)?.data || {};
  const form = document.querySelector('#wfForm');
  if (!form) return;

  Object.entries(draft).forEach(([key, value]) => {
    const input = form.elements.namedItem(key);
    if (input && String(value || '').trim()) input.value = value;
  });

  const snapshot = () => {
    const data = { ...baseData };
    new FormData(form).forEach((value, key) => { data[key] = String(value || '').trim(); });
    return data;
  };

  // Create the draft immediately, even before the technician types anything.
  const initial = { ...baseData, ...draft };
  draftState.pending = buildDraftPayload(action, cleanOrder, initial, 'draft');
  saveDraft(action, cleanOrder, initial, 'draft');

  const queueSave = () => {
    const data = snapshot();
    draftState.pending = buildDraftPayload(action, cleanOrder, data, 'draft');
    clearTimeout(draftState.timer);
    draftState.timer = setTimeout(() => saveDraft(action, cleanOrder, data, 'draft'), 250);
  };

  form.addEventListener('input', queueSave);
  form.addEventListener('change', () => {
    const data = snapshot();
    draftState.pending = buildDraftPayload(action, cleanOrder, data, 'draft');
    saveDraft(action, cleanOrder, data, 'draft');
  });

  // Clicking BUAT/PROSES only generates the result. The workflow remains a draft
  // until the technician explicitly taps SUDAH DIKERJAKAN on the result page.
  form.addEventListener('submit', () => {
    const data = snapshot();
    draftState.pending = buildDraftPayload(action, cleanOrder, data, 'draft');
    saveDraft(action, cleanOrder, data, 'draft');
  });
};
