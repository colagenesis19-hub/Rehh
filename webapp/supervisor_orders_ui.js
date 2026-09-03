(() => {
  if (window.__supervisorOrdersUiInstalled) return;
  window.__supervisorOrdersUiInstalled = true;
  window.__orderTargetNik = '';
  let supervisorMeta = null;

  const escS = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const originalRenderMyOpenArea = window.renderMyOpenArea;
  const nativeFetch = window.fetch.bind(window);

  window.fetch = function supervisorAwareFetch(input, init) {
    let url = typeof input === 'string' ? input : input?.url;
    if (url && url.includes('/api/dismantle-orders?') && !url.includes('target_nik=')) {
      const target = String(window.__orderTargetNik || '').trim();
      if (target) {
        const u = new URL(url, window.location.origin);
        u.searchParams.set('target_nik', target);
        url = u.pathname + u.search;
        if (typeof input === 'string') input = url;
        else input = new Request(url, input);
      }
    }
    return nativeFetch(input, init);
  };

  window.fetchMyOpenOrders = async function fetchMyOpenOrdersSupervisor(force=false) {
    const u=telegramUser(); if(!u?.id)throw new Error('Mini App harus dibuka dari Telegram.');
    const p=new URLSearchParams({telegram_id:String(u.id)});
    if(window.__orderTargetNik)p.set('target_nik',window.__orderTargetNik);
    if(force)p.set('force','1');
    const r=await fetch(`/api/my-open-orders?${p}`,{cache:'no-store'}); const d=await r.json();
    if(!r.ok||!d.ok)throw new Error(d.message||`HTTP ${r.status}`);
    state.myOpenOrders=d; supervisorMeta=d; ensureSupervisorFilter(d); return d;
  };

  function ensureSupervisorFilter(data) {
    const page=document.querySelector('#ordersPage'); const summary=document.querySelector('#myOrderSummary');
    if(!page||!summary)return;
    let panel=document.querySelector('#orderSupervisorFilter');
    if(!data?.can_filter_nik){ panel?.remove(); return; }
    if(!panel){
      panel=document.createElement('section'); panel.id='orderSupervisorFilter'; panel.className='panel';
      panel.style.cssText='margin:12px 0;padding:14px;border-color:#31506f';
      panel.innerHTML=`<div style="display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:10px"><div><strong>👁 MODE ATASAN</strong><small style="display:block;color:#8095aa;margin-top:3px">Order semua teknisi • read only</small></div><span style="font-size:9px;color:#78dcb4">READ ONLY</span></div><label style="display:block;color:#8298ae;font-size:9px;margin-bottom:5px">FILTER NIK TEKNISI</label><select id="orderNikFilter" style="width:100%;border:1px solid #2d4c6a;background:#081827;color:#eef7ff;border-radius:12px;padding:11px"></select>`;
      summary.parentNode.insertBefore(panel,summary);
      panel.querySelector('#orderNikFilter').addEventListener('change',async e=>{
        window.__orderTargetNik=e.target.value;
        await loadMyOpenOrders(false);
        window.dispatchEvent(new CustomEvent('order-supervisor-filter-change',{detail:{targetNik:window.__orderTargetNik}}));
      });
    }
    const select=panel.querySelector('#orderNikFilter');
    const selected=String(data.selected_nik||'ALL').toUpperCase();
    select.innerHTML=`<option value="ALL">ALL • SEMUA TEKNISI</option>`+(data.technicians||[]).map(t=>`<option value="${escS(t.nik)}">${escS(t.nik)} • ${escS(t.name)}</option>`).join('');
    select.value=selected==='ALL'?'ALL':selected;
    window.__orderTargetNik=select.value;
  }

  window.renderMyOpenArea = function renderSupervisorOpenArea(area) {
    if(!supervisorMeta?.supervisor) return originalRenderMyOpenArea(area);
    const list=document.querySelector('#myOrdersList'),count=document.querySelector('#myOrderCount'); list.replaceChildren(); count.textContent=`${area.orders?.length||0} OPEN`;
    const back=document.createElement('button');back.className='tool-action';back.innerHTML='<b>‹ Kembali ke daftar area</b><span>📍</span>';back.addEventListener('click',()=>renderMyOrderAreas(state.myOpenOrders));list.appendChild(back);
    (area.orders||[]).forEach((o,i)=>{const c=document.createElement('div');c.className='mini-order';c.innerHTML=`<strong>${i+1}. ${esc(o.customer_name||'-')}</strong><small style="line-height:1.65">👷 ${esc(o.technician_nik||'-')} • ${esc(o.technician_name||'-')}<br>🎫 ${esc(o.ticket_id||'MANUAL')}<br>🌐 ${esc(o.service_number||'-')}<br>📞 ${esc(o.customer_phone||'-')}<br>⚡ ${esc(o.package||'-')}<br>📡 ONU RX: ${esc(o.onu_rx||'-')}<br>📝 RCA: ${esc(o.rca||'-')}<br>🏠 ${esc(o.address||'-')}</small>`;list.appendChild(c);});
  };

  function enforceReadOnlyDismantle() {
    if (!supervisorMeta?.supervisor) return;
    document.querySelectorAll('.dismantle-done').forEach(button => button.remove());
    const head = document.querySelector('#dismantleOverlay .dismantle-head p');
    if (head) head.textContent = 'NTE CRASH • mode atasan read only';
  }
  new MutationObserver(enforceReadOnlyDismantle).observe(document.body,{childList:true,subtree:true});
})();
