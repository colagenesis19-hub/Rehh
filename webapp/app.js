const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }

const state = { area:'ALL', period:'daily', query:'', payload:null, me:null, myOpenOrders:null, workflow:null };
const fmt = v => new Intl.NumberFormat('id-ID').format(Number(v || 0));
const shortDay = v => String(v || '').slice(0,3).toUpperCase();
const normName = v => String(v || '').toUpperCase().replace(/[^A-Z0-9]+/g,' ').trim().replace(/\s+/g,' ');
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function telegramUser(){ return tg?.initDataUnsafe?.user || null; }
function telegramName(){ const u=telegramUser(); return u ? [u.first_name,u.last_name].filter(Boolean).join(' ').trim() : ''; }
function setWelcome(){
  document.querySelector('#welcomeName').textContent = telegramName() || 'Teknisi';
  const now=new Date();
  const date=new Intl.DateTimeFormat('id-ID',{weekday:'long',day:'numeric',month:'long',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(now).replace(' pukul ',' • ');
  document.querySelector('#currentDate').textContent=`▣ ${date} WIB`;
}
function periodText(){ return state.period==='daily'?'Hari Ini':state.period==='weekly'?'Minggu Ini':'Keseluruhan'; }
function selectedRows(){ const rows=state.payload?.leaderboard||[]; const q=state.query.trim().toUpperCase(); return q?rows.filter(i=>String(i.name||'').toUpperCase().includes(q)||String(i.nik||'').toUpperCase().includes(q)):rows; }

function renderSummary(){
  const s=state.payload?.summary||{}, close=Number(s.total_close||0), tech=Number(s.active_technicians||0), avg=Number(s.average_close||0);
  document.querySelector('#totalClose').textContent=fmt(close); document.querySelector('#activeTechnicians').textContent=fmt(tech); document.querySelector('#averageClose').textContent=avg.toFixed(1).replace('.0','');
  document.querySelector('#periodLabel').textContent=state.payload?.period_label||periodText(); document.querySelector('#periodPillLabel').textContent=periodText();
  document.querySelector('#activeAreaLabel').textContent=state.area==='MYR'?'MANYAR':state.area==='JGR'?'JAGIR':'SEMUA';
  document.querySelector('#ringValue').textContent=fmt(close); document.querySelector('#ringClose').textContent=fmt(close); document.querySelector('#ringTech').textContent=fmt(tech); document.querySelector('#ringAvg').textContent=avg.toFixed(1).replace('.0','');
  document.querySelector('#progressRing').style.setProperty('--p',`${Math.min(360,Math.max(20,close*7))}deg`);
}
function renderTrend(){
  const chart=document.querySelector('#trendChart'), trend=state.payload?.trend||[], max=Math.max(1,...trend.map(i=>Number(i.total||0)));
  chart.replaceChildren(); document.querySelector('#trendTotal').textContent=`${fmt(trend.reduce((a,i)=>a+Number(i.total||0),0))} close`;
  trend.forEach(item=>{ const col=document.createElement('div'); col.className='trend-col'; const h=Math.max(5,Math.round(Number(item.total||0)/max*100)); col.innerHTML=`<span class="trend-value">${fmt(item.total)}</span><div class="trend-bar-wrap"><div class="trend-bar" style="height:${h}%"></div></div><span class="trend-label">${shortDay(item.label)}</span>`; chart.appendChild(col); });
}
function renderLeaderboard(){
  const list=document.querySelector('#leaderboard'), empty=document.querySelector('#emptyState'), tpl=document.querySelector('#leaderTemplate'), rows=selectedRows();
  list.replaceChildren(); document.querySelector('#resultCount').textContent=`${rows.length} teknisi`; empty.classList.toggle('hidden',rows.length>0);
  rows.slice(0,12).forEach((item,index)=>{ const node=tpl.content.cloneNode(true), btn=node.querySelector('.leader-row'); node.querySelector('.rank').textContent=String(index+1); node.querySelector('.leader-name').textContent=item.name||'-'; node.querySelector('.leader-meta').textContent=`${item.nik||'-'} • ${item.area_label||item.sto||'SEMUA'}`; node.querySelector('.leader-score').textContent=fmt(item.total); btn.addEventListener('click',()=>openTechnician(item.key||item.nik)); list.appendChild(node); });
}
function renderRecentActivity(){
  const c=document.querySelector('#recentActivity'), rows=state.payload?.leaderboard||[]; c.replaceChildren();
  if(!rows.length){c.innerHTML='<div class="empty"><p>Belum ada aktivitas pada filter ini.</p></div>';return;}
  rows.slice(0,3).forEach((item,i)=>{const r=document.createElement('div');r.className='activity-item';r.innerHTML=`<span class="activity-bullet">${i===0?'✓':'↗'}</span><div><strong>${esc(item.name||'-')}</strong><small>${fmt(item.total)} close • ${esc(item.area_label||item.sto||'SEMUA')}</small></div>`;c.appendChild(r);});
}
function renderRca(){
  const box=document.querySelector('.rca-panel .placeholder-chart'); if(!box)return; const s=state.payload?.rca_summary||{total:0,items:[]}, items=s.items||[];
  if(!s.total||!items.length){box.innerHTML='<div class="placeholder-pie">!</div><div><strong>Belum ada RCA</strong><p>Belum ditemukan RCA pada Google Sheet maupun Grup Kendala untuk filter area ini.</p></div>';return;}
  const pal=['#8d2dce','#ee4f5d','#ffb62c','#2584ef','#2bd08f','#57e6ff','#7e74ff','#ff7d20','#8ca2bd']; let cur=0; const stops=[];
  items.forEach((it,i)=>{const start=cur;cur+=Number(it.percent||0);stops.push(`${pal[i%pal.length]} ${start}% ${cur}%`);}); if(cur<100)stops.push(`#1a2e45 ${cur}% 100%`);
  const legend=items.slice(0,7).map((it,i)=>`<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin:7px 0;font-size:10px"><span style="display:flex;align-items:center;gap:7px;color:#b7c8d9"><i style="width:8px;height:8px;border-radius:50%;background:${pal[i%pal.length]};display:inline-block"></i>${esc(it.label)}</span><strong style="white-space:nowrap">${fmt(it.count)} <span style="color:#71879f;font-weight:500">(${it.percent}%)</span></strong></div>`).join('');
  box.innerHTML=`<div class="placeholder-pie" style="width:180px;height:180px;flex:0 0 180px;font-size:24px;background:conic-gradient(${stops.join(',')});box-shadow:inset 0 0 0 38px #0a1929">${fmt(s.total)}</div><div style="min-width:0;flex:1"><strong>${fmt(s.total)} RCA tercatat</strong><p style="margin:4px 0 8px">${esc(s.source||'Google Sheet + Grup Kendala')} • Sheet ${fmt(s.sheet_count)} • Kendala ${fmt(s.kendala_count)}</p>${legend}</div>`;
}
function render(){renderSummary();renderTrend();renderLeaderboard();renderRecentActivity();renderRca();}
function resolveMeFromPayload(){const n=normName(telegramName());return n?(state.payload?.leaderboard||[]).find(i=>normName(i.name)===n)||null:null;}
async function loadDashboard(){
  try{const p=new URLSearchParams({area:state.area,period:state.period}),r=await fetch(`/api/dashboard?${p}`,{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);state.payload=await r.json();state.me=resolveMeFromPayload()||state.me;}catch(e){console.error(e);state.payload={summary:{},trend:[],leaderboard:[],rca_summary:{total:0,items:[]}};}render();
}
async function fetchTechnician(key,area='ALL'){const r=await fetch(`/api/technician?${new URLSearchParams({key,area})}`,{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json();}
async function openTechnician(key){
  try{const d=await fetchTechnician(key,state.area);document.querySelector('#detailName').textContent=d.name||'-';document.querySelector('#detailNik').textContent=`NIK ${d.nik||'-'}`;document.querySelector('#detailDaily').textContent=fmt(d.daily);document.querySelector('#detailWeekly').textContent=fmt(d.weekly);document.querySelector('#detailAll').textContent=fmt(d.all);document.querySelector('#detailCount').textContent=`${(d.orders||[]).length} data`;const c=document.querySelector('#detailOrders');c.replaceChildren();(d.orders||[]).forEach(o=>{const r=document.createElement('div');r.className='order-row';r.innerHTML=`<div><strong>${esc(o.service_number||'-')}</strong><small>${esc(o.ticket_id||'MANUAL')} • ${esc(o.area_label||o.sto||'-')}</small></div><span class="order-date">${esc(o.date_label||'-')}</span>`;c.appendChild(r);});document.querySelector('#detailPanel').classList.remove('hidden');}catch(e){showToast('Detail teknisi gagal dimuat');}
}

async function fetchMyOpenOrders(force=false){
  const u=telegramUser(); if(!u?.id)throw new Error('Mini App harus dibuka dari Telegram.'); const p=new URLSearchParams({telegram_id:String(u.id)}); if(force)p.set('force','1'); const r=await fetch(`/api/my-open-orders?${p}`,{cache:'no-store'}); const d=await r.json(); if(!r.ok||!d.ok)throw new Error(d.message||`HTTP ${r.status}`); state.myOpenOrders=d; return d;
}
function setMyOrderSummary(total,areas){const boxes=document.querySelectorAll('#myOrderSummary > div'),labels=['ORDER OPEN','AREA AKTIF','SUMBER'],vals=[fmt(total),fmt(areas),'SHEET'];boxes.forEach((b,i)=>{b.querySelector('span').textContent=labels[i];b.querySelector('strong').textContent=vals[i];});}
function renderMyOrderAreas(d){const list=document.querySelector('#myOrdersList'),count=document.querySelector('#myOrderCount');list.replaceChildren();count.textContent=`${d.total_open||0} OPEN`;if(!d.areas?.length){list.innerHTML='<div class="empty"><p>✅ Tidak ada order OPEN dari Google Sheets.</p></div>';return;}d.areas.forEach(a=>{const b=document.createElement('button');b.className='tool-action';b.innerHTML=`<div><b>📍 ${esc(a.area)}</b><small style="display:block;margin-top:4px;color:#758ba2">🟢 Open: ${fmt(a.open)} | 🔴 Close: ${fmt(a.close)}${a.update?` | 🟡 Update: ${fmt(a.update)}`:''}</small></div><span>${fmt(a.open)} ›</span>`;b.addEventListener('click',()=>renderMyOpenArea(a));list.appendChild(b);});}
function renderMyOpenArea(a){const list=document.querySelector('#myOrdersList'),count=document.querySelector('#myOrderCount');list.replaceChildren();count.textContent=`${a.orders?.length||0} OPEN`;const back=document.createElement('button');back.className='tool-action';back.innerHTML='<b>‹ Kembali ke daftar area</b><span>📍</span>';back.addEventListener('click',()=>renderMyOrderAreas(state.myOpenOrders));list.appendChild(back);(a.orders||[]).forEach((o,i)=>{const c=document.createElement('div');c.className='mini-order';c.innerHTML=`<strong>${i+1}. ${esc(o.customer_name||'-')}</strong><small style="line-height:1.65">🎫 ${esc(o.ticket_id||'MANUAL')}<br>🌐 ${esc(o.service_number||'-')}<br>📞 ${esc(o.customer_phone||'-')}<br>⚡ ${esc(o.package||'-')}<br>📡 ONU RX: ${esc(o.onu_rx||'-')}<br>📝 RCA: ${esc(o.rca||'-')}<br>🏠 ${esc(o.address||'-')}</small>`;list.appendChild(c);});}
async function loadMyOpenOrders(force=false){const id=document.querySelector('#ordersIdentity'),list=document.querySelector('#myOrdersList');id.textContent='🔄 Membaca Google Sheets terbaru...';list.innerHTML='<div class="empty"><p>Memuat order OPEN...</p></div>';try{const d=await fetchMyOpenOrders(force);id.textContent=`${d.technician.name} • NIK ${d.technician.nik||'-'} • ${d.source}`;setMyOrderSummary(d.total_open,d.active_areas);renderMyOrderAreas(d);}catch(e){id.textContent='❌ Gagal membaca Orderanku dari Google Sheets.';list.innerHTML=`<div class="empty"><p>${esc(e.message)}</p></div>`;setMyOrderSummary(0,0);}}

const WF_LABELS={ticket_id:'TIKET ID',service_number:'NO SERVICE',voip_number:'NO VOIP',old_sn:'SN ONT LAMA',new_sn:'SN ONT BARU',ont_type:'TYPE ONT',sto:'STO',valins_id:'VALINS ID',result:'RESULT',config_description:'KETERANGAN CONFIG',report_description:'KETERANGAN REPORT/STO',customer_name:'NAMA PELANGGAN',address:'ALAMAT',customer_phone:'CP / NO HP'};
const WF_REQUIRED={config:['ticket_id','service_number','voip_number','old_sn','new_sn','ont_type','sto','config_description'],report:['ticket_id','service_number','old_sn','new_sn','valins_id','result','report_description','address','customer_phone'],sto:['ticket_id','service_number','old_sn','new_sn','ont_type','sto','valins_id','report_description','customer_name','address','customer_phone']};
WF_REQUIRED.lengkap=[...new Set([...WF_REQUIRED.config,...WF_REQUIRED.report,...WF_REQUIRED.sto])];
function workflowHost(){return document.querySelector('#inputPage .tool-list');}
function renderWorkflowHome(){
  state.workflow=null; const sub=document.querySelector('#inputPage .tool-sub'); if(sub)sub.textContent='Pilih workflow, lalu pilih order OPEN dari Google Sheet. Data yang sudah tersedia akan terisi otomatis; teknisi hanya mengisi yang masih kosong.';
  const host=workflowHost(); if(!host)return; host.innerHTML=['lengkap','config','report','sto'].map(a=>`<article class="tool-card"><strong>${a.toUpperCase()}</strong><small>${a==='lengkap'?'CONFIG + REPORT + STO sekaligus':a==='config'?'Format konfigurasi replacement ONT':a==='report'?'Laporan hasil pekerjaan':'Rekap pekerjaan ke STO'}</small><button class="tool-action" data-workflow="${a}"><b>${a.toUpperCase()}</b><span>Pilih order ›</span></button></article>`).join('');host.querySelectorAll('[data-workflow]').forEach(b=>b.addEventListener('click',()=>startWorkflow(b.dataset.workflow)));
}
async function startWorkflow(action){
  state.workflow={action,order:null}; const host=workflowHost(); host.innerHTML='<div class="empty"><p>🔄 Membaca order OPEN dari Google Sheet...</p></div>';
  try{const d=state.myOpenOrders||await fetchMyOpenOrders(false); const rows=[];(d.areas||[]).forEach(a=>(a.orders||[]).forEach(o=>rows.push({...o,area:a.area}))); renderWorkflowOrders(action,rows);}catch(e){host.innerHTML=`<div class="empty"><p>❌ ${esc(e.message)}</p><button class="tool-action" id="wfBack"><b>Kembali</b><span>‹</span></button></div>`;document.querySelector('#wfBack')?.addEventListener('click',renderWorkflowHome);}
}
function renderWorkflowOrders(action,rows){
  const host=workflowHost(); host.innerHTML=`<article class="tool-card"><strong>${action.toUpperCase()} • PILIH ORDER</strong><small>${rows.length} order OPEN tersedia</small><div class="search-wrap" style="margin-top:12px"><span>⌕</span><input id="wfSearch" placeholder="Cari INET, tiket, nama, alamat..." /></div><div id="wfOrders" class="mini-order-list"></div><button class="tool-action" id="wfBack"><b>‹ Ganti workflow</b><span>${action.toUpperCase()}</span></button></article>`;
  const draw=q=>{const box=document.querySelector('#wfOrders');box.replaceChildren();const n=normName(q);const filtered=rows.filter(o=>!n||normName(`${o.service_number} ${o.ticket_id} ${o.customer_name} ${o.address} ${o.area}`).includes(n));filtered.slice(0,80).forEach(o=>{const b=document.createElement('button');b.className='tool-action';b.innerHTML=`<div><b>🌐 ${esc(o.service_number)}</b><small style="display:block;margin-top:4px;color:#758ba2">${esc(o.customer_name||'-')} • ${esc(o.area||'-')}<br>${esc(o.address||'-')}</small></div><span>›</span>`;b.addEventListener('click',()=>renderWorkflowForm(action,o));box.appendChild(b);});if(!filtered.length)box.innerHTML='<div class="empty"><p>Order tidak ditemukan.</p></div>';};
  draw('');document.querySelector('#wfSearch').addEventListener('input',e=>draw(e.target.value));document.querySelector('#wfBack').addEventListener('click',renderWorkflowHome);
}
function workflowSeed(order){return {ticket_id:order.ticket_id==='MANUAL'?'':order.ticket_id||'',service_number:order.service_number||'',customer_name:order.customer_name||'',address:order.address||'',customer_phone:order.customer_phone||'',voip_number:'',old_sn:'',new_sn:'',ont_type:'',sto:state.myOpenOrders?.technician?.sto||'',valins_id:'',result:'',config_description:'',report_description:''};}
function renderWorkflowForm(action,order){
  state.workflow={action,order}; const data=workflowSeed(order), required=WF_REQUIRED[action], missing=required.filter(k=>!String(data[k]||'').trim()); const host=workflowHost();
  const known=required.filter(k=>String(data[k]||'').trim()).map(k=>`<div style="display:flex;justify-content:space-between;gap:10px;padding:7px 0;border-bottom:1px solid rgba(87,119,153,.13);font-size:10px"><span style="color:#8298b2">${WF_LABELS[k]}</span><strong style="text-align:right">${esc(data[k])}</strong></div>`).join('');
  const fields=missing.map(k=>`<label style="display:block;margin:11px 0"><span style="display:block;color:#9cb0c5;font-size:10px;margin-bottom:5px">${WF_LABELS[k]}</span><input name="${k}" required placeholder="Isi ${WF_LABELS[k]}${['valins_id','voip_number'].includes(k)?' atau -':''}" style="width:100%;border:1px solid #2a496b;border-radius:12px;background:#081727;color:#fff;padding:12px;outline:none" /></label>`).join('');
  host.innerHTML=`<article class="tool-card"><strong>${action.toUpperCase()} • ${esc(order.service_number)}</strong><small>${esc(order.customer_name||'-')} • ${esc(order.address||'-')}</small>${known?`<div style="margin-top:12px">${known}</div>`:''}<form id="wfForm" style="margin-top:10px">${fields||'<div class="info-box"><span>✓</span><p>Semua data yang dibutuhkan sudah tersedia.</p></div>'}<button class="tool-action" type="submit"><b>BUAT ${action.toUpperCase()}</b><span>Proses ›</span></button></form><button class="tool-action" id="wfBackOrders"><b>‹ Pilih order lain</b><span>🌐</span></button></article>`;
  document.querySelector('#wfBackOrders').addEventListener('click',()=>startWorkflow(action)); document.querySelector('#wfForm').addEventListener('submit',e=>{e.preventDefault();const fd=new FormData(e.currentTarget);missing.forEach(k=>data[k]=String(fd.get(k)||'').trim()||'-');renderWorkflowResult(action,order,data);});
}
function line(label,value,width=17){return `${label.padEnd(width,' ')}: ${value||'-'}`;}
function generateWorkflowOutputs(action,data){
  const tech=state.myOpenOrders?.technician||{nik:'-',name:telegramName()||'-',sto:''}, sto=(tech.sto||data.sto||'-').toUpperCase(), out=[];
  if(action==='config'||action==='lengkap')out.push(['CONFIG',['===========================','/CONFIG REPLACEMENT ONT','===========================','',line('NIK',tech.nik),line('NAMA',tech.name),line('TIKET ID',data.ticket_id),line('NO SERVICE',data.service_number),line('NO VOIP',data.voip_number),line('SN ONT LAMA',data.old_sn),line('SN ONT BARU',data.new_sn),line('TYPE ONT',data.ont_type),line('STO',sto),line('KETERANGAN',data.config_description)].join('\n')]);
  if(action==='report'||action==='lengkap'){const t=new Date(),date=`${String(t.getDate()).padStart(2,'0')}/${String(t.getMonth()+1).padStart(2,'0')}/${t.getFullYear()}`;out.push(['REPORT',['=============================','/REPORT REPLACEMENT ONT','=============================',line('TANGGAL',date),line('NIK',tech.nik),line('NAMA',tech.name),line('TIKET ID',data.ticket_id),line('NO INET',data.service_number),line('SN ONT LAMA',data.old_sn),line('SN ONT BARU',data.new_sn),line('VALINS ID',data.valins_id),line('RESULT',data.result),line('KETERANGAN',data.report_description),line('ALAMAT',data.address),line('CP',data.customer_phone),'============================='].join('\n')]);}
  if(action==='sto'||action==='lengkap')out.push(['STO',[`/STO : ${sto}`,`TIKET : ${data.ticket_id||'-'}`,`NO SERVICE : ${data.service_number||'-'}`,`SN ONT LAMA : ${data.old_sn||'-'}`,`SN ONT BARU : ${data.new_sn||'-'}`,`TYPE ONT : ${data.ont_type||'-'}`,`STO : ${sto}`,`VALIN ID : ${data.valins_id||'-'}`,`KETERANGAN : ${data.report_description||'-'}`,`NAMA : ${data.customer_name||'-'}`,`ALAMAT : ${data.address||'-'}`,`CP : ${data.customer_phone||'-'}`,`NIK NAMA TEKNISI : ${tech.nik||'-'} | ${tech.name||'-'}`].join('\n')]);
  return out;
}
function renderWorkflowResult(action,order,data){
  const host=workflowHost(), outputs=generateWorkflowOutputs(action,data); host.innerHTML=`<article class="tool-card"><strong>✅ ${action.toUpperCase()} SIAP</strong><small>INET ${esc(order.service_number)} • ${esc(order.customer_name||'-')}</small><div id="wfOutputs" style="margin-top:12px"></div><button class="tool-action" id="wfAnother"><b>Kerjakan order lain</b><span>＋</span></button><button class="tool-action" id="wfHome"><b>Kembali ke menu Input</b><span>‹</span></button></article>`;
  const box=document.querySelector('#wfOutputs'); outputs.forEach(([kind,text])=>{const c=document.createElement('div');c.style.marginBottom='12px';c.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px"><strong>${kind}</strong><button class="round-btn" style="width:auto;height:32px;border-radius:10px;padding:0 10px;font-size:10px">Salin</button></div><pre style="white-space:pre-wrap;word-break:break-word;background:#06111f;border:1px solid #203a57;border-radius:12px;padding:12px;font-size:10px;line-height:1.5;color:#dceaff;margin:0">${esc(text)}</pre>`;c.querySelector('button').addEventListener('click',()=>copyText(text,`${kind} tersalin`));box.appendChild(c);});document.querySelector('#wfAnother').addEventListener('click',()=>startWorkflow(action));document.querySelector('#wfHome').addEventListener('click',renderWorkflowHome);
}

async function loadReportData(){const candidate=state.me||resolveMeFromPayload(),el=document.querySelector('#reportIdentity');if(!candidate){el.textContent='Data akun Telegram ini belum cocok dengan nama teknisi pada REPORT.';return;}try{const d=await fetchTechnician(candidate.key||candidate.nik,'ALL');el.textContent=`${d.name||candidate.name} • NIK ${d.nik||candidate.nik||'-'}`;document.querySelectorAll('#reportSummary strong').forEach((x,i)=>x.textContent=fmt([d.daily,d.weekly,d.all][i]));}catch(e){el.textContent='Gagal memuat data teknisi.';}}
function openPage(id){document.querySelectorAll('.page-view').forEach(p=>p.classList.toggle('hidden',p.id!==id));document.querySelectorAll('.nav-item[data-page]').forEach(n=>n.classList.toggle('active',n.dataset.page===id));if(id==='ordersPage')loadMyOpenOrders();if(id==='reportsPage')loadReportData();if(id==='inputPage')renderWorkflowHome();window.scrollTo({top:0,behavior:'smooth'});}
function selectArea(v){state.area=v;document.querySelectorAll('.segment').forEach(i=>i.classList.toggle('active',i.dataset.area===v));loadDashboard();}
function showToast(text){const t=document.querySelector('#toast');t.textContent=text;t.classList.remove('hidden');clearTimeout(showToast.timer);showToast.timer=setTimeout(()=>t.classList.add('hidden'),1800);}
async function copyText(text,msg='Tersalin'){try{await navigator.clipboard.writeText(text);}catch{const a=document.createElement('textarea');a.value=text;document.body.appendChild(a);a.select();document.execCommand('copy');a.remove();}showToast(msg);tg?.HapticFeedback?.impactOccurred('light');}
async function copyCommand(cmd){return copyText(cmd,`${cmd} tersalin`);}
function closeOverlays(){document.querySelector('#drawer').classList.add('hidden');document.querySelector('#moreMenu').classList.add('hidden');}

document.querySelectorAll('.segment').forEach(b=>b.addEventListener('click',()=>selectArea(b.dataset.area)));
document.querySelectorAll('[data-area-shortcut]').forEach(b=>b.addEventListener('click',()=>selectArea(b.dataset.areaShortcut)));
document.querySelectorAll('.period').forEach(b=>b.addEventListener('click',()=>{state.period=b.dataset.period;document.querySelectorAll('.period').forEach(i=>i.classList.toggle('active',i===b));loadDashboard();}));
document.querySelector('#searchInput').addEventListener('input',e=>{state.query=e.target.value;renderLeaderboard();});
document.querySelectorAll('.nav-item[data-page]').forEach(b=>b.addEventListener('click',()=>openPage(b.dataset.page)));
document.querySelectorAll('[data-back-dashboard]').forEach(b=>b.addEventListener('click',()=>openPage('dashboardPage')));
document.querySelectorAll('[data-close-detail]').forEach(i=>i.addEventListener('click',()=>document.querySelector('#detailPanel').classList.add('hidden')));
document.querySelectorAll('[data-copy-command]').forEach(b=>b.addEventListener('click',()=>copyCommand(b.dataset.copyCommand)));
document.querySelector('#menuButton')?.addEventListener('click',()=>document.querySelector('#drawer').classList.remove('hidden'));
document.querySelectorAll('[data-close-drawer]').forEach(i=>i.addEventListener('click',closeOverlays));
document.querySelectorAll('[data-drawer-page]').forEach(b=>b.addEventListener('click',()=>{closeOverlays();openPage(b.dataset.drawerPage);}));
document.querySelector('#moreButton')?.addEventListener('click',()=>document.querySelector('#moreMenu').classList.remove('hidden'));
document.querySelectorAll('[data-close-more]').forEach(i=>i.addEventListener('click',closeOverlays));
document.querySelector('#refreshButton')?.addEventListener('click',async()=>{closeOverlays();await loadDashboard();if(!document.querySelector('#ordersPage').classList.contains('hidden'))await loadMyOpenOrders(true);showToast('Data diperbarui');});
document.querySelector('#closeMiniAppButton')?.addEventListener('click',()=>tg?.close?.());

setWelcome(); renderWorkflowHome(); loadDashboard();