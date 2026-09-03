// Personal report dashboard for the logged-in Telegram technician.
let reportPeriod = 'weekly';
let reportPayload = null;

function reportDateKey(order) {
  return String(order.raw_day || order.message_day || '').slice(0, 10);
}
function localYmd(date) {
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}
function shortDateLabel(ymd) {
  if (!ymd) return '-';
  const d = new Date(`${ymd}T00:00:00`);
  if (Number.isNaN(d.getTime())) return ymd;
  return new Intl.DateTimeFormat('id-ID',{day:'2-digit',month:'short'}).format(d).replace('.','');
}
function weekBounds() {
  const now = new Date();
  const day = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const daysSinceFriday = (day.getDay()+2)%7;
  const start = new Date(day); start.setDate(day.getDate()-daysSinceFriday);
  const end = new Date(start); end.setDate(start.getDate()+6);
  return {start,end};
}

function buildReportPage() {
  const page = document.querySelector('#reportsPage');
  if (!page) return;
  page.innerHTML = `
    <header class="app-header">
      <button class="round-btn" data-back-dashboard>‹</button>
      <div class="brand-center"><strong>Laporan</strong><small>rekap pekerjaan</small></div>
      <span class="round-btn ghost">▥</span>
    </header>
    <h1 class="tool-title">Rekap Pekerjaan</h1>
    <p class="tool-sub" id="reportIdentity">Memuat data teknisi...</p>

    <div id="reportSummary" class="my-summary report-summary-tabs">
      <button type="button" data-report-summary="daily"><span>HARI INI</span><strong>0</strong></button>
      <button type="button" data-report-summary="weekly" class="active"><span>MINGGU</span><strong>0</strong></button>
      <button type="button" data-report-summary="all"><span>KESELURUHAN</span><strong>0</strong></button>
    </div>

    <section class="panel" style="margin-bottom:12px">
      <div class="panel-head">
        <div><span class="panel-icon">⌁</span><strong id="personalTrendTitle">GRAFIK PEROLEHAN MINGGU INI</strong></div>
        <span id="personalTrendTotal" class="panel-meta">0 order</span>
      </div>
      <div id="personalTrendChart" class="report-line-chart"></div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <div><span class="panel-icon">✓</span><strong>SUDAH DIKERJAKAN</strong></div>
        <span id="reportOrderCount" class="panel-meta">0 data</span>
      </div>
      <div class="segmented" style="margin:12px 0">
        <button class="report-period" data-report-period="daily">HARI INI</button>
        <button class="report-period active" data-report-period="weekly">MINGGU</button>
        <button class="report-period" data-report-period="all">SEMUA</button>
      </div>
      <div id="reportOrders" class="mini-order-list"></div>
    </section>`;

  const setPeriod = value => {
    reportPeriod = value;
    page.querySelectorAll('[data-report-period]').forEach(b=>b.classList.toggle('active',b.dataset.reportPeriod===value));
    page.querySelectorAll('[data-report-summary]').forEach(b=>b.classList.toggle('active',b.dataset.reportSummary===value));
    renderPersonalTrend();
    renderPersonalReportOrders();
  };
  page.querySelector('[data-back-dashboard]')?.addEventListener('click',()=>openPage('dashboardPage'));
  page.querySelectorAll('[data-report-period]').forEach(b=>b.addEventListener('click',()=>setPeriod(b.dataset.reportPeriod)));
  page.querySelectorAll('[data-report-summary]').forEach(b=>b.addEventListener('click',()=>setPeriod(b.dataset.reportSummary)));

  if (!document.querySelector('#reportDashboardStyles')) {
    const style=document.createElement('style');
    style.id='reportDashboardStyles';
    style.textContent=`
      .report-summary-tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
      .report-summary-tabs button{appearance:none;border:1px solid #263e5b;background:linear-gradient(180deg,#0d1d31,#091726);border-radius:18px;padding:15px 10px;color:#eef6ff;text-align:center;transition:transform .25s cubic-bezier(.2,.8,.2,1),border-color .25s,box-shadow .25s,background .25s}
      .report-summary-tabs button span{display:block;color:#8094ac;font-size:10px}.report-summary-tabs button strong{display:block;font-size:28px;margin-top:6px}
      .report-summary-tabs button.active{transform:translateY(-2px);border-color:#2f8eff;background:linear-gradient(180deg,rgba(24,91,155,.42),rgba(10,31,51,.96));box-shadow:0 10px 26px rgba(36,135,255,.18),inset 0 1px 0 rgba(255,255,255,.05)}
      .report-line-chart{height:220px;position:relative;overflow:hidden;padding-top:4px}.report-line-chart svg{width:100%;height:100%;display:block;overflow:visible}
      .report-grid{stroke:rgba(122,158,194,.13);stroke-width:1}.report-line{fill:none;stroke:url(#reportStroke);stroke-width:4;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:1;stroke-dashoffset:1;animation:reportDraw .85s cubic-bezier(.2,.75,.2,1) forwards}.report-area{fill:url(#reportArea);opacity:0;animation:reportAreaIn .55s .18s ease forwards}.report-dot{fill:#eaf7ff;stroke:#2d91ff;stroke-width:4}.report-value{fill:#eef7ff;font-size:14px;font-weight:800}.report-label{fill:#7f96af;font-size:12px;font-weight:700}.report-point{opacity:0;animation:reportPointIn .3s ease forwards;animation-delay:calc(.25s + var(--i)*.05s)}
      @keyframes reportDraw{to{stroke-dashoffset:0}}@keyframes reportAreaIn{to{opacity:1}}@keyframes reportPointIn{to{opacity:1}}
      @media(max-width:430px){.report-summary-tabs{gap:7px}.report-summary-tabs button{padding:12px 6px}.report-summary-tabs button strong{font-size:24px}.report-line-chart{height:205px}}
    `;
    document.head.appendChild(style);
  }
}

