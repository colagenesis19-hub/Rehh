// Make generated workflow output explicit editable CODE before copying.

function telegramCodeBlock(text) {
  const clean = String(text || '').replace(/```/g, "''' ").trim();
  return `\`\`\`\n${clean}\n\`\`\``;
}

async function saveCompletedWorkflow(action, order, data, outputCards) {
  const user = telegramUser();
  if (!user?.id) throw new Error('Mini App harus dibuka dari Telegram.');
  const outputs = outputCards.map(card => ({
    kind: card.dataset.outputKind,
    content: card.querySelector('textarea')?.value || '',
  }));
  const response = await fetch('/api/workflow-complete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      telegram_id: String(user.id),
      action,
      service_number: order.service_number,
      data,
      outputs,
    }),
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.message || `HTTP ${response.status}`);
  return payload;
}

const _renderWorkflowResultBeforeCodeEditor = renderWorkflowResult;
renderWorkflowResult = function renderWorkflowResultAsEditableCode(action, order, data) {
  const host = workflowHost();
  const outputs = generateWorkflowOutputs(action, data);
  host.innerHTML = `<article class="tool-card">
    <strong>✅ ${action.toUpperCase()} SIAP</strong>
    <small>INET ${esc(order.service_number)} • edit bila perlu, lalu salin sebagai code Telegram.</small>
    <div class="info-box" style="margin-top:12px"><span>⌨</span><p><strong style="color:#eef6ff">Output berupa CODE</strong><br>Saat disalin, output otomatis dibungkus dengan tanda <b>&#96;&#96;&#96;</b> supaya tampil sebagai code block di Telegram.</p></div>
    <div id="wfOutputs" style="margin-top:12px"></div>
    <div class="info-box" style="margin-top:12px;border-color:#5a4721"><span>🕘</span><p><strong style="color:#eef6ff">Belum ditandai selesai</strong><br>Sebelum tombol SUDAH DIKERJAKAN ditekan, proses tetap dianggap draft. Setelah ditekan, hasil masuk history dan tetap bisa diedit.</p></div>
    <button class="tool-action" id="wfDone" style="border-color:#2f765d;background:linear-gradient(180deg,#103128,#0b2025)"><b>✅ SUDAH DIKERJAKAN</b><span>Simpan history ›</span></button>
    <button class="tool-action hidden" id="wfOpenHistory"><b>🕘 HISTORY / EDIT</b><span>›</span></button>
    <button class="tool-action" id="wfAnother"><b>Kerjakan order lain</b><span>＋</span></button>
    <button class="tool-action" id="wfHome"><b>Kembali ke menu Input</b><span>‹</span></button>
  </article>`;

  const box = document.querySelector('#wfOutputs');
  outputs.forEach(([kind, text], index) => {
    const card = document.createElement('div');
    card.dataset.outputKind = kind;
    card.style.marginBottom = '14px';
    card.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:7px"><strong>${esc(kind)}</strong><span style="font-size:9px;color:#758ba2">CODE ${index + 1}</span></div>
      <textarea spellcheck="false" style="width:100%;min-height:${kind === 'REPORT' ? '300px' : '250px'};box-sizing:border-box;white-space:pre;overflow:auto;background:#06111f;border:1px solid #203a57;border-radius:12px;padding:12px;font:10px/1.55 monospace;color:#dceaff;resize:vertical">${esc(text)}</textarea>
      <button class="tool-action" type="button"><b>📋 SALIN CODE ${esc(kind)}</b><span>Salin ›</span></button>`;
    const textarea = card.querySelector('textarea');
    card.querySelector('button').addEventListener('click', () => copyText(telegramCodeBlock(textarea.value), `Code ${kind} tersalin`));
    box.appendChild(card);
  });

  const doneButton = document.querySelector('#wfDone');
  const historyButton = document.querySelector('#wfOpenHistory');
  doneButton?.addEventListener('click', async () => {
    if (doneButton.disabled) return;
    doneButton.disabled = true;
    doneButton.querySelector('b').textContent = '⏳ MENYIMPAN...';
    try {
      const cards = [...box.querySelectorAll('[data-output-kind]')];
      await saveCompletedWorkflow(action, order, data, cards);
      doneButton.querySelector('b').textContent = '✅ SUDAH TERSIMPAN';
      doneButton.querySelector('span').textContent = 'Masuk history';
      historyButton?.classList.remove('hidden');
      if (typeof removeWorkflowDraft === 'function') {
        try { removeWorkflowDraft(action, order.service_number); } catch (_) {}
      }
      showToast('Pekerjaan masuk history');
    } catch (error) {
      console.error('Gagal menyimpan pekerjaan selesai', error);
      doneButton.disabled = false;
      doneButton.querySelector('b').textContent = '✅ SUDAH DIKERJAKAN';
      doneButton.querySelector('span').textContent = 'Coba lagi ›';
      showToast(error.message || 'Gagal menyimpan history');
    }
  });

  historyButton?.addEventListener('click', () => {
    if (typeof openWorkflowHistory === 'function') {
      openWorkflowHistory(order.service_number);
    } else {
      openPage('reportsPage');
      showToast('Buka order lalu HISTORY / EDIT');
    }
  });

  document.querySelector('#wfAnother')?.addEventListener('click', () => startWorkflow(action));
  document.querySelector('#wfHome')?.addEventListener('click', renderWorkflowHome);
};
