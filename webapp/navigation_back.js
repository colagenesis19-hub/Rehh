// Context-aware back navigation for Kerja BOT Mini App.
// Header back should step out of the current workflow before returning home.

function currentVisiblePage() {
  return [...document.querySelectorAll('.page-view')].find(page => !page.classList.contains('hidden')) || null;
}

function currentWorkflowArea() {
  const areaName = state.workflow?.order?.area;
  if (!areaName) return null;
  return (state.myOpenOrders?.areas || []).find(area => area.area === areaName) || null;
}

function smartBack() {
  const profileOverlay = document.querySelector('#technicianProfileOverlay');
  if (profileOverlay) { profileOverlay.remove(); return; }
  const masterOverlay = document.querySelector('#technicianMasterOverlay');
  if (masterOverlay) { masterOverlay.remove(); return; }
  const page = currentVisiblePage();
  if (!page) return;
  const dismantleOverlay = document.querySelector('#dismantleOverlay');
  if (dismantleOverlay && !dismantleOverlay.classList.contains('hidden')) { dismantleOverlay.classList.add('hidden'); return; }
  if (page.id === 'inputPage') {
    const action = state.workflow?.action;
    if (document.querySelector('#wfOutputs')) { const order=state.workflow?.order; if(action&&order)renderWorkflowForm(action,order);else if(action)startWorkflow(action);else renderWorkflowHome();return; }
    if (document.querySelector('#wfForm')) { const area=currentWorkflowArea();if(action&&area)renderWorkflowAreaOrders(action,area);else if(action)renderWorkflowAreas(action,state.myOpenOrders);else renderWorkflowHome();return; }
    if (document.querySelector('#wfOrders')) { if(action)renderWorkflowAreas(action,state.myOpenOrders);else renderWorkflowHome();return; }
    if (document.querySelector('#wfAreaList')) { renderWorkflowHome(); return; }
    openPage('dashboardPage'); return;
  }
  if (page.id === 'ordersPage') {
    const areaBack=[...document.querySelectorAll('#myOrdersList .tool-action')].find(button=>button.textContent.includes('Kembali ke daftar area'));
    if(areaBack){renderMyOrderAreas(state.myOpenOrders);return;}
  }
  if(page.id!=='dashboardPage')openPage('dashboardPage');
}

document.querySelectorAll('[data-back-dashboard]').forEach(button=>button.addEventListener('click',event=>{event.preventDefault();event.stopImmediatePropagation();smartBack();},true));

if (tg?.BackButton) {
  const syncTelegramBack=()=>{const page=currentVisiblePage();if(page&&page.id!=='dashboardPage')tg.BackButton.show();else tg.BackButton.hide();};
  tg.BackButton.onClick(smartBack);
  const originalOpenPage=openPage;openPage=function openPageWithBackSync(id){originalOpenPage(id);syncTelegramBack();};syncTelegramBack();
}

function loadMiniAppScript(src, marker) {
  return new Promise((resolve,reject)=>{
    const existing=document.querySelector(`script[data-${marker}]`);
    if(existing){if(existing.dataset.loaded==='1')resolve();else{existing.addEventListener('load',resolve,{once:true});existing.addEventListener('error',reject,{once:true});}return;}
    const script=document.createElement('script');script.src=`${src}?v=20260831-nik-link1`;script.dataset[marker.replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]='1';
    script.onload=()=>{script.dataset.loaded='1';resolve();};script.onerror=reject;document.body.appendChild(script);
  });
}

loadMiniAppScript('/technician_profile_ui.js','technician-profile-ui').catch(error=>console.error('Gagal memuat profile editor',error));
loadMiniAppScript('/report_dashboard.js','report-dashboard')
  .then(()=>loadMiniAppScript('/report_supervisor.js','report-supervisor'))
  .then(()=>loadMiniAppScript('/technician_master_ui.js','technician-master-ui'))
  .then(()=>loadMiniAppScript('/report_history_editor.js','report-history-editor'))
  .catch(error=>console.error('Gagal memuat report/master enhancement',error));
loadMiniAppScript('/leaderboard_identity_fix.js','leaderboard-identity-fix').catch(error=>console.error('Gagal memuat identity fix',error));
loadMiniAppScript('/draft_history.js','draft-history').then(()=>loadMiniAppScript('/unified_workflow_ui.js','unified-workflow-ui')).then(()=>loadMiniAppScript('/input_code_editor.js','input-code-editor')).catch(error=>console.error('Gagal memuat workflow enhancement',error));
loadMiniAppScript('/order_detail.js','order-detail').then(()=>loadMiniAppScript('/orderanku_android_fix.js','orderanku-android-fix')).then(()=>loadMiniAppScript('/supervisor_orders_ui.js','supervisor-orders-ui')).then(()=>loadMiniAppScript('/manja_ui_v2.js','manja-ui-v2')).then(()=>loadMiniAppScript('/dismantle_ui.js','dismantle-ui')).catch(error=>console.error('Gagal memuat detail order/MANJA/DISMANTLE',error));
loadMiniAppScript('/interactive_ui.js','interactive-ui').then(()=>loadMiniAppScript('/dashboard_chart_switch.js','dashboard-chart-switch')).catch(error=>console.error('Gagal memuat interaction/dashboard chart enhancement',error));
loadMiniAppScript('/injoko_role_ui.js','injoko-role-ui').catch(error=>console.error('Gagal memuat INJOKO role UI',error));
loadMiniAppScript('/injoko_html.js','injoko-html').catch(error=>console.error('Gagal memuat INJOKO HTML patch',error));
