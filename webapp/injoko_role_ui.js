// INJOKO role-based Mini App UI.
(function(){
  'use strict';

  const tgUser=()=>window.Telegram?.WebApp?.initDataUnsafe?.user||null;
  const normalizeRole=v=>String(v||'').trim().toUpperCase();
  const managerRoles=new Set(['HSA','OSA','ADMIN','SUPERVISOR']);

  // Explicit INJOKO role mapping.
  // NIK 86240021 is HSA and must not fall back to TECHNICIAN.
  const nikRoleMap={
    '86240021':'HSA'
  };

  function applyBranding(){
    document.title='INJOKO - Dashboard';
    document.querySelectorAll('body *').forEach(el=>{
      if(el.children.length!==0)return;
      const text=el.textContent||'';
      const next=text.replace(/Kerja BOT/gi,'INJOKO').replace(/Payroll/gi,'Rekon');
      if(next!==text)el.textContent=next;
    });
    document.querySelectorAll('.payroll-nav small').forEach(el=>{
      if(el.textContent!=='Rekon')el.textContent='Rekon';
    });
    const p=document.querySelector('#payrollPage');
    if(p)p.querySelectorAll('*').forEach(el=>{
      if(el.children.length!==0)return;
      const text=el.textContent||'';
      const next=text.replace(/Payroll/gi,'Rekon');
      if(next!==text)el.textContent=next;
    });
  }

  function applyRole(role){
    role=normalizeRole(role)||'TECHNICIAN';
    window.INJOKO_ROLE=role;
    const badge=document.querySelector('.role-badge');
    if(badge)badge.textContent=role==='TECHNICIAN'?'TEKNISI':role==='SUPERVISOR'?'HSA / OSA':role;
    const input=document.querySelector('#inputPage');
    if(!input)return;
    const title=input.querySelector('.tool-title');
    const sub=input.querySelector('.tool-sub');
    const host=input.querySelector('.tool-list');
    if(!host)return;

    if(managerRoles.has(role)){
      if(title)title.textContent='Assign WO';
      if(sub)sub.textContent='HSA / OSA • Assign Work Order ke teknisi';
      host.innerHTML='<article class="tool-card"><strong>ASSIGN WO</strong><small>Pilih teknisi dan order untuk proses assignment. Workflow assignment yang sudah tersedia tetap digunakan.</small><button class="tool-action" id="injokoAssign"><b>ASSIGN WO</b><span>Mulai ›</span></button></article>';
      host.querySelector('#injokoAssign')?.addEventListener('click',async()=>{
        try{await navigator.clipboard.writeText('/assign')}catch(e){}
        if(typeof window.showToast==='function')window.showToast('/assign tersalin — lanjutkan di bot');
        else if(window.Telegram?.WebApp?.showPopup)window.Telegram.WebApp.showPopup({title:'Assign WO',message:'Perintah /assign sudah disalin. Lanjutkan assignment melalui bot.'});
      });
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
      const d=await r.json();
      let role=d?.profile?.role||'';

      // If the profile API exposes NIK, enforce the explicit INJOKO mapping.
      const profile=d?.profile||{};
      const nik=String(profile.nik||profile.NIK||profile.nik_teknisi||profile.nikTeknisi||'').trim();
      if(nik && nikRoleMap[nik]) role=nikRoleMap[nik];

      if(!role||role==='TECHNICIAN'){
        try{
          const mr=await fetch('/api/technician-master?telegram_id='+encodeURIComponent(user.id),{cache:'no-store'});
          if(mr.ok){
            const md=await mr.json();
            if(md?.can_manage||md?.role==='SUPERVISOR')role=md.role||'SUPERVISOR';
          }
        }catch(e){}
      }

      // Re-apply the explicit mapping after master lookup so it cannot be overwritten.
      if(nik && nikRoleMap[nik]) role=nikRoleMap[nik];
      applyRole(role||'TECHNICIAN');
    }catch(e){
      console.error('[INJOKO] role load failed',e);
      applyRole('TECHNICIAN');
    }
  }

  window.INJOKO_APPLY_BRANDING=applyBranding;
  window.INJOKO_APPLY_ROLE=applyRole;

  function boot(){
    applyBranding();
    loadRole();
    setTimeout(applyBranding,500);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
  window.addEventListener('pageshow',()=>{applyBranding();loadRole();});
})();
