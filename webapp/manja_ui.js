(() => {
  const $=(s,p=document)=>p.querySelector(s);
  const $$=(s,p=document)=>[...p.querySelectorAll(s)];
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let manjaPayload={ok:true,count:0,items:[]};

  function telegramId(){ return window.Telegram?.WebApp?.initDataUnsafe?.user?.id || null; }
  function orderData(){ try{return typeof state!=='undefined'?state.myOpenOrders:window.state?.myOpenOrders;}catch(_){return window.state?.myOpenOrders;} }
  function itemMap(){ return new Map((manjaPayload.items||[]).map(x=>[String(x.service_number||''),x])); }
  function findInet(text){ return (String(text||'').match(/\b\d{9,15}\b/)||[])[0]||''; }

  function ensureStyles(){
    if($('#manjaStyles'))return;
    const st=document.createElement('style'); st.id='manjaStyles'; st.textContent=`
      .manja-banner{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:10px 0 12px;padding:13px 14px;border:1px solid rgba(255,190,47,.32);border-radius:17px;background:linear-gradient(135deg,rgba(87,56,6,.36),rgba(26,40,58,.86));color:#eef6ff;box-shadow:0 12px 28px rgba(0,0,0,.14);transition:.25s}.manja-banner:active{transform:scale(.985)}
      .manja-banner-left{display:flex;gap:10px;align-items:center}.manja-orb{width:39px;height:39px;border-radius:13px;display:grid;place-items:center;background:linear-gradient(135deg,#ffcc4d,#f39a18)}.manja-copy strong{display:block;font-size:12px}.manja-copy small{display:block;color:#a9b6c8;font-size:9px;margin-top:3px}.manja-count{min-width:32px;height:28px;padding:0 9px;border-radius:999px;display:grid;place-items:center;background:rgba(255,193,44,.13);border:1px solid rgba(255,193,44,.28);color:#ffd169;font-weight:900}
      .mini-order.manja-order{border-color:rgba(255,190,47,.42)!important;background:linear-gradient(180deg,rgba(53,42,18,.42),rgba(10,24,40,.98))!important}.manja-chip{display:inline-flex;align-items:center;gap:5px;margin:0 0 7px;padding:5px 8px;border-radius:999px;background:rgba(255,191,38,.12);border:1px solid rgba(255,191,38,.28);color:#ffd169;font-size:9px;font-weight:900}.manja-actions{display:flex;gap:8px;margin-top:10px}.manja-actions button{flex:1;border:1px solid #2b4664;background:#0b1c30;color:#eaf5ff;border-radius:11px;padding:9px;font-size:10px;font-weight:800}.manja-actions .danger{border-color:rgba(255,91,108,.35);color:#ff8791}
      .manja-modal{position:fixed;inset:0;z-index:180}.manja-backdrop{position:absolute;inset:0;background:rgba(0,5,12,.72);backdrop-filter:blur(6px)}.manja-sheet{position:absolute;left:0;right:0;bottom:0;max-width:720px;margin:auto;border:1px solid #294562;border-radius:24px 24px 0 0;background:linear-gradient(180deg,#10243b,#091725);padding:18px 16px calc(24px + env(safe-area-inset-bottom));animation:manjaUp .28s cubic-bezier(.2,.8,.2,1)}@keyframes manjaUp{from{transform:translateY(18px);opacity:.2}to{transform:none;opacity:1}}.manja-sheet h3{margin:4px 0}.manja-sheet p{margin:0 0 14px;color:#8197ae;font-size:10px}.manja-grid{display:grid;grid-template-columns:1fr 1fr;gap:9px}.manja-field{display:grid;gap:5px}.manja-field.full{grid-column:1/-1}.manja-field span{font-size:9px;color:#8fa5bc;font-weight:800}.manja-field input,.manja-field textarea{width:100%;border:1px solid #294562;border-radius:12px;background:#081726;color:#fff;padding:11px;outline:0}.manja-field textarea{min-height:84px;resize:vertical}.manja-save{width:100%;margin-top:12px;border:0;border-radius:13px;padding:12px;background:linear-gradient(135deg,#f0a51d,#ffd15a);color:#291900;font-weight:900}.manja-close{position:absolute;right:14px;top:14px;border:0;background:#162b44;color:#fff;width:34px;height:34px;border-radius:10px}
    `; document.head.appendChild(st);
  }

  function mergeIntoOrders(){
    const map=itemMap(); const data=orderData();
    (data?.areas||[]).forEach(area=>(area.orders||[]).forEach(order=>{
      const m=map.get(String(order.service_number||''));
      if(m){order.rca='MANJA';order.manja=m;order.manja_note=m.note||'';order.manja_source=m.source||'';}
      else if(order.manja){delete order.manja;delete order.manja_note;delete order.manja_source;}
    }));
  }

  async function refreshManja(){
    const id=telegramId(); if(!id)return;
    try{
      const r=await fetch(`/api/manja?${new URLSearchParams({telegram_id:String(id)})}`,{cache:'no-store'}); const d=await r.json();
      if(r.ok&&d.ok){manjaPayload=d;mergeIntoOrders();updateBanner();decorate();}
    }catch(e){console.error('MANJA fetch gagal',e);}
  }

  function ensureBanner(){
    ensureStyles(); const page=$('#ordersPage'); if(!page)return null; let b=$('#manjaBanner');
    if(!b){b=document.createElement('button');b.id='manjaBanner';b.className='manja-banner hidden';b.type='button';b.innerHTML='<span class="manja-banner-left"><span class="manja-orb">📅</span><span class="manja-copy"><strong>MANJA • Manajemen Janji</strong><small>Gabungan /update + Mini App</small></span></span><span class="manja-count">0</span>';const a=$('#myOrderSummary',page)||$('#myOrdersList',page);a?.parentNode?.insertBefore(b,a);b.onclick=renderManjaOnly;}
    return b;
  }

  function updateBanner(){const b=ensureBanner();if(!b)return;const n=manjaPayload.count||0;b.classList.toggle('hidden',!n);$('.manja-count',b).textContent=String(n);$('.manja-copy small',b).textContent=n?`${n} MANJA aktif • ketuk untuk lihat`:'Tidak ada MANJA aktif';if(n&&!sessionStorage.getItem('manja-reminded')){sessionStorage.setItem('manja-reminded','1');window.showToast?.(`📅 Kamu punya ${n} MANJA aktif`);}}

  function sourceText(m){return m?.source==='MINI APP'?'MINI APP':'WORK ORDER MANYAR /update';}
  function scheduleText(m){if(!m?.appointment_date)return'';return `${m.appointment_date}${m.appointment_time?' • '+m.appointment_time:''}`;}

  function addAction(card,inet,m){
    if($('.manja-actions',card))return; const actions=document.createElement('div');actions.className='manja-actions';
    const set=document.createElement('button');set.textContent=m?'✏️ UBAH MANJA':'📅 ATUR MANJA';set.onclick=e=>{e.stopPropagation();openEditor(inet,m);};actions.appendChild(set);
    if(m){const cancel=document.createElement('button');cancel.className='danger';cancel.textContent='✓ SELESAIKAN';cancel.onclick=e=>{e.stopPropagation();saveManja(inet,{status:'DONE',appointment_date:'',appointment_time:'',note:m.note||''});};actions.appendChild(cancel);}
    card.appendChild(actions);
  }

  function decorate(){
    const map=itemMap(); $$('#myOrdersList .mini-order').forEach(card=>{
      const inet=findInet(card.textContent); if(!inet)return; const m=map.get(inet);
      card.classList.toggle('manja-order',!!m); card.querySelector('.manja-chip')?.remove(); card.querySelector('.manja-meta')?.remove(); card.querySelector('.manja-actions')?.remove();
      if(m){const chip=document.createElement('div');chip.className='manja-chip';chip.textContent='📅 MANJA';card.prepend(chip);const meta=document.createElement('small');meta.className='manja-meta';meta.style.lineHeight='1.7';meta.innerHTML=`<br>📍 Sumber: ${esc(sourceText(m))}${scheduleText(m)?`<br>🕒 Janji: ${esc(scheduleText(m))}`:''}${m.note?`<br>📝 ${esc(m.note)}`:''}`;card.appendChild(meta);}
      addAction(card,inet,m);
    });
  }

  function ensureModal(){let modal=$('#manjaModal');if(modal)return modal;modal=document.createElement('section');modal.id='manjaModal';modal.className='manja-modal hidden';modal.innerHTML=`<div class="manja-backdrop" data-close-manja></div><article class="manja-sheet"><button class="manja-close" data-close-manja>✕</button><h3>📅 Atur MANJA</h3><p id="manjaInetLabel">-</p><div class="manja-grid"><label class="manja-field"><span>TANGGAL JANJI</span><input id="manjaDate" type="date"></label><label class="manja-field"><span>JAM JANJI</span><input id="manjaTime" type="time"></label><label class="manja-field full"><span>KETERANGAN</span><textarea id="manjaNote" placeholder="Contoh: pelanggan minta besok sore"></textarea></label></div><button id="manjaSave" class="manja-save">SIMPAN MANJA</button></article>`;document.body.appendChild(modal);$$('[data-close-manja]',modal).forEach(x=>x.onclick=()=>modal.classList.add('hidden'));return modal;}

  function openEditor(inet,m){const modal=ensureModal();modal.dataset.inet=inet;$('#manjaInetLabel',modal).textContent=`INET ${inet}${m?` • ${sourceText(m)}`:''}`;$('#manjaDate',modal).value=m?.appointment_date||'';$('#manjaTime',modal).value=m?.appointment_time||'';$('#manjaNote',modal).value=m?.note||'';$('#manjaSave',modal).onclick=()=>saveManja(inet,{status:'ACTIVE',appointment_date:$('#manjaDate',modal).value,appointment_time:$('#manjaTime',modal).value,note:$('#manjaNote',modal).value});modal.classList.remove('hidden');}

  async function saveManja(inet,extra){const id=telegramId();if(!id)return;try{const r=await fetch('/api/manja',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:String(id),service_number:inet,...extra})});const d=await r.json();if(!r.ok||!d.ok)throw new Error(d.message||'Gagal menyimpan MANJA');$('#manjaModal')?.classList.add('hidden');window.showToast?.(extra.status==='ACTIVE'?'📅 MANJA disimpan':'✅ MANJA diselesaikan');await refreshManja();}catch(e){window.showToast?.(`❌ ${e.message}`);}}

  function renderManjaOnly(){const rows=manjaPayload.items||[];const data=orderData();const orderMap=new Map();(data?.areas||[]).forEach(a=>(a.orders||[]).forEach(o=>orderMap.set(String(o.service_number||''),{...o,__area:a.area})));const list=$('#myOrdersList'),count=$('#myOrderCount');if(!list)return;list.replaceChildren();if(count)count.textContent=`${rows.length} MANJA`;const back=document.createElement('button');back.className='tool-action';back.innerHTML='<b>‹ Kembali ke semua order</b><span>📅</span>';back.onclick=()=>{if(typeof renderMyOrderAreas==='function')renderMyOrderAreas(data);else window.renderMyOrderAreas?.(data);};list.appendChild(back);rows.forEach((m,i)=>{const o=orderMap.get(String(m.service_number))||{};const card=document.createElement('div');card.className='mini-order manja-order';card.innerHTML=`<div class="manja-chip">📅 MANJA</div><strong>${i+1}. ${esc(o.customer_name||'-')}</strong><small style="line-height:1.7">🌐 ${esc(m.service_number)}<br>🎫 ${esc(o.ticket_id||'MANUAL')}<br>📍 ${esc(o.__area||'-')}<br>📍 Sumber: ${esc(sourceText(m))}${scheduleText(m)?`<br>🕒 ${esc(scheduleText(m))}`:''}<br>📝 ${esc(m.note||'-')}<br>🏠 ${esc(o.address||'-')}</small>`;addAction(card,m.service_number,m);list.appendChild(card);});}

  function wrap(name){const fn=window[name];if(typeof fn!=='function'||fn.__manja)return;const w=function(...args){const out=fn.apply(this,args);queueMicrotask(()=>{refreshManja();decorate();});return out;};w.__manja=true;window[name]=w;}
  function init(){ensureStyles();ensureBanner();wrap('renderMyOrderAreas');wrap('renderMyOpenArea');refreshManja();const list=$('#myOrdersList');if(list)new MutationObserver(()=>decorate()).observe(list,{childList:true,subtree:true});}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
