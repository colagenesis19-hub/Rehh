(() => {
  if (window.__injokoAreaMap) return;
  window.__injokoAreaMap = true;

  const BOUNDARY_API = 'https://wilayah-id-web.gislabs.workers.dev/api/v1';
  const STATS_API = '/api/injoko-area-map';
  const AREAS = [
    { code: '357822', name: 'GAYUNGAN' },
    { code: '357823', name: 'JAMBANGAN' },
    { code: '357804', name: 'WONOKROMO' }
  ];

  const COLORS = {
    GAYUNGAN: '#35d07f',
    JAMBANGAN: '#4db7ff',
    WONOKROMO: '#ffb84d'
  };

  function injectAssets() {
    if (!document.querySelector('link[data-injoko-leaflet]')) {
      const l = document.createElement('link');
      l.rel = 'stylesheet';
      l.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
      l.dataset.injokoLeaflet = '1';
      document.head.appendChild(l);
    }
    if (!window.L) {
      if (document.querySelector('script[data-injoko-leaflet]')) return;
      const s = document.createElement('script');
      s.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
      s.dataset.injokoLeaflet = '1';
      s.onload = render;
      document.head.appendChild(s);
    } else {
      render();
    }
  }

  function ensureUI() {
    const page = document.querySelector('#ordersPage');
    if (!page || page.querySelector('#injokoAreaMapPanel')) return;

    const panel = document.createElement('section');
    panel.id = 'injokoAreaMapPanel';
    panel.className = 'panel';
    panel.style.marginTop = '12px';
    panel.innerHTML = `
      <div class="panel-head">
        <div><span class="panel-icon">🗺</span><strong>AREA SUCCESS MAP</strong></div>
        <span id="injokoMapSource" class="panel-meta">INJOKO</span>
      </div>
      <p class="panel-sub">Pemetaan order INJOKO berdasarkan kecamatan. Klik polygon untuk melihat performa area.</p>
      <div id="injokoAreaMap" style="height:390px;border-radius:16px;overflow:hidden;border:1px solid #294562;background:#081522"></div>
      <div id="injokoAreaLegend" style="display:grid;gap:8px;margin-top:10px"></div>
    `;
    page.appendChild(panel);
  }

  async function getBoundary(code) {
    const r = await fetch(`${BOUNDARY_API}/boundaries/districts/${code}?geometry=true`, { cache: 'force-cache' });
    if (!r.ok) throw new Error('Boundary ' + code + ' HTTP ' + r.status);
    const j = await r.json();
    return j.data?.geometry
      ? { type: 'Feature', properties: j.data, geometry: j.data.geometry }
      : (j.data?.type === 'Feature' ? j.data : null);
  }

  async function getStats() {
    const r = await fetch(STATS_API + '?force=0', { cache: 'no-store' });
    if (!r.ok) throw new Error('Stats HTTP ' + r.status);
    return r.json();
  }

  function statText(a) {
    return `<div style="min-width:190px">
      <strong style="font-size:13px">📍 ${a.district}</strong>
      <div style="margin-top:7px;line-height:1.65;font-size:11px">
        🟢 OPEN: <b>${a.open}</b><br>
        🔴 CLOSE: <b>${a.close}</b><br>
        🟡 UPDATE: <b>${a.update}</b><br>
        ⚫ MENOLAK: <b>${a.menolak || 0}</b><br>
        📊 SUCCESS: <b>${a.success}%</b>
      </div>
    </div>`;
  }

  function renderLegend(stats) {
    const legend = document.querySelector('#injokoAreaLegend');
    if (!legend) return;
    legend.replaceChildren();

    stats.forEach(a => {
      const color = COLORS[a.district] || '#7f93aa';
      const item = document.createElement('button');
      item.type = 'button';
      item.style.cssText = 'display:grid;grid-template-columns:10px 1fr auto;align-items:center;gap:8px;width:100%;border:1px solid #203a57;background:#0a1828;color:#dceaff;border-radius:12px;padding:9px 10px;text-align:left';
      item.innerHTML = `
        <span style="width:10px;height:10px;border-radius:50%;background:${color}"></span>
        <span><strong style="font-size:11px">${a.district}</strong><small style="display:block;color:#71869e;font-size:9px;margin-top:2px">${a.close} close / ${a.total} total</small></span>
        <b style="font-size:12px">${a.success}%</b>`;
      item.dataset.area = a.district;
      legend.appendChild(item);
    });
  }

  async function render() {
    ensureUI();
    if (!window.L) return;

    const el = document.querySelector('#injokoAreaMap');
    if (!el || el.dataset.ready) return;
    el.dataset.ready = '1';

    const map = L.map(el, { zoomControl: true }).setView([-7.315, -112.735], 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    const group = L.featureGroup().addTo(map);
    const legend = document.querySelector('#injokoAreaLegend');
    const layers = {};

    try {
      const [statsPayload, ...features] = await Promise.all([
        getStats(),
        ...AREAS.map(a => getBoundary(a.code))
      ]);

      const statsByName = Object.fromEntries((statsPayload.areas || []).map(a => [a.district, a]));
      renderLegend(AREAS.map(a => statsByName[a.name] || {
        district: a.name, open: 0, close: 0, update: 0, menolak: 0, total: 0, success: 0
      }));

      features.forEach((feature, i) => {
        if (!feature) return;
        const area = AREAS[i];
        const stat = statsByName[area.name] || { open: 0, close: 0, update: 0, menolak: 0, total: 0, success: 0 };
        const color = COLORS[area.name] || '#7f93aa';

        const layer = L.geoJSON(feature, {
          style: {
            color,
            weight: 2,
            fillColor: color,
            fillOpacity: .18
          }
        }).addTo(group);

        layers[area.name] = layer;
        layer.bindTooltip(`${area.name} • ${stat.success}% success`, {
          sticky: true,
          direction: 'center'
        });
        layer.bindPopup(statText({ ...stat, district: area.name }));

        layer.on('mouseover', () => layer.setStyle({ weight: 3, fillOpacity: .30 }));
        layer.on('mouseout', () => layer.setStyle({ weight: 2, fillOpacity: .18 }));
        layer.on('click', () => layer.openPopup());
      });

      legend?.querySelectorAll('[data-area]').forEach(btn => {
        btn.addEventListener('click', () => {
          const layer = layers[btn.dataset.area];
          if (layer) {
            map.fitBounds(layer.getBounds(), { padding: [20, 20], maxZoom: 14 });
            layer.openPopup();
          }
        });
      });

      if (group.getBounds().isValid()) {
        map.fitBounds(group.getBounds(), { padding: [18, 18] });
      }
      document.querySelector('#injokoMapSource')?.replaceChildren(document.createTextNode('SHEET • LIVE'));
    } catch (e) {
      console.error('INJOKO success map:', e);
      if (legend) legend.innerHTML = '<small style="color:#ff9b9b">Data peta gagal dimuat. Coba refresh.</small>';
    }
  }

  const observer = new MutationObserver(() => {
    const page = document.querySelector('#ordersPage');
    if (page && !page.classList.contains('hidden')) {
      injectAssets();
      if (window.L) render();
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });
  injectAssets();
})();