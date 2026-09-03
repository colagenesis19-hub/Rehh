(() => {
  if (window.__unifiedWorkflowUiInstalled) return;
  window.__unifiedWorkflowUiInstalled = true;

  const sharedFields = [
    'ticket_id','service_number','voip_number','customer_name','address',
    'customer_phone','old_sn','new_sn','ont_type','sto','valins_id','result',
    'config_description','report_description'
  ];

  const previousWorkflowSeed = window.workflowSeed;
  if (typeof previousWorkflowSeed === 'function') {
    window.workflowSeed = function unifiedWorkflowSeed(order) {
      const base = previousWorkflowSeed(order || {});
      sharedFields.forEach(field => {
        const value = String(order?.[field] ?? '').trim();
        if (value && value !== 'MANUAL') base[field] = value;
      });
      // Keep MANUAL as an empty ticket so the UI still asks for a real ticket.
      if (String(order?.ticket_id || '').trim().toUpperCase() === 'MANUAL') base.ticket_id = '';
      return base;
    };
  }

  function addSyncInfo() {
    const host = document.querySelector('#wfForm')?.closest('.tool-card');
    const order = state?.workflow?.order;
    if (!host || !order || host.querySelector('#unifiedWorkflowInfo')) return;
    if (!order.unified && !(order.completed_kinds || []).length) return;

    const kinds = Array.isArray(order.completed_kinds) ? order.completed_kinds : [];
    const info = document.createElement('div');
    info.id = 'unifiedWorkflowInfo';
    info.className = 'info-box';
    info.style.marginTop = '10px';
    info.innerHTML = `<span>↔</span><p><strong>Sinkron dengan Chatbot</strong><br>${
      order.unified ? 'Field terakhir dari chatbot/Mini App sudah dipakai bersama.' : 'State workflow bersama aktif.'
    }${kinds.length ? `<br>History tersedia: ${kinds.join(' • ')}` : ''}</p>`;
    const form = host.querySelector('#wfForm');
    host.insertBefore(info, form);
  }

  // draft_history.js may wrap renderWorkflowForm before this script loads.
  // Wrap the final function so the sync indicator always follows the rendered form.
  if (typeof window.renderWorkflowForm === 'function') {
    const previousRenderWorkflowForm = window.renderWorkflowForm;
    window.renderWorkflowForm = function renderUnifiedWorkflowForm(action, order) {
      const result = previousRenderWorkflowForm(action, order);
      setTimeout(addSyncInfo, 0);
      return result;
    };
  }
})();
