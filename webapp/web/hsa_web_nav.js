(function(){
'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state={page:'dashboard',cache:{}};
const navMap={
  'Dashboard':{page:'dashboard',title:'Dashboard',sub:'Monitoring • Analytics • Operations'},
  'Orderanku':{page:'orders',title:'Orderanku',sub:'Daftar order dan status pekerjaan'},
  'Req Open Tiket':{page:'open',title:'Request Open Tiket',sub:'Order OPEN yang membutuhkan tindak lanjut'},
  'Riwayat Order':{page:'history',title:'Riwayat Order',sub:'Riwayat status dan aktivitas order'},
  'Teknisi':{page:'technician',title:'Teknisi',sub:'Performa dan distribusi pekerjaan teknisi'},
  'Area / STO':{page:'area',title:'Area / STO',sub:'Distribusi order berdasarkan wilayah'},
  'Peta Operasi':{page:'map',title:'Peta Operasi',sub:'Lokasi dan sebaran operasi lapangan'},
  'Live Tracking':{page:'tracking',title:'Live Tracking',sub:'Monitoring aktivitas operasi secara live'},
  'Laporan':{page:'report',title:'Laporan',sub:'Ringkasan dan laporan operasional'},
  'Perolehan':{page:'earnings',title:'Perolehan',sub:'Rekap perolehan teknisi'},
  'Rekon / Payroll':{page:'payroll',title:'Rekon / Payroll',sub:'Rekonsiliasi dan data payroll'},
  'Master Teknisi':{page:'master-tech',title:'Master Teknisi',sub:'Data teknisi dan status akses'},
  'Master Data':{page:'master-data',title:'Master Data',sub:'Data referensi operasional'}
};
function ensureStyle(){
 if($('#hsaNavStyle'))return;
 const s=document.createElement('style');s.id='hsaNavStyle';s.textContent=
 '.web-page{position:fixed;inset:72px 0 0 250px;z-index:18;overflow:auto;padding:22px 24px 50px;background:linear-gradient(180deg,#050c16f8,#050914f8);backdrop-filter:blur(12px)}'+
 '.web-page-head{display:flex;align-items:flex-end;justify-content:space-between;gap:15px;margin-bottom:16px}.web-page-head h2{margin:0;font-size:27px}.web-page-head p{margin:5px 0 0;color:#20caff;font-size:9px;letter-spacing:.08em}.web-page-actions{display:flex;gap:8px}.web-btn{border:1px solid #2b526e;border-radius:9px;padding:8px 11px;background:#0a1c2e;color:#b9d0e4;font-size:9px;font-weight:800}.web-btn.primary{background:linear-gradient(135deg,#087ff1,#27cfff);color:#fff;border-color:#2bbcff}.web-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px}.web-card{padding:14px;border:1px solid #1d3a56;border-radius:14px;background:linear-gradient(145deg,#0d2136,#081523)}.web-card small{color:#7990a7;font-size:8px}.web-card strong{display:block;font-size:23px;margin-top:6px}.web-table{width:100%;border-collapse:collapse;font-size:9px}.web-table th{text-align:left;color:#68829c;font-size:8px;font-weight:800;padding:10px 8px;border-bottom:1px solid #23435d}.web-table td{padding:10px 8px;border-bottom:1px solid #31516b24;color:#cbdbea}.web-table tr:hover{background:#10273b55}.web-badge{display:inline-block;padding:4px 7px;border-radius:99px;background:#103957;color:#5edfff;font-size:7px;font-weight:900}.web-empty{padding:45px 15px;text-align:center;color:#70869e;border:1px dashed #29455d;border-radius:13px}.web-detail{display:grid;grid-template-columns:1fr 1fr;gap:11px}.web-list{display:grid;gap:8px}.web-row{display:grid;grid-template-columns:90px 1fr auto;gap:8px;align-items:center;padding:11px;border:1px solid #1d3a56;border-radius:11px;background:#091a2a}.web-row b{font-size:9px}.web-row small{display:block;color:#748ba2;font-size:7px;margin-top:3px}.web-search{width:100%;padding:10px 12px;border:1px solid #294863;border-radius:10px;background:#071725;color:#eaf5ff;outline:0;margin-bottom:10px}.web-map{min-height:430px;border:1px solid #23507355;border-radius:14px;position:relative;overflow:hidden;background:radial-gradient(circle at 50% 50%,#159edf18,transparent 40%),linear-gradient(145deg,#071a2a,#07111d)}.web-map:before{content:"";position:absolute;inset:35px;border:1px solid #3c86ae18;transform:skewY(-7deg) rotate(-2deg);box-shadow:0 0 90px #168fff0c inset}.map-dot{position:absolute;width:12px;height:12px;border-radius:50%;background:#1bcaff;box-shadow:0 0 18px #1bcaff;transform:translate(-50%,-50%)}.map-dot.close{background:#a64cff;box-shadow:0 0 18px #a64cff}.map-dot.update{background:#ffc531;box-shadow:0 0 18px #ffc531}.map-city{position:absolute;color:#bcd2e5;font-size:10px;font-weight:800}.web-overlay{position:fixed;inset:0;z-index:100;background:#0008;display:grid;place-items:center;padding:18px}.web-modal{width:min(620px,100%);max-height:90vh;overflow:auto;border:1px solid #294b68;border-radius:17px;background:#081624;box-shadow:0 30px 100px #000b;padding:18px}.web-modal h3{margin:0 0 10px}.web-modal p{color:#8ca1b6;font-size:9px;line-height:1.6}.web-close{float:right;border:1px solid #294661;border-radius:50%;width:30px;height:30px;background:#0b1d30;color:#fff}@media(max-width:1180px){.web-page{left:215px}.web-cards{grid-template-columns:repeat(2,1fr)}}@media(max-width:760px){.web-page{inset:58px 0 0 0;padding:14px 10px 35px}.web-cards{grid-template-columns:repeat(2,1fr)}.web-detail{grid-template-columns:1fr}.web-page-head{align-items:flex-start}.web-page-head h2{font-size:21px}}';
 document.head.appendChild(s);
}
function hideDashboardSections(){['dashboard','order'].forEach(id=>{const e=document.getElementById(id);if(e)e.dataset.navHidden='1';});}
function restoreDashboard(){const page=$('#webPage');if(page)page.remove();const d=$('#dashboard');const o=$('#order');if(d)d.style.display='block';if(o)o.style.display='none';$('[data-nav-original]').forEach(e=>e.style.display='');}
function pageShell(cfg){
 restoreDashboard(); const d=$('#dashboard');const o=$('#order');if(d)d.style.display='none';if(o)o.style.display='none'; ensureStyle();
 const p=document.createElement('section');p.id='webPage';p.className='web-page';
 p.innerHTML='<div class="web-page-head"><div><h2>'+esc(cfg.title)+'</h2><p>'+esc(cfg.sub)+'</p></div><div class="web-page-actions"><button class="web-btn" id="webRefresh">↻ Refresh</button></div></div><div id="webPageBody"><div class="web-empty">Memuat data...</div></div>';
 document.querySelector('.main').appendChild(p); $('#webRefresh').onclick=()=>loadPage(cfg,true); return p;
}
function dashboard(){
 restoreDashboard(); const d=$('#dashboard');if(d)d.style.display='block';
 const o=$('#order');if(o)o.style.display='none';
 window.scrollTo({top:0,behavior:'smooth'});
}
function fmt(v){return new Intl.NumberFormat('id-ID').format(Number(v)||0)}
function pick(o,...keys){for(const k of keys){if(o&&o[k]!==undefined&&o[k]!==null&&String(o[k])!=='')return o[k]}return '-'}
function arr(d,...keys){for(const k of keys)if(Array.isArray(d?.[k]))return d[k];return []}
function status(o){return String(pick(o,'status','result','state')).toUpperCase()}
function renderRows(items){
 if(!items.length)return '<div class="web-empty">Tidak ada data pada periode ini.</div>';
 return '<div class="web-list">'+items.map((o,i)=>'<div class="web-row"><b>'+esc(pick(o,'service_number','inet','inet_number','serviceNumber','ticket_id'))+'</b><div><b>'+esc(pick(o,'customer_name','customer','name'))+'</b><small>'+esc(pick(o,'address','alamat','area'))+'</small></div><span class="web-badge">'+esc(status(o)||'OPEN')+'</span></div>').join('')+'</div>';
}
async function get(url){
 const r=await fetch(url,{credentials:'same-origin',cache:'no-store'});const d=await r.json().catch(()=>({ok:false}));
 if(r.status===401)throw Error('Sesi login habis. Silakan login kembali.');
 if(!r.ok||d.ok===false)throw Error(d.message||d.error||('HTTP '+r.status));return d;
}
async function loadPage(cfg,refresh){
 const p=pageShell(cfg),body=$('#webPageBody');try{
   let d=state.cache[cfg.page]; if(!d||refresh){
    const endpoint=cfg.page==='orders'||cfg.page==='open'||cfg.page==='history'?'/api/web-orders?force='+(refresh?'1':'0'):
      cfg.page==='report'||cfg.page==='earnings'||cfg.page==='payroll'?'/api/web-report?force='+(refresh?'1':'0'):
      cfg.page==='area'||cfg.page==='technician'||cfg.page==='master-tech'?'/api/web-dashboard?period=all':
      cfg.page==='master-data'?'/api/web-rca':'/api/web-dashboard?period=all';
    d=await get(endpoint);state.cache[cfg.page]=d;
   }
   const items=arr(d,'orders','rows','data','technicians','areas');
   const totals=d.totals||d.summary||d.stats||{};
   let html='<div class="web-cards"><div class="web-card"><small>TOTAL</small><strong>'+fmt(pick(totals,'total','total_order','orders')||items.length)+'</strong></div><div class="web-card"><small>OPEN</small><strong>'+fmt(pick(totals,'open','OPEN')||0)+'</strong></div><div class="web-card"><small>CLOSE</small><strong>'+fmt(pick(totals,'close','CLOSE')||0)+'</strong></div><div class="web-card"><small>UPDATE</small><strong>'+fmt(pick(totals,'update','UPDATE')||0)+'</strong></div></div>';
   if(cfg.page==='map'||cfg.page==='tracking'){
     html+='<div class="web-map"><span class="map-city" style="left:46%;top:48%">SURABAYA</span><span class="map-city" style="left:26%;top:28%">GRESIK</span><span class="map-city" style="left:53%;top:75%">SIDOARJO</span><span class="map-city" style="right:12%;top:62%">BANGIL</span>';
     [[28,42,''],[39,34,''],[53,27,'close'],[61,43,''],[72,35,'update'],[48,57,''],[66,63,'close'],[81,51,'']].forEach(x=>html+='<span class="map-dot '+x[2]+'" style="left:'+x[0]+'%;top:'+x[1]+'%"></span>');html+='</div>';
   } else if(cfg.page==='area'){
     const areas=arr(d,'areas','area_breakdown','breakdown');html+='<div class="panel"><div class="head"><strong>DISTRIBUSI AREA / STO</strong><small>'+items.length+' DATA</small></div><div class="bars" style="height:260px">'+(areas.length?areas.slice(0,12).map(a=>{const name=pick(a,'area','name','sto');const val=Number(pick(a,'count','total','orders')||0);return '<div class="bar-item"><b>'+fmt(val)+'</b><div class="bar-outer"><div class="bar" style="height:'+Math.max(6,Math.min(100,val/Math.max(1,...areas.map(z=>Number(pick(z,'count','total','orders')||0)))*100))+'%"></div></div><small>'+esc(name)+'</small></div>'}).join(''):'<div class="web-empty">Belum ada rincian area.</div>')+'</div></div>';
   } else {
     const filtered=cfg.page==='open'?items.filter(o=>/OPEN|PROGRESS|UPDATE/.test(status(o))):cfg.page==='history'?items.slice(0,100):items;
     html+='<input id="webFilter" class="web-search" placeholder="Cari INET, pelanggan, alamat, teknisi...">'+renderRows(filtered);
   }
   body.innerHTML=html;
   $('#webFilter')?.addEventListener('input',e=>{const q=e.target.value.toUpperCase();$$('.web-row').forEach(r=>r.style.display=r.textContent.toUpperCase().includes(q)?'grid':'none');});
 }catch(e){body.innerHTML='<div class="web-empty">❌ '+esc(e.message)+'<br><br><button class="web-btn primary" id="retryPage">Coba lagi</button></div>';$('#retryPage').onclick=()=>loadPage(cfg,true);}
}
function activate(label){
 const cfg=navMap[label];if(!cfg)return;
 $$('.nav button').forEach(b=>b.classList.toggle('active',b.textContent.trim()===label));
 state.page=cfg.page;
 if(cfg.page==='dashboard'){dashboard();return;}
 loadPage(cfg,false);
 if(window.innerWidth<=760)document.body.classList.remove('menu-open');
}
function bind(){
 if(!document.documentElement.dataset.hsaNavCapture){document.documentElement.dataset.hsaNavCapture='1';document.addEventListener('click',e=>{const b=e.target.closest('.nav button[data-target]');if(!b)return;e.preventDefault();e.stopPropagation();activate(b.textContent.trim());},true);}
 document.querySelectorAll('.nav button[data-target]').forEach(b=>{
   if(b.dataset.webBound)return;b.dataset.webBound='1';
   b.addEventListener('click',e=>{e.preventDefault();activate(b.textContent.trim());});
 });
 const menu=$('#menu');if(menu&&!menu.dataset.bound){menu.dataset.bound='1';menu.onclick=()=>document.body.classList.toggle('menu-open');}
 const logout=$('#logout');if(logout&&!logout.dataset.webBound){logout.dataset.webBound='1';logout.onclick=async()=>{try{await fetch('/api/web-logout',{method:'POST',credentials:'same-origin'});}finally{location.href='/website';}};}
}
ensureStyle();bind();window.addEventListener('resize',bind);
})();