function trendRowsForPeriod() {
  const orders = reportPayload?.orders || [];
  const now = new Date();
  if (reportPeriod === 'daily') {
    const today=localYmd(now);
    return [{label:'Hari ini',key:today,total:orders.filter(o=>reportDateKey(o)===today).length}];
  }
  if (reportPeriod === 'weekly') {
    const {start}=weekBounds();
    return Array.from({length:7},(_,i)=>{
      const d=new Date(start); d.setDate(start.getDate()+i); const key=localYmd(d);
      return {key,label:new Intl.DateTimeFormat('id-ID',{weekday:'short'}).format(d).replace('.',''),total:orders.filter(o=>reportDateKey(o)===key).length};
    });
  }
  const counts=new Map();
  orders.forEach(o=>{const key=reportDateKey(o);if(key)counts.set(key,(counts.get(key)||0)+1);});
  return [...counts.entries()].sort((a,b)=>a[0].localeCompare(b[0])).map(([key,total])=>({key,label:shortDateLabel(key),total}));
}
function reportLinePath(points){
  if(!points.length)return''; if(points.length===1)return`M ${points[0][0]} ${points[0][1]}`;
  let d=`M ${points[0][0]} ${points[0][1]}`;
  for(let i=1;i<points.length;i++){const [x0,y0]=points[i-1],[x1,y1]=points[i],mx=(x0+x1)/2;d+=` C ${mx} ${y0}, ${mx} ${y1}, ${x1} ${y1}`;} return d;
}
function renderPersonalTrend() {
  const chart=document.querySelector('#personalTrendChart'); if(!chart)return;
  const rows=trendRowsForPeriod();
  const total=rows.reduce((s,r)=>s+Number(r.total||0),0);
  const title=document.querySelector('#personalTrendTitle');
  if(title)title.textContent=reportPeriod==='daily'?'GRAFIK PEROLEHAN HARI INI':reportPeriod==='weekly'?'GRAFIK PEROLEHAN MINGGU INI':'GRAFIK PEROLEHAN KESELURUHAN';
  document.querySelector('#personalTrendTotal').textContent=`${fmt(total)} order`;
  if(!rows.length){chart.innerHTML='<div class="empty"><p>Belum ada data grafik.</p></div>';return;}
  const W=700,H=210,left=38,right=24,top=28,bottom=42,base=H-bottom,max=Math.max(1,...rows.map(r=>Number(r.total||0)));
  const step=rows.length>1?(W-left-right)/(rows.length-1):0;
  const points=rows.map((r,i)=>[left+i*step,base-(Number(r.total||0)/max)*(base-top)]);
  const path=reportLinePath(points); const area=`${path} L ${points.at(-1)[0]} ${base} L ${points[0][0]} ${base} Z`;
  const dots=points.map(([x,y],i)=>`<g class="report-point" style="--i:${i}"><circle class="report-dot" cx="${x}" cy="${y}" r="5"/><text class="report-value" x="${x}" y="${Math.max(16,y-14)}" text-anchor="middle">${rows[i].total}</text></g>`).join('');
  const labels=points.map(([x],i)=>`<text class="report-label" x="${x}" y="${H-12}" text-anchor="middle">${esc(rows[i].label)}</text>`).join('');
  chart.innerHTML=`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><defs><linearGradient id="reportStroke" x1="0" x2="1"><stop offset="0%" stop-color="#57e6ff"/><stop offset="100%" stop-color="#2580ff"/></linearGradient><linearGradient id="reportArea" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#42cfff" stop-opacity=".25"/><stop offset="100%" stop-color="#2387ff" stop-opacity="0"/></linearGradient></defs><line class="report-grid" x1="${left}" x2="${W-right}" y1="${base}" y2="${base}"/><path class="report-area" d="${area}"/><path class="report-line" d="${path}" pathLength="1"/>${dots}${labels}</svg>`;
}

