// Detailed CONFIG / REPORT / STO history from the bot database.

function workflowHistoryKindLabel(kind) {
  return String(kind || '').toUpperCase();
}

function historyTelegramCodeBlock(text) {
  const clean = String(text || '').replace(/```/g, "''' ").trim();
  return `\`\`\`\n${clean}\n\`\`\``;
}

async function fetchWorkflowHistory(serviceNumber) {
  const user = telegramUser();
  if (!user?.id) throw new Error('Mini App harus dibuka dari Telegram.');
  const params = new URLSearchParams({ telegram_id: String(user.id), service_number: String(serviceNumber || '') });
  const response = await fetch(`/api/workflow-history?${params}`, { cache: 'no-store' });
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.message || `HTTP ${response.status}`);
  return payload.items || [];
}

async function fetchWorkflowDraftsForService(serviceNumber) {
  const user = telegramUser();
  if (!user?.id) throw new Error('Mini App harus dibuka dari Telegram.');
  const params = new URLSearchParams({ telegram_id: String(user.id) });
  const response = await fetch(`/api/workflow-drafts?${params}`, { cache: 'no-store' });
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.message || `HTTP ${response.status}`);
  const wanted = String(serviceNumber || '').trim();
  return (payload.items || []).filter(item => String(item.service_number || '').trim() === wanted && String(item.status || 'draft').toLowerCase() !== 'completed');
}

async function saveWorkflowHistoryContent(historyId, content) {
  const user = telegramUser();
  if (!user?.id) throw new Error('Mini App harus dibuka dari Telegram.');
  const response = await fetch('/api/workflow-history', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ telegram_id: String(user.id), history_id: historyId, content }),
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.message || `HTTP ${response.status}`);
}

function closeWorkflowHistoryPanel() {
  document.querySelector('#workflowHistoryDetail')?.remove();
}

function historyEditorBlock(item) {
  return `<article class="tool-card" style="margin-top:10px">
    <div style="display:flex;align-items:center;justify-content:space-between;gap:10px">
      <strong>${esc(workflowHistoryKindLabel(item.kind))}</strong>
      <span style="font-size:9px;color:#7890aa">${esc(String(item.created_at || '').replace('T',' ').replace('Z',''))}</span>
    </div>
    <textarea data-history-editor="${item.id}" spellcheck="false" style="width:100%;min-height:220px;margin-top:10px;border:1px solid #294968;border-radius:12px;background:#06111f;color:#dceaff;padding:12px;font:10px/1.55 monospace;box-sizing:border-box;resize:vertical">${esc(item.content || '')}</textarea>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
      <button class="tool-action" type="button" data-copy-history="${item.id}"><b>SALIN CODE</b><span>⧉</span></button>
      <button class="tool-action" type="button" data-save-history="${item.id}"><b>SIMPAN EDIT</b><span>✓</span></button>
    </div>
  </article>`;
}

function draftHistoryBlock(item, index) {
  const action = String(item.action || 'lengkap').toUpperCase();
  const order = item.order || {};
  const data = item.data || {};
  const updated = String(item.updated_at || '').replace('T', ' ').replace('Z', '');
  const filled = Object.values(data).filter(value => String(value || '').trim()).length;
  return `<article class="tool-card" style="margin-top:10px;border-color:#80641e;background:linear-gradient(180deg,#241d0b,#12140d)">
    <div style="display:flex;align-items:center;justify-content:space-between;gap:10px">
      <strong style="color:#ffd768">🟡 DRAFT ${esc(action)}</strong>
      <span style="font-size:9px;color:#a89257">${esc(updated || '-')}</span>
    </div>
    <small style="margin-top:7px;color:#c6b988;line-height:1.6">Belum dikerjakan / belum ditandai selesai.<br>${esc(order.customer_name || '-')} • ${esc(order.area || order.sto || '-')} • ${filled} field tersimpan.</small>
    <button class="tool-action" type="button" data-resume-history-draft="${index}" style="border-color:#80641e"><b>↻ LANJUTKAN DRAFT</b><span>Input ›</span></button>
  </article>`;
}

