// INJOKO role-based Mini App UI.
(function(){
  const tgUser=()=>window.Telegram?.WebApp?.initDataUnsafe?.user||null;
  const normalizeRole=v=>String(v||'').trim().toUpperCase();
  const managerRoles=new Set(['HSA','OSA','ADMIN']);
  function applyBranding(){
    document.title='INJOKO - Dashboard';
    document.querySelectorAll('body *').forEach(el=>{if(el.children.length===0&&/Kerja BOT/i.test(el.textContent||''))el.textContent=el.textContent.replace(/Kerja BOT/gi,'INJOKO');});
    document.querySelectorAll('.payroll-nav small').forEach(el=>el.textContent='Rekon');
    const p=document.querySelector('#payrollPage');
    if(p)p.querySelectorAll('*').forEach(el=>{if(el.children.length===0&&/Payroll/i.test(el.textContent||''))el.textContent=el.textContent.replace(/Payroll/gi,'Rekon');});
  }
  function applyRole(role){
    role=normalizeRole(role)||'TECHNICIAN'; window.INJOKO_ROLE=role;
    const badge=document.querySelector('.role-badge'); if(badge)badge.textContent=role==='TECHNICIAN'?'TEKNISI':role;
    const input=document.querySelector('#inputPage'); if(!input)return;
    const title=input.querySelector('.tool-title'),sub=input.querySelector('.tool-sub'),host=input.querySelector('.tool-list'); if(!host)return;
    if(managerRoles.has(role)){
      if(title)title.textContent='Assign WO'; if(sub)sub.textContent=`${role} • Assign Work Order ke teknisi`;
      host.innerHTML='<article class="tool-card"><strong>ASSIGN WO</strong><small>Gunakan workflow assignment yang sudah tersedia untuk memilih teknisi dan meneruskan WO.</small><button class="tool-action" id="injokoAssign"><b>ASSIGN WO</b><span>Mulai ›</span></button></article>';
      host.querySelector('#injokoAssign')?.addEventListener('click',async()=>{try{await navigator.clipboard.writeText('/assign')}catch(e){} if(typeof window.showToast==='function')window.showToast('/assign tersalin — lanjutkan di bot');else if(window.Telegram?.WebApp?.showPopup)window.Telegram.WebApp.showPopup({title:'Assign WO',message:'Perintah /assign sudah disalin. Lanjutkan assignment melalui bot.'});});
    }else{
      if(title)title.textContent='Input Pekerjaan'; if(sub)sub.textContent='Pilih workflow, lalu pilih order OPEN dari Google Sheet.';
      if(typeof window.renderWorkflowHome==='function')window.renderWorkflowHome();
    }
  }
  async function loadRole(){
    const user=tgUser(); if(!user?.id){applyRole('TECHNICIAN');return;}
    try{const r=await fetch('/api/technician-profile?telegram_id='+encodeURIComponent(user.id),{cache:'no-store'});const d=await r.json();applyRole(d?.profile?.role||'TECHNICIAN');}
    catch(e){console.error('[INJOKO] role load failed',e);applyRole('TECHNICIAN');}
  }
  applyBranding(); window.addEventListener('load',()=>{applyBranding();loadRole();}); window.addEventListener('pageshow',()=>{applyBranding();loadRole();});
})();
