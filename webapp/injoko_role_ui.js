// INJOKO role-based Mini App UI + HSA/OSA Assign WO.
(function(){
  'use strict';
  const tgUser=()=>window.Telegram?.WebApp?.initDataUnsafe?.user||null;
  const normalizeRole=v=>String(v||'').trim().toUpperCase();
  const managerRoles=new Set(['HSA','OSA','ADMIN','SUPERVISOR']);
  const nikRoleMap={'86240021':'HSA'};
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function applyBranding(){
    document.title='INJOKO - Dashboard';
    document.querySelectorAll('body *').forEach(el=>{if(el.children.length!==0)return;const text=el.textContent||'';const next=text.replace(/Kerja BOT/gi,'INJOKO').replace(/Payroll/gi,'Rekon');if(next!==text)el.textContent=next;});
    document.querySelectorAll('.payroll-nav small').forEach(el=>el.textContent='Rekon');
  }

  async function openAssignWO(){
    const host=document.querySelector('#inputPage .tool-list');if(!host)return;
    host.innerHTML='<div class="empty"><p>🔄 Membaca teknisi dan order OPEN dari Google Sheet...</p></div>';
    try{const u=tgUser();if(!u?.id)throw new Error('Mini App harus dibuka dari Telegram.');const r=await fetch('/api/assign-wo?telegram_id='+encodeURIComponent(u.id),{cache:'no-store'});const d=await r.json().catch(()=>({}));if(!r.ok||!d.ok)throw new Error(d.message||`HTTP ${r.status}`);renderAssignWO(d);}catch(e){host.innerHTML=`<div class="empty"><p>❌ ${esc(e.message)}</p><button class="tool-action" id="assignRetry"><b>COBA LAGI</b><span>↻</span></button></div>`;host.querySelector('#assignRetry')?.addEventListener('click',openAssignWO);}
  }

  function renderAssignWO(d){
    const host=document.querySelector('#inputPage .tool-list');if(!host)return;
    const techOptions=(d.technicians||[]).map(t=>`<option value="${esc(t.nik)}">${esc(t.name)}${t.sto?` • ${esc(t.sto)}`:''} • ${esc(t.nik)}</option>`).join('');
    const orders=(d.orders||[]).map(o=>`<label class="mini-order assign-card" style="display:block;cursor:pointer"><input type="checkbox" class="assign-order" value="${esc(o.service_number)}" style="margin-right:8px"><strong>${esc(o.customer_name||'-')}</strong><small style="line-height:1.65">🌐 ${esc(o.service_number)}<br>🎫 ${esc(o.ticket_id||'MANUAL')}<br>📍 ${esc(o.address||'-')}<br>👤 ${o.assigned_technician?`Sudah: ${esc(o.assigned_technician)}`:'Belum di-assign'}</small></label>`).join('');
    host.innerHTML=`<article class="tool-card"><strong>ASSIGN WO</strong><small>Pilih teknisi tujuan dan order OPEN. Assignment akan ditulis langsung ke Google Sheet.</small><label style="display:block;margin-top:12px;color:#7890aa;font-size:10px">TEKNISI TUJUAN<select id="assignTech" style="width:100%;margin-top:6px;padding:12px;border-radius:12px;background:#0b1b2e;color:#eef6ff;border:1px solid #294562"><option value="">Pilih teknisi...</option>${techOptions}</select></label><div class="search-wrap" style="margin-top:12px"><span>⌕</span><input id="assignSearch" placeholder="Cari INET, nama, alamat..." /></div><div id="assignOrders" class="mini-order-list" style="margin-top:9px;max-height:55vh;overflow:auto">${orders||'<div class="empty"><p>Tidak ada order OPEN.</p></div>'}</div><button class="tool-action" id="assignSubmit"><b>ASSIGN WO</b><span>→</span></button><button class="tool-action" id="assignRefresh"><b>REFRESH SHEET</b><span>↻</span></button></article>`;
    host.querySelector('#assignSearch')?.addEventListener('input',()=>{const q=String(host.querySelector('#assignSearch').value||'').toUpperCase();host.querySelectorAll('.assign-card').forEach(card=>card.style.display=(!q||card.textContent.toUpperCase().includes(q))?'block':'none');});
    host.querySelector('#assignRefresh')?.addEventListener('click',openAssignWO);
    host.querySelector('#assignSubmit')?.addEventListener('click',async()=>{const tech=host.querySelector('#assignTech')?.value;const selected=[...host.querySelectorAll('.assign-order:checked')].map(x=>x.value);if(!tech)return window.showToast?.('Pilih teknisi tujuan');if(!selected.length)return window.showToast?.('Pilih minimal satu INET');const btn=host.querySelector('#assignSubmit');btn.disabled=true;btn.querySelector('b').textContent='MEMPROSES...';try{const u=tgUser();const r=await fetch('/api/assign-wo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:String(u.id),target_nik:tech,service_numbers:selected})});const x=await r.json().catch(()=>({}));if(!r.ok||!x.ok)throw new Error(x.message||`HTTP ${r.status}`);window.showToast?.(`✅ ${x.assigned.length} WO berhasil di-assign`);openAssignWO();}catch(e){window.showToast?.('❌ '+e.message);btn.disabled=false;btn.querySelector('b').textContent='ASSIGN WO';}});
  }

  function applyRole(role){
    role=normalizeRole(role)||'TECHNICIAN';window.INJOKO_ROLE=role;const badge=document.querySelector('.role-badge');if(badge)badge.textContent=role==='TECHNICIAN'?'TEKNISI':role==='SUPERVISOR'?'HSA / OSA':role;const input=document.querySelector('#inputPage');if(!input)return;const title=input.querySelector('.tool-title'),sub=input.querySelector('.tool-sub'),host=input.querySelector('.tool-list');if(!host)return;
    if(managerRoles.has(role)){if(title)title.textContent='Assign WO';if(sub)sub.textContent='HSA / OSA • Assign Work Order ke teknisi';host.innerHTML='<article class="tool-card"><strong>ASSIGN WO</strong><small>Pilih teknisi dan order OPEN untuk proses assignment ke Google Sheet.</small><button class="tool-action" id="injokoAssign"><b>ASSIGN WO</b><span>Mulai ›</span></button></article>';host.querySelector('#injokoAssign')?.addEventListener('click',openAssignWO);}
    else{if(title)title.textContent='Input Pekerjaan';if(sub)sub.textContent='Pilih workflow, lalu pilih order OPEN dari Google Sheet.';if(typeof window.renderWorkflowHome==='function')window.renderWorkflowHome();}
  }

  function protectManagerWorkflow(){if(!managerRoles.has(window.INJOKO_ROLE)||typeof window.renderWorkflowHome!=='function')return;if(window.__injokoWorkflowGuard)return;window.__injokoWorkflowGuard=true;const original=window.renderWorkflowHome;window.renderWorkflowHome=function(){if(managerRoles.has(window.INJOKO_ROLE)){openAssignWO();return;}return original.apply(this,arguments);};}

  async function loadRole(){
    const user=tgUser();if(!user?.id){applyRole('TECHNICIAN');return;}
    try{const r=await fetch('/api/technician-profile?telegram_id='+encodeURIComponent(user.id),{cache:'no-store'});const d=await r.json().catch(()=>({}));const profile=d?.profile||{};let role=normalizeRole(profile.role);const nik=String(profile.nik||profile.NIK||profile.nik_teknisi||profile.nikTeknisi||'').replace(/\D/g,'');if(nikRoleMap[nik])role=nikRoleMap[nik];try{const mr=await fetch('/api/technician-master?telegram_id='+encodeURIComponent(user.id),{cache:'no-store'});if(mr.ok){const md=await mr.json().catch(()=>({}));const masterRole=normalizeRole(md?.role);if(managerRoles.has(masterRole))role=masterRole;}}catch(e){}if(nikRoleMap[nik])role=nikRoleMap[nik];applyRole(role||'TECHNICIAN');protectManagerWorkflow();}catch(e){console.error('[INJOKO] role load failed',e);applyRole('TECHNICIAN');}
  }
  window.INJOKO_APPLY_BRANDING=applyBranding;window.INJOKO_APPLY_ROLE=applyRole;window.INJOKO_OPEN_ASSIGN_WO=openAssignWO;
  function boot(){applyBranding();loadRole();setTimeout(()=>{applyBranding();protectManagerWorkflow();},700);}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
  window.addEventListener('pageshow',()=>{applyBranding();loadRole();});
})();
