(() => {
  if (window.__injokoWebsiteAreaMap) return;
  window.__injokoWebsiteAreaMap = true;

  const BOUNDARY_API = 'https://wilayah-id-web.gislabs.workers.dev/api/v1';
  const AREAS = [
    { code: '357822', name: 'GAYUNGAN', keys: ['GAYUNGAN','DUKUH MENANGGAL','MENANGGAL','KETINTANG'] },
    { code: '357823', name: 'JAMBANGAN', keys: ['JAMBANGAN','KARAH','KEBONSARI','PAGESANGAN'] },
    { code: '357804', name: 'WONOKROMO', keys: ['WONOKROMO','WONOKROMO','PULO WONOKROMO','PULO TEGALSARI','KARANG REJO','JETIS KULON','SMEA'] }
  ];

  function esc(v){return String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function norm(v){return String(v||'').toUpperCase().replace(/\s+/g,' ').trim();}
  function statusOf(o){
    return norm(o.status || o.status_manual || o.status_tacpro || o.status_insera || '');
  }
  function bucket(o){
    const s=statusOf(o);
    if(/CLOSE|CLOSED|DONE|SELESAI|COMPLET/.test(s)) return 'close';
    if(/UPDATE|UPDATED|PROGRESS|PENDING/.test(s)) return 'update';
    if(/MENOLAK|MENOLAKAN|REJECT|TOLAK/.test(s)) return 'reject';
    return 'open';
  }
  function areaFor(o){
    const a=norm(o.address || o.alamat || '');
    for(const area of AREAS){
      if(area.keys.some(k=>a.includes(k))) return area.name;
    }
    return 'LAINNYA';
  }
  function color(success){
    if(success >= 80) return '#19e79b';
    if(success >= 60) return '#a8e85a';
    if(success >= 40) return '#ffc531';
    return '#ff4962';
  }

  async function boundary(code){
    const r=await fetch(`${BOUNDARY_API}/boundaries/districts/${code}?geometry=true`,{cache:'force-cache'});
    if(!r.ok) throw new Error('Boundary '+code+' HTTP '+r.status);
    const j=await r.json();
    return j.data?.geometry ? {type:'Feature',properties:j.data,geometry:j.data.geometry} :
      (j.data?.type==='Feature' ? j.data : null);
  }

  function ensure(){
    const host=document.querySelector('#injokoWebsiteAreaMap');
    return host;
  }

  async function render(){
    const host=ensure();
    if(!host || host.dataset.ready) return;
    host.dataset.ready='1';

    if(!window.L){
      if(!document.querySelector('script[data-injoko-leaflet]')){
        const css=document.createElement('link');
        css.rel='stylesheet'; css.href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
        document.head.appendChild(css);
        const s=document.createElement('script');
        s.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
        s.dataset.injokoLeaflet='1'; s.onload=render;
        document.head.appendChild(s);
      }
      return;
    }

    const map=L.map(host,{zoomControl:true}).setView([-7.315,-112.735],13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(map);
    const group=L.featureGroup().addTo(map);

    try{
      const payload=await fetch('/api/web-orders?force=1',{credentials:'same-origin',cache:'no-store'}).then(r=>{
        if(!r.ok) throw new Error('Order API HTTP '+r.status); return r.json();
      });
      const orders=Array.isArray(payload)?payload:(payload.orders||payload.data||[]);
      const stats={};
      AREAS.forEach(a=>stats[a.name]={district:a.name,total:0,open:0,close:0,update:0,reject:0,success:0});
      orders.forEach(o=>{
        const name=areaFor(o);
        if(!stats[name]) return;
        const b=bucket(o); stats[name].total++; stats[name][b]++;
      });
      AREAS.forEach(a=>{
        const s=stats[a.name];
        s.success=s.total ? Math.round(s.close/s.total*1000)/10 : 0;
      });

      const bounds=[];
      const features=await Promise.all(AREAS.map(a=>boundary(a.code).catch(()=>null)));
      features.forEach((feature,i)=>{
        if(!feature) return;
        const a=AREAS[i], s=stats[a.name], c=color(s.success);
        const layer=L.geoJSON(feature,{style:{color:c,weight:2,fillColor:c,fillOpacity:.20}});
        layer.addTo(group); bounds.push(layer.getBounds());
        layer.bindTooltip(`${a.name} • ${s.success}% success`,{sticky:true,direction:'center'});
        layer.bindPopup(`<div style="min-width:190px"><strong>📍 ${esc(a.name)}</strong><div style="margin-top:7px;line-height:1.7;font-size:11px">📋 TOTAL: <b>${s.total}</b><br>🟢 OPEN: <b>${s.open}</b><br>🔴 CLOSE: <b>${s.close}</b><br>🟡 UPDATE: <b>${s.update}</b><br>⚫ MENOLAK: <b>${s.reject}</b><br>📊 SUCCESS: <b>${s.success}%</b></div></div>`);
        layer.on('mouseover',()=>layer.setStyle({weight:3,fillOpacity:.34}));
        layer.on('mouseout',()=>layer.setStyle({weight:2,fillOpacity:.20}));
      });

      const legend=document.querySelector('#injokoAreaMapLegend');
      if(legend) legend.innerHTML=AREAS.map(a=>{
        const s=stats[a.name], c=color(s.success);
        return `<div style="display:grid;grid-template-columns:10px 1fr auto;gap:8px;align-items:center;padding:9px 10px;border:1px solid #1d3a56;border-radius:11px;background:#081725">
          <span style="width:10px;height:10px;border-radius:50%;background:${c}"></span>
          <span><b style="font-size:10px">${a.name}</b><small style="display:block;color:#71869f;font-size:8px;margin-top:2px">${s.close} close / ${s.total} total</small></span>
          <b style="font-size:11px;color:${c}">${s.success}%</b>
        </div>`;
      }).join('');
      if(bounds.length) map.fitBounds(L.featureGroup(group.getLayers()).getBounds(),{padding:[18,18]});
      const src=document.querySelector('#injokoMapSource'); if(src) src.textContent='SHEET • LIVE';
    }catch(e){
      console.error('INJOKO Area Success Map',e);
      const legend=document.querySelector('#injokoAreaMapLegend');
      if(legend) legend.innerHTML='<div style="color:#ff7387;font-size:9px">Data peta gagal dimuat. Coba refresh.</div>';
    }
  }

  const observer=new MutationObserver(()=>{if(document.querySelector('#injokoWebsiteAreaMap')) render();});
  observer.observe(document.body,{childList:true,subtree:true});
  render();
})();