function reportOrderMatchesPeriod(order) {
  if(reportPeriod==='all')return true;
  const raw=reportDateKey(order),today=new Date(),ymd=localYmd(today);
  if(reportPeriod==='daily')return raw?raw===ymd:String(order.date_label||'').includes(String(today.getDate()));
  const {start,end}=weekBounds(); if(!raw)return true; const d=new Date(`${raw}T00:00:00`); return d>=start&&d<=end;
}
function renderPersonalReportOrders(){
  const box=document.querySelector('#reportOrders'),count=document.querySelector('#reportOrderCount'); if(!box||!count)return;
  const orders=(reportPayload?.orders||[]).filter(reportOrderMatchesPeriod); count.textContent=`${orders.length} data`; box.replaceChildren();
  if(!orders.length){box.innerHTML='<div class="empty"><p>Belum ada pekerjaan pada periode ini.</p></div>';return;}
  orders.forEach((order,index)=>{const row=document.createElement('div');row.className='mini-order';row.innerHTML=`<strong>${index+1}. 🌐 ${esc(order.service_number||'-')}</strong><small style="line-height:1.7">🎫 ${esc(order.ticket_id||'MANUAL')}<br>📍 ${esc(order.area_label||order.sto||'-')}<br>📅 ${esc(order.date_label||'-')}</small>`;box.appendChild(row);});
}

loadReportData=async function loadPersonalReportData(){
  const identity=document.querySelector('#reportIdentity'),user=telegramUser(); if(!user?.id){identity.textContent='Mini App harus dibuka dari Telegram.';return;}
  identity.textContent='🔄 Memuat rekap pekerjaan...';
  try{const response=await fetch(`/api/my-report?${new URLSearchParams({telegram_id:String(user.id)})}`,{cache:'no-store'}),data=await response.json();if(!response.ok||!data.ok)throw new Error(data.message||`HTTP ${response.status}`);reportPayload=data;identity.textContent=`${data.technician.name} • NIK ${data.technician.nik||'-'}${data.technician.sto?` • ${data.technician.sto}`:''}`;const totals=[data.daily,data.weekly,data.all];document.querySelectorAll('#reportSummary strong').forEach((node,i)=>node.textContent=fmt(totals[i]||0));renderPersonalTrend();renderPersonalReportOrders();}
  catch(error){reportPayload=null;identity.textContent=`❌ ${error.message}`;document.querySelectorAll('#reportSummary strong').forEach(node=>node.textContent='0');renderPersonalTrend();renderPersonalReportOrders();}
};

buildReportPage();
