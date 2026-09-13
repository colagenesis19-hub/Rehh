(() => {
  if (window.__injokoAreaMap) return;
  window.__injokoAreaMap = true;

  const API = 'https://wilayah-id-web.gislabs.workers.dev/api/v1';
  const AREAS = [
    {code:'357822', name:'GAYUNGAN'},
    {code:'357823', name:'JAMBANGAN'},
    {code:'357804', name:'WONOKROMO'}
  ];

  function injectAssets(){
    if(!document.querySelector('link[data-injoko-leaflet]')){
      const l=document.createElement('link');
      l.rel='stylesheet'; l.href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
      l.dataset.injokoLeaflet='1'; document.head.appendChild(l);
    }
    if(!window.L){
      const s=document.createElement('script');
      s.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
      s.onload=render;
      document.head.appendChild(s);
    } else render();
  }

  function ensureUI(){
    const page=document.querySelector('#ordersPage');
    if(!page || page.querySelector('#injokoAreaMapPanel')) return;
    const panel=document.createElement('section');
    panel.id='injokoAreaMapPanel';
    panel.className='panel';
    panel.style.marginTop='12px';
    panel.innerHTML=`
      <div class="panel-head">
        <div><span class="panel-icon">🗺</span><strong>AREA INJOKO</strong></div>
        <span class="panel-meta">POLYGON</span>
      </div>
      <p class="panel-sub">Pemetaan batas kecamatan dan area order INJOKO.</p>
      <div id="injokoAreaMap" style="height:390px;border-radius:16px;overflow:hidden;border:1px solid #294562;background:#081522"></div>
      <div id="injokoAreaLegend" style="display:grid;gap:7px;margin-top:10px"></div>
    `;
    page.appendChild(panel);
  }

  async function getBoundary(code){
    const r=await fetch(`${API}/boundaries/districts/${code}?geometry=true`,{cache:'no-store'});
    if(!r.ok) throw new Error('Boundary '+code+' HTTP '+r.status);
    const j=await r.json();
    return j.data?.geometry ? {type:'Feature',properties:j.data,geometry:j.data.geometry}
      : (j.data?.type==='Feature' ? j.data : null);
  }

  function render(){
    ensureUI();
    if(!window.L) return;
    const el=document.querySelector('#injokoAreaMap');
    if(!el || el.dataset.ready) return;
    el.dataset.ready='1';

    const map=L.map(el,{zoomControl:true}).setView([-7.315,-112.735],13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
      maxZoom:19,attribution:'© OpenStreetMap contributors'
    }).addTo(map);

    const colors=['#35d07f','#4db7ff','#ffb84d'];
    const group=L.featureGroup().addTo(map);
    const legend=document.querySelector('#injokoAreaLegend');

    Promise.all(AREAS.map((a,i)=>getBoundary(a.code).then(f=>{
      if(!f) return;
      const layer=L.geoJSON(f,{
        style:{color:colors[i],weight:2,fillColor:colors[i],fillOpacity:.16}
      }).addTo(group);
      layer.bindTooltip(a.name,{sticky:true,direction:'center'});
      layer.on('click',()=>layer.setStyle({fillOpacity:.30,weight:3}));
      const item=document.createElement('div');
      item.style.cssText='display:flex;align-items:center;gap:8px;color:#dceaff;font-size:11px';
      item.innerHTML='<span style="width:10px;height:10px;border-radius:50%;background:'+colors[i]+'"></span><strong>'+a.name+'</strong>';
      legend.appendChild(item);
    }))).then(()=>{
      if(group.getBounds().isValid()) map.fitBounds(group.getBounds(),{padding:[18,18]});
    }).catch(e=>{
      console.error('INJOKO map:',e);
      legend.innerHTML='<small style="color:#ff9b9b">Batas polygon gagal dimuat.</small>';
    });
  }

  const observer=new MutationObserver(()=>{
    const page=document.querySelector('#ordersPage');
    if(page && !page.classList.contains('hidden')){
      injectAssets();
      if(window.L) render();
    }
  });
  observer.observe(document.body,{childList:true,subtree:true});
  injectAssets();
})();