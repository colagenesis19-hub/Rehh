// INJOKO role-based Mini App UI.
(function(){
  'use strict';
  const tgUser=()=>window.Telegram?.WebApp?.initDataUnsafe?.user||null;
  const normalizeRole=v=>String(v||'').trim().toUpperCase();
  const managerRoles=new Set(['HSA','OSA','ADMIN','SUPERVISOR']);
  const nikRoleMap={'86240021':'HSA'};

  function applyBranding(){
    document.title='INJOKO - Dashboard';
    document.querySelectorAll('body *').forEach(el=>{
      if(el.children.length!==0)return;
      const text=el.textContent||'';
      const next=text.replace(/Kerja BOT/gi,'INJOKO').replace(/Payroll/gi,'Rekon');
      if(next!==text)el.textContent=next;
    });
    document.querySelectorAll('.payroll-nav small').forEach(el=>el.textContent='Rekon');
  }

  function applyRole(role){
    role=normalizeRole(role)||'TECHNICIAN';
    window.INJOKO_ROLE=role;
    const badge=document.querySelector('.role-badge');
    if(badge)badge.textContent=role==='TECHNICIAN'?'TEKNISI':role==='SUPERVISOR'?'HSA / OSA':role;
    const input=document.querySelector('#inputPage');
    if(!input)return;
    const title=input.querySelector('.tool-title'),sub=input.querySelector('.tool-sub'),host=input.querySelector('.tool-list');
    if(!host)return;
    if(managerRoles.has(role)){
      if(title)title.textContent='Assign WO';
      if(sub)sub.textContent='HSA / OSA • Assign Work Order ke teknisi';
      host.innerHTML='<article class="tool-card"><strong>ASSIGN WO</strong><small>Pilih teknisi dan order untuk proses assignment.</small><button class="tool-action" id="injokoAssign"><b>ASSIGN WO</b><span>Mulai ›</span></button></article>';
      host.querySelector('#injokoAssign')?.addEventListener('click',async()=>{try{await navigator.clipboard.writeText('/assign')}catch(e){};if(typeof window.showToast==='function')window.showToast('/assign tersalin — lanjutkan di bot');else if(window.Telegram?.WebApp?.showPopup)window.Telegram.WebApp.showPopup({title:'Assign WO',message:'Perintah /assign sudah disalin. Lanjutkan assignment melalui bot.'});});
    }else{
      if(title)title.textContent='Input Pekerjaan';
      if(sub)sub.textContent='Pilih workflow, lalu pilih order OPEN dari Google Sheet.';
      if(typeof window.renderWorkflowHome==='function')window.renderWorkflowHome();
    }
  }

  async function loadRole(){
    const user=tgUser();
    if(!user?.id){applyRole('TECHNICIAN');return;}
    try{
      const r=await fetch('/api/technician-profile?telegram_id='+encodeURIComponent(user.id),{cache:'no-store'});
      const d=await r.json().catch(()=>({}));
      const profile=d?.profile||{};
      let role=normalizeRole(profile.role);
      const nik=String(profile.nik||profile.NIK||profile.nik_teknisi||profile.nikTeknisi||'').replace(/\D/g,'');
      if(nikRoleMap[nik])role=nikRoleMap[nik];
      try{
        const mr=await fetch('/api/technician-master?telegram_id='+encodeURIComponent(user.id),{cache:'no-store'});
        if(mr.ok){const md=await mr.json().catch(()=>({}));const masterRole=normalizeRole(md?.role);if(managerRoles.has(masterRole))role=masterRole;}
      }catch(e){}
      if(nikRoleMap[nik])role=nikRoleMap[nik];
      applyRole(role||'TECHNICIAN');
    }catch(e){console.error('[INJOKO] role load failed',e);applyRole('TECHNICIAN');}
  }

  window.INJOKO_APPLY_BRANDING=applyBranding;
  window.INJOKO_APPLY_ROLE=applyRole;
  function boot(){applyBranding();loadRole();setTimeout(applyBranding,500);}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
  window.addEventListener('pageshow',()=>{applyBranding();loadRole();});
})();