async function openWorkflowHistory(serviceNumber) {
  closeWorkflowHistoryPanel();
  const panel = document.createElement('section');
  panel.id = 'workflowHistoryDetail';
  panel.className = 'detail-panel';
  panel.innerHTML = `<div class="detail-backdrop" data-close-workflow-history></div><article class="detail-sheet" style="overflow:auto"><div class="detail-handle"></div><button class="close-detail" data-close-workflow-history>✕</button><p class="section-kicker">HISTORY WORKFLOW</p><h2>${esc(serviceNumber)}</h2><div id="workflowHistoryBody"><div class="empty"><p>🔄 Memuat DRAFT / CONFIG / REPORT / STO...</p></div></div></article>`;
  document.body.appendChild(panel);
  panel.querySelectorAll('[data-close-workflow-history]').forEach(button => button.addEventListener('click', closeWorkflowHistoryPanel));

  try {
    const [items, drafts] = await Promise.all([
      fetchWorkflowHistory(serviceNumber),
      fetchWorkflowDraftsForService(serviceNumber),
    ]);
    const body = panel.querySelector('#workflowHistoryBody');

    if (!items.length && !drafts.length) {
      body.innerHTML = '<div class="empty"><p>Belum ada draft atau history CONFIG / REPORT / STO untuk INET ini.</p></div>';
      return;
    }

    const draftMarkup = drafts.length
      ? `<div class="info-box" style="border-color:#80641e"><span>🟡</span><p><strong style="color:#ffd768">BELUM DIKERJAKAN</strong><br>INET ini masih memiliki draft workflow. Data tersimpan dan bisa dilanjutkan.</p></div>${drafts.map(draftHistoryBlock).join('')}`
      : '';

    const byKind = new Set(items.map(item => workflowHistoryKindLabel(item.kind)));
    const lengkap = ['CONFIG','REPORT','STO'].every(kind => byKind.has(kind));
    const completedMarkup = items.length
      ? `${lengkap ? '<div class="info-box"><span>✅</span><p><strong style="color:#eef6ff">/LENGKAP</strong><br>History /CONFIG + /REPORT + /STO tersedia untuk INET ini.</p></div>' : ''}${items.map(historyEditorBlock).join('')}`
      : '<div class="info-box"><span>ℹ</span><p>Belum ada output CONFIG / REPORT / STO yang selesai untuk INET ini.</p></div>';

    body.innerHTML = `${draftMarkup}${completedMarkup}`;

    body.querySelectorAll('[data-resume-history-draft]').forEach(button => {
      button.addEventListener('click', () => {
        const item = drafts[Number(button.dataset.resumeHistoryDraft)];
        if (!item) return;
        closeWorkflowHistoryPanel();
        openPage('inputPage');
        const order = { ...(item.order || {}), __draftData: item.data || {} };
        renderWorkflowForm(String(item.action || 'lengkap').toLowerCase(), order);
        showToast(`Melanjutkan ${String(item.action || '').toUpperCase()} ${item.service_number}`);
      });
    });

    body.querySelectorAll('[data-copy-history]').forEach(button => {
      button.addEventListener('click', () => {
        const editor = body.querySelector(`[data-history-editor="${button.dataset.copyHistory}"]`);
        copyText(historyTelegramCodeBlock(editor?.value || ''), 'Code tersalin');
      });
    });
    body.querySelectorAll('[data-save-history]').forEach(button => {
      button.addEventListener('click', async () => {
        const editor = body.querySelector(`[data-history-editor="${button.dataset.saveHistory}"]`);
        try {
          await saveWorkflowHistoryContent(button.dataset.saveHistory, editor?.value || '');
          showToast('History berhasil diedit');
        } catch (error) {
          showToast('Gagal menyimpan edit');
        }
      });
    });
  } catch (error) {
    panel.querySelector('#workflowHistoryBody').innerHTML = `<div class="empty"><p>❌ ${esc(error.message)}</p></div>`;
  }
}

// Enhance rows on the personal report page after every render.
const _renderPersonalReportOrdersWithHistory = renderPersonalReportOrders;
renderPersonalReportOrders = function renderPersonalReportOrdersHistoryEnabled() {
  _renderPersonalReportOrdersWithHistory();
  const box = document.querySelector('#reportOrders');
  if (!box) return;
  [...box.querySelectorAll('.mini-order')].forEach((row, index) => {
    const orders = (reportPayload?.orders || []).filter(reportOrderMatchesPeriod);
    const order = orders[index];
    if (!order) return;
    row.style.cursor = 'pointer';
    row.insertAdjacentHTML('beforeend', '<button class="tool-action" type="button"><b>HISTORY / EDIT</b><span>›</span></button>');
    row.querySelector('.tool-action')?.addEventListener('click', () => openWorkflowHistory(order.service_number));
  });
};
