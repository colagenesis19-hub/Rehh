(() => {
  const tg = window.Telegram?.WebApp;
  const root = document.documentElement;
  const body = document.body;
  const $ = (s, p=document) => p.querySelector(s);
  const $$ = (s, p=document) => [...p.querySelectorAll(s)];

  const ajaxState = {
    active: 0,
    lastSuccess: Date.now(),
    lastVisibleRefresh: 0,
    inflight: new Map(),
    nativeFetch: window.fetch.bind(window),
  };

  function haptic(kind='light') {
    try { tg?.HapticFeedback?.impactOccurred?.(kind); } catch (_) {}
  }

  function toast(message) {
    const el = $('#toast');
    if (!el) return;
    el.textContent = message;
    el.classList.remove('hidden', 'toast-in');
    void el.offsetWidth;
    el.classList.add('toast-in');
    clearTimeout(window.__interactiveToastTimer);
    window.__interactiveToastTimer = setTimeout(() => {
      el.classList.remove('toast-in');
      setTimeout(() => el.classList.add('hidden'), 180);
    }, 1800);
  }

  function apiUrl(input) {
    try {
      const raw = typeof input === 'string' ? input : input?.url;
      const url = new URL(raw, window.location.href);
      return url.origin === window.location.origin && url.pathname.startsWith('/api/') ? url : null;
    } catch (_) { return null; }
  }

  function setAjaxBusy(delta) {
    ajaxState.active = Math.max(0, ajaxState.active + delta);
    body.classList.toggle('ajax-busy', ajaxState.active > 0);
    root.dataset.ajax = ajaxState.active > 0 ? 'loading' : 'idle';
  }

  function combineSignal(controller, externalSignal) {
    if (!externalSignal) return;
    if (externalSignal.aborted) controller.abort(externalSignal.reason);
    else externalSignal.addEventListener('abort', () => controller.abort(externalSignal.reason), { once:true });
  }

  async function ajaxFetch(input, init={}) {
    const url = apiUrl(input);
    if (!url) return ajaxState.nativeFetch(input, init);

    const method = String(init.method || (typeof input !== 'string' ? input?.method : '') || 'GET').toUpperCase();
    const key = `${method}:${url.pathname}${url.search}`;
    const isGet = method === 'GET';

    if (isGet && ajaxState.inflight.has(key)) {
      const response = await ajaxState.inflight.get(key);
      return response.clone();
    }

    const controller = new AbortController();
    combineSignal(controller, init.signal);
    const timeout = setTimeout(() => controller.abort(new DOMException('Request timeout', 'TimeoutError')), 20000);
    const headers = new Headers(init.headers || (typeof input !== 'string' ? input?.headers : undefined) || {});
    headers.set('X-Requested-With', 'XMLHttpRequest');

    const opts = {
      ...init,
      headers,
      signal: controller.signal,
      cache: isGet ? 'no-store' : init.cache,
    };

    setAjaxBusy(1);
    window.dispatchEvent(new CustomEvent('kerja:ajax-start', { detail:{ url:url.pathname, method } }));

    const promise = ajaxState.nativeFetch(input, opts)
      .then(response => {
        if (!response.ok) throw Object.assign(new Error(`HTTP ${response.status}`), { response });
        ajaxState.lastSuccess = Date.now();
        window.dispatchEvent(new CustomEvent('kerja:ajax-success', { detail:{ url:url.pathname, method, status:response.status } }));
        return response;
      })
      .catch(error => {
        window.dispatchEvent(new CustomEvent('kerja:ajax-error', { detail:{ url:url.pathname, method, error } }));
        throw error;
      })
      .finally(() => {
        clearTimeout(timeout);
        ajaxState.inflight.delete(key);
        setAjaxBusy(-1);
        window.dispatchEvent(new CustomEvent('kerja:ajax-end', { detail:{ url:url.pathname, method } }));
      });

    if (isGet) ajaxState.inflight.set(key, promise);
    const response = await promise;
    return response.clone();
  }

  // All existing Mini App API calls become AJAX automatically without a page reload.
  window.fetch = ajaxFetch;
  window.KerjaAjax = {
    get: async (url, init={}) => {
      const r = await ajaxFetch(url, { ...init, method:'GET' });
      return r.json();
    },
    post: async (url, data, init={}) => {
      const headers = new Headers(init.headers || {});
      if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
      const r = await ajaxFetch(url, { ...init, method:'POST', headers, body:JSON.stringify(data ?? {}) });
      return r.json();
    },
    refresh: () => refreshCurrent(false),
    state: ajaxState,
  };

  function ensureWelcomeStatus() {
    const pill = $('.welcome-row .period-pill');
    if (!pill) return null;
    let wrap = $('.welcome-row .welcome-status');
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.className = 'welcome-status';
      pill.parentNode.insertBefore(wrap, pill);
      wrap.appendChild(pill);
    }
    return wrap;
  }

  function setNetworkState() {
    const online = navigator.onLine;
    root.dataset.network = online ? 'online' : 'offline';
    const wrap = ensureWelcomeStatus();
    let badge = $('#networkBadge');
    if (!badge) {
      badge = document.createElement('div');
      badge.id = 'networkBadge';
      badge.setAttribute('role', 'status');
      badge.innerHTML = '<i></i><b></b>';
      (wrap || body).prepend(badge);
    } else if (wrap && badge.parentElement !== wrap) wrap.prepend(badge);
    const label = $('b', badge);
    if (label) label.textContent = online ? 'ONLINE' : 'OFFLINE';
    badge.classList.toggle('offline', !online);
    badge.title = online ? 'Koneksi aktif' : 'Koneksi terputus';
  }

  async function refreshCurrent(showMessage=true) {
    if (!navigator.onLine) {
      if (showMessage) toast('Sedang offline');
      return;
    }
    haptic('medium');
    body.classList.add('is-refreshing');
    const active = $('.page-view:not(.hidden)')?.id || 'dashboardPage';
    try {
      if (active === 'dashboardPage' && typeof window.loadDashboard === 'function') await window.loadDashboard();
      else if (active === 'ordersPage' && typeof window.loadMyOpenOrders === 'function') await window.loadMyOpenOrders(true);
      else if (active === 'reportsPage' && typeof window.loadMyReport === 'function') await window.loadMyReport();
      else if (active === 'inputPage' && typeof window.fetchMyOpenOrders === 'function') await window.fetchMyOpenOrders(true);
      ajaxState.lastVisibleRefresh = Date.now();
      if (showMessage) toast('Data diperbarui');
    } catch (err) {
      console.error(err);
      if (showMessage) toast('Refresh gagal');
    } finally {
      setTimeout(() => body.classList.remove('is-refreshing'), 360);
    }
  }

  function linePath(points) {
    if (!points.length) return '';
    if (points.length === 1) return `M ${points[0][0]} ${points[0][1]}`;
    let d = `M ${points[0][0]} ${points[0][1]}`;
    for (let i=1; i<points.length; i++) {
      const [x0,y0] = points[i-1];
      const [x1,y1] = points[i];
      const mx = (x0+x1)/2;
      d += ` C ${mx} ${y0}, ${mx} ${y1}, ${x1} ${y1}`;
    }
    return d;
  }

  function upgradeTrendChart() {
    const chart = $('#trendChart');
    if (!chart || chart.dataset.fluidChart === '1') return;
    const cols = $$('.trend-col', chart);
    if (!cols.length) return;
    const rows = cols.map(col => ({
      value: Number(($('.trend-value', col)?.textContent || '0').replace(/[^0-9.-]/g,'')) || 0,
      label: $('.trend-label', col)?.textContent || ''
    }));
    if (!rows.length) return;

    const W=700, H=200, left=38, right=24, top=30, bottom=45;
    const plotBottom=H-bottom, plotHeight=plotBottom-top;
    const max=Math.max(1,...rows.map(r=>r.value));
    const step=rows.length>1?(W-left-right)/(rows.length-1):0;
    const points=rows.map((r,i)=>[left+i*step, plotBottom-(r.value/max)*plotHeight]);
    const path=linePath(points);
    const area=`${path} L ${points[points.length-1][0]} ${plotBottom} L ${points[0][0]} ${plotBottom} Z`;
    const dots=points.map(([x,y],i)=>`<g class="line-point" style="--i:${i}"><circle class="line-halo" cx="${x}" cy="${y}" r="9"/><circle class="line-dot" cx="${x}" cy="${y}" r="5"/><text class="line-value" x="${x}" y="${Math.max(16,y-15)}" text-anchor="middle">${rows[i].value}</text><line class="line-guide" x1="${x}" x2="${x}" y1="${y+9}" y2="${plotBottom}"/></g>`).join('');
    const labels=points.map(([x],i)=>`<text class="line-label" x="${x}" y="${H-14}" text-anchor="middle">${rows[i].label}</text>`).join('');

    chart.dataset.fluidChart='1';
    chart.innerHTML=`<svg class="trend-line-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Grafik garis trend order harian"><defs><linearGradient id="trendAreaGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#42cfff" stop-opacity=".27"/><stop offset="100%" stop-color="#2387ff" stop-opacity="0"/></linearGradient><linearGradient id="trendStrokeGradient" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#52dcff"/><stop offset="100%" stop-color="#2580ff"/></linearGradient><filter id="trendGlow"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs><line class="line-baseline" x1="${left}" x2="${W-right}" y1="${plotBottom}" y2="${plotBottom}"/><path class="trend-area-path" d="${area}"/><path class="trend-line-path" d="${path}" pathLength="1"/>${dots}${labels}</svg>`;
  }

  function observeTrend() {
    const chart = $('#trendChart');
    if (!chart) return;
    const observer = new MutationObserver(() => {
      if ($('.trend-col', chart)) {
        chart.dataset.fluidChart='0';
        requestAnimationFrame(upgradeTrendChart);
      }
    });
    observer.observe(chart,{childList:true,subtree:true});
    requestAnimationFrame(upgradeTrendChart);
  }

  function animateMetric(el) {
    if (!el || el.dataset.animating === '1') return;
    el.dataset.animating='1';
    el.classList.remove('metric-pop');
    void el.offsetWidth;
    el.classList.add('metric-pop');
    setTimeout(()=>{el.classList.remove('metric-pop');el.dataset.animating='0';},420);
  }

  function observeMetrics() {
    ['#totalClose','#activeTechnicians','#averageClose','#ringValue','#myOrderCount'].forEach(sel=>{
      const el=$(sel); if(!el)return;
      new MutationObserver(()=>animateMetric(el)).observe(el,{childList:true,characterData:true,subtree:true});
    });
  }

  function enhanceEntrance() {
    $$('.kpi-card,.dashboard-grid>.panel').forEach((el,i)=>el.style.setProperty('--enter-delay',`${Math.min(i*42,260)}ms`));
  }

  function installAutoRefresh() {
    const tick = async () => {
      if (document.hidden || !navigator.onLine || ajaxState.active > 0) return;
      const active = $('.page-view:not(.hidden)')?.id;
      if (active !== 'dashboardPage') return;
      if (Date.now() - ajaxState.lastVisibleRefresh < 45000) return;
      await refreshCurrent(false);
    };
    setInterval(tick, 15000);
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden && Date.now() - ajaxState.lastSuccess > 60000) setTimeout(() => refreshCurrent(false), 250);
    });
  }

  document.addEventListener('pointerdown', (e) => {
    const target = e.target.closest('button,.tool-action,.mini-order,.leader-row,.area-row,.kpi-card');
    if (target) target.classList.add('pressing');
  }, {passive:true});

  document.addEventListener('pointerup', (e) => {
    const target = e.target.closest('button,.tool-action,.mini-order,.leader-row,.area-row,.kpi-card');
    if (target) {
      target.classList.remove('pressing');
      haptic('light');
    }
  }, {passive:true});

  document.addEventListener('pointercancel', () => $$('.pressing').forEach(el=>el.classList.remove('pressing')), {passive:true});
  window.addEventListener('online', () => { setNetworkState(); toast('Koneksi kembali online'); setTimeout(()=>refreshCurrent(false),300); });
  window.addEventListener('offline', () => { setNetworkState(); toast('Koneksi terputus'); });
  window.addEventListener('kerja:ajax-error', e => {
    if (e.detail?.error?.name === 'AbortError') return;
    body.classList.add('ajax-error-flash');
    setTimeout(()=>body.classList.remove('ajax-error-flash'),350);
  });

  let startY=0, pulling=false, indicator;
  function ensureIndicator() {
    if (indicator) return indicator;
    indicator=document.createElement('div');
    indicator.id='pullRefresh';
    indicator.innerHTML='<span>↻</span><b>Tarik untuk refresh</b>';
    body.appendChild(indicator);
    return indicator;
  }
  document.addEventListener('touchstart',e=>{if(window.scrollY>2||e.touches.length!==1)return;startY=e.touches[0].clientY;pulling=true;},{passive:true});
  document.addEventListener('touchmove',e=>{if(!pulling)return;const delta=Math.max(0,Math.min(95,e.touches[0].clientY-startY));if(delta<8)return;const el=ensureIndicator();el.style.transform=`translate(-50%, ${Math.min(58,delta*.6)}px)`;el.classList.toggle('ready',delta>70);$('b',el).textContent=delta>70?'Lepas untuk refresh':'Tarik untuk refresh';},{passive:true});
  document.addEventListener('touchend',async e=>{if(!pulling)return;pulling=false;const delta=e.changedTouches?.[0]?e.changedTouches[0].clientY-startY:0;if(indicator)indicator.style.transform='translate(-50%,-60px)';if(delta>70)await refreshCurrent(true);},{passive:true});

  const style=document.createElement('style');
  style.textContent=`
    html{scroll-behavior:smooth}body{overflow-x:hidden;background-attachment:fixed}
    body::before{content:'';position:fixed;z-index:999;left:0;top:0;width:100%;height:2px;pointer-events:none;transform-origin:left center;transform:scaleX(0);opacity:0;background:linear-gradient(90deg,#3ddcff,#2f86ff,#8d72ff);box-shadow:0 0 14px rgba(61,220,255,.7);transition:transform .35s cubic-bezier(.2,.8,.2,1),opacity .2s ease}
    body.ajax-busy::before{opacity:1;transform:scaleX(.82);animation:ajaxProgress 1.2s ease-in-out infinite}
    @keyframes ajaxProgress{0%{transform:scaleX(.12);transform-origin:left}55%{transform:scaleX(.78);transform-origin:left}100%{transform:scaleX(.18);transform-origin:right}}
    .welcome-status{display:flex;flex-direction:column;align-items:stretch;gap:7px;min-width:128px}
    #networkBadge{position:static;align-self:flex-end;display:inline-flex;align-items:center;gap:7px;min-height:24px;padding:5px 9px;border:1px solid rgba(63,221,153,.30);border-radius:999px;background:linear-gradient(180deg,rgba(8,38,42,.82),rgba(4,24,31,.72));backdrop-filter:blur(12px);color:#5ee6a5;font:800 8px/1 system-ui;letter-spacing:.11em;pointer-events:none;box-shadow:0 7px 20px rgba(0,0,0,.12);transition:color .35s ease,border-color .35s ease,background .35s ease,transform .35s cubic-bezier(.2,.8,.2,1)}
    #networkBadge i{width:7px;height:7px;border-radius:50%;background:currentColor;box-shadow:0 0 0 4px rgba(94,230,165,.08),0 0 12px currentColor;animation:networkPulse 2.2s ease-in-out infinite}#networkBadge.offline{color:#ff7480;border-color:rgba(255,91,108,.35);background:rgba(44,9,17,.76)}
    @keyframes networkPulse{0%,100%{transform:scale(.88);opacity:.7}50%{transform:scale(1.08);opacity:1}}
    .round-btn,.segment,.period,.nav-item,.tool-action,.leader-row,.area-row,.mini-order,.kpi-card,.panel,.pay-stat,.detail-metrics>div{transition:transform .28s cubic-bezier(.2,.8,.2,1),border-color .28s ease,background .28s ease,box-shadow .32s ease,filter .24s ease,opacity .24s ease}
    .round-btn:active,.segment:active,.period:active,.nav-item:active{transform:scale(.94)}
    .pressing{transform:scale(.975)!important;filter:brightness(1.10);transition-duration:.09s!important}
    .segment.active,.period.active{transform:translateY(-1px);box-shadow:0 8px 24px rgba(36,135,255,.28)}
    .segmented{overflow:hidden;box-shadow:inset 0 1px 0 rgba(255,255,255,.025)}
    .kpi-card,.panel{backdrop-filter:blur(12px)}
    body.ajax-busy .dashboard-grid>.panel,body.ajax-busy .kpi-card{filter:saturate(.96)}
    .kpi-card{animation:cardEnter .5s cubic-bezier(.16,.82,.25,1) both;animation-delay:var(--enter-delay,0ms)}
    .dashboard-grid>.panel{animation:panelEnter .55s cubic-bezier(.16,.82,.25,1) both;animation-delay:var(--enter-delay,0ms)}
    @keyframes cardEnter{from{opacity:0;transform:translateY(13px) scale(.985)}to{opacity:1;transform:none}}
    @keyframes panelEnter{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
    .kpi-icon{transition:transform .35s cubic-bezier(.2,.8,.2,1),box-shadow .35s ease}.kpi-card:active .kpi-icon{transform:scale(1.08) rotate(-3deg)}
    .metric-pop{animation:metricPop .4s cubic-bezier(.2,.9,.2,1)}@keyframes metricPop{0%{transform:translateY(5px);opacity:.35}55%{transform:translateY(-2px) scale(1.04)}100%{transform:none;opacity:1}}
    .trend-chart{height:218px!important;display:block!important;padding:6px 0 0!important;position:relative;overflow:visible}
    .trend-line-svg{width:100%;height:100%;overflow:visible;display:block}
    .line-baseline{stroke:rgba(116,153,190,.22);stroke-width:1}.trend-area-path{fill:url(#trendAreaGradient);opacity:0;animation:areaFade .7s .2s ease forwards}.trend-line-path{fill:none;stroke:url(#trendStrokeGradient);stroke-width:4;stroke-linecap:round;stroke-linejoin:round;filter:url(#trendGlow);stroke-dasharray:1;stroke-dashoffset:1;animation:drawTrend .9s cubic-bezier(.2,.75,.2,1) forwards}
    .line-guide{stroke:rgba(76,161,255,.16);stroke-width:1;stroke-dasharray:4 5}.line-dot{fill:#eaf7ff;stroke:#2d91ff;stroke-width:4;filter:url(#trendGlow)}.line-halo{fill:rgba(66,207,255,.11);stroke:none}.line-value{fill:#eaf6ff;font-size:15px;font-weight:800}.line-label{fill:#7e96af;font-size:13px;font-weight:700}.line-point{opacity:0;animation:pointIn .34s cubic-bezier(.2,.9,.2,1) forwards;animation-delay:calc(.42s + var(--i)*.07s)}
    @keyframes drawTrend{to{stroke-dashoffset:0}}@keyframes areaFade{to{opacity:1}}@keyframes pointIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
    .bottom-nav{box-shadow:0 20px 55px rgba(0,0,0,.32),inset 0 1px 0 rgba(255,255,255,.045);transition:transform .3s ease,background .3s ease}.nav-item.active{transform:translateY(-1px)}.nav-item.active span{filter:drop-shadow(0 0 9px rgba(75,167,255,.45))}.nav-plus span{transition:transform .3s cubic-bezier(.2,.9,.2,1),box-shadow .3s ease}.nav-plus:active span{transform:scale(.92) rotate(4deg)}
    .detail-panel:not(.hidden) .detail-backdrop,.drawer:not(.hidden) .drawer-backdrop,.more-menu:not(.hidden) .more-backdrop{animation:backdropIn .2s ease both}.detail-panel:not(.hidden) .detail-sheet{animation:sheetUp .34s cubic-bezier(.18,.85,.25,1) both}.drawer:not(.hidden) .drawer-sheet{animation:drawerIn .3s cubic-bezier(.18,.85,.25,1) both}.more-menu:not(.hidden) .more-box{animation:menuPop .24s cubic-bezier(.18,.85,.25,1) both}
    @keyframes backdropIn{from{opacity:0}to{opacity:1}}@keyframes sheetUp{from{opacity:.4;transform:translateY(34px)}to{opacity:1;transform:none}}@keyframes drawerIn{from{transform:translateX(-22px);opacity:.5}to{transform:none;opacity:1}}@keyframes menuPop{from{opacity:0;transform:translateY(-8px) scale(.96)}to{opacity:1;transform:none}}
    .page-view{animation:pageFluidIn .3s cubic-bezier(.18,.82,.28,1) both}@keyframes pageFluidIn{from{opacity:0;transform:translateY(9px) scale(.996)}to{opacity:1;transform:none}}
    .toast{transition:opacity .18s ease,transform .22s cubic-bezier(.2,.9,.2,1)}.toast.toast-in{animation:toastPop .28s cubic-bezier(.2,.9,.2,1)}@keyframes toastPop{from{opacity:0;transform:translate(-50%,10px) scale(.96)}to{opacity:1;transform:translate(-50%,0) scale(1)}}
    body.is-refreshing .brand-center strong::after{content:' ↻';display:inline-block;color:#55d9ff;animation:uiSpin .7s linear infinite}@keyframes uiSpin{to{transform:rotate(360deg)}}
    #pullRefresh{position:fixed;z-index:260;left:50%;top:-52px;transform:translate(-50%,-60px);display:flex;align-items:center;gap:8px;border:1px solid #284762;background:rgba(7,24,40,.95);box-shadow:0 10px 30px rgba(0,0,0,.35);border-radius:999px;padding:8px 12px;color:#90a8be;font:700 10px system-ui;transition:transform .15s ease}#pullRefresh span{font-size:15px;color:#55d9ff}#pullRefresh.ready{color:#e9f7ff;border-color:#45b9df}#pullRefresh.ready span{animation:uiSpin .65s linear infinite}
    .ajax-error-flash .app-shell{animation:errorFlash .32s ease}@keyframes errorFlash{50%{filter:saturate(.8) brightness(.94)}100%{filter:none}}
    @media(max-width:430px){.welcome-status{min-width:112px}.trend-chart{height:198px!important}.line-value{font-size:13px}.line-label{font-size:12px}}
    @media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important;scroll-behavior:auto!important}}
  `;
  document.head.appendChild(style);

  setNetworkState();
  observeTrend();
  observeMetrics();
  enhanceEntrance();
  installAutoRefresh();
  tg?.setHeaderColor?.('#06111f');
  tg?.setBackgroundColor?.('#06111f');

  // Re-run one silent AJAX refresh after the enhancement layer is installed,
  // so the first visible dashboard also benefits from the AJAX pipeline.
  setTimeout(() => refreshCurrent(false), 450);
})();
