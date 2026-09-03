(() => {
  if (window.__injokoOrderankuClean) return;
  window.__injokoOrderankuClean = true;

  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = v => new Intl.NumberFormat('id-ID').format(Number(v || 0));
  const legacy = /MANYAR|MYR|JAGIR|JGR|ORDER SHEET \(MYR\)|WORK ORDER JAGIR/i;

  function isOrdersPage(){ return document.querySelector('#ordersPage') && !document.querySelector('#ordersPage')?.classList.contains('hidden'); }
  function cleanText(root=document){
    if (!isOrdersPage()) return;
    root.querySelectorAll('#ordersPage *').forEach(el => {
      if (el.children.length === 0 && legacy.test(el.textContent || '')) {
        el.textContent = (el.textContent || '').replace(legacy, 'INJOKO');
      }
    });
  }

  function renderInjokoOrders(data){
    const page=document.querySelector('#ordersPage');
    const id=document.querySelector('#ordersIdentity');
    const list=document.querySelector('#myOrdersList');
    const count=document.querySelector('#myOrderCount');
    if(!page||!id||!list||!count)return;

    const tech=data.technician||{};
    const supervisor=!!data.supervisor;
    id.textContent=supervisor
      ? `${tech.name||'HSA'} • NIK ${tech.nik||'-'} • INJOKO`
      : `${tech.name||'-'} • NIK ${tech.nik||'-'} • INJOKO`;

    count.textContent=`${fmt(data.total_open||0)} OPEN`;
    list.replaceChildren();

    if (supervisor) {
      // Supervisor UI already renders the global HSA summary.
      if (typeof window.renderSupervisorSummary === 'function') window.renderSupervisorSummary(data);
    }

    const areas=(data.areas||[]).filter(a => String(a.area||'').toUpperCase()==='INJOKO');
    if(!areas.length){
      list.innerHTML='<div class="empty"><p>✅ Tidak ada order OPEN INJOKO.</p></div>';
      cleanText(page);
      return;
    }

    const area=areas[0];
    const orders=area.orders||[];
    const head=document.createElement('section');
    head.className='panel';
    head.style.cssText='margin-bottom:10px;padding:12px 14px';
    head.innerHTML=`<strong>🧰 REPLACEMENT • INJOKO</strong><small style="display:block;color:#8095aa;margin-top:4px">OPEN ${fmt(area.open)} • SELESAI ${fmt(area.close)} • UPDATE ${fmt(area.update)}</small>`;
    list.appendChild(head);

    if(!orders.length){
      const empty=document.createElement('div');
      empty.className='empty';
      empty.innerHTML='<p>✅ Tidak ada order OPEN INJOKO.</p>';
      list.appendChild(empty);
      cleanText(page);
      return;
    }

    orders.forEach((o,i)=>{
      const c=document.createElement('div');
      c.className='mini-order';
      const techLine=supervisor?`👷 ${esc(o.technician_nik||'-')} • ${esc(o.technician_name||'-')}<br>`:'';
      c.innerHTML=`<strong>${i+1}. ${esc(o.customer_name||'-')}</strong><small style="line-height:1.65">${techLine}🎫 ${esc(o.ticket_id||'MANUAL')}<br>🌐 ${esc(o.service_number||'-')}<br>📞 ${esc(o.customer_phone||'-')}<br>⚡ ${esc(o.package||'-')}<br>📡 ONU RX: ${esc(o.onu_rx||'-')}<br>📝 RCA: ${esc(o.rca||'-')}<br>🏠 ${esc(o.address||'-')}</small>`;
      list.appendChild(c);
    });
    cleanText(page);
  }

  const originalLoad=window.loadMyOpenOrders;
  window.loadMyOpenOrders=async function injokoLoadMyOpenOrders(force=false){
    const id=document.querySelector('#ordersIdentity'),list=document.querySelector('#myOrdersList');
    if(id)id.textContent='🔄 Membaca Google Sheets INJOKO...';
    if(list)list.innerHTML='<div class="empty"><p>Memuat order INJOKO...</p></div>';
    try{
      if(typeof window.fetchMyOpenOrders!=='function') return await originalLoad(force);
      const d=await window.fetchMyOpenOrders(force);
      state.myOpenOrders=d;
      renderInjokoOrders(d);
      return d;
    }catch(e){
      if(id)id.textContent='❌ Gagal membaca Orderanku INJOKO.';
      if(list)list.innerHTML=`<div class="empty"><p>${esc(e.message)}</p></div>`;
      return null;
    }
  };

  const observer=new MutationObserver(() => {
    if(isOrdersPage()) cleanText();
  });
  observer.observe(document.body,{childList:true,subtree:true});
})();
