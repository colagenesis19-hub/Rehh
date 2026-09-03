(() => {
  if (window.__dashboardChartSwitchInstalled) return;
  window.__dashboardChartSwitchInstalled = true;

  const tg = window.Telegram?.WebApp;
  let mode = 'replacement';
  let dismantlePayload = null;
  let loading = false;

  const userId = () => tg?.initDataUnsafe?.user?.id || null;
  const fmt = value => new Intl.NumberFormat('id-ID').format(Number(value || 0));
  const shortDay = value => String(value || '').slice(0, 3).toUpperCase();

  function injectStyles() {
    if (document.querySelector('#dashboardChartSwitchStyles')) return;
    const style = document.createElement('style');
    style.id = 'dashboardChartSwitchStyles';
    style.textContent = `
      .chart-mode-switch{display:grid;grid-template-columns:1fr 1fr;gap:6px;padding:5px;margin:0 0 12px;border:1px solid rgba(123,160,200,.16);border-radius:14px;background:rgba(5,14,25,.72)}
      .chart-mode-btn{min-height:40px;border:0;border-radius:10px;background:transparent;color:#7f94ab;font-size:10px;font-weight:900;letter-spacing:.02em}
      .chart-mode-btn.active{background:linear-gradient(135deg,#1c83ff,#4fd7ff);color:#fff;box-shadow:0 6px 20px rgba(36,135,255,.22)}
      .trend-panel[data-chart-mode="dismantle"] .panel-icon{color:#ffb32c}
      .trend-panel[data-chart-mode="dismantle"] .trend-line-path{stroke:#ffad2f!important}
      .trend-panel[data-chart-mode="dismantle"] .line-dot{fill:#ffad2f!important}
      .trend-panel[data-chart-mode="dismantle"] .line-halo{stroke:#ffad2f!important}
      .chart-mode-note{display:block;margin-top:6px;color:#70869e;font-size:9px}
    `;
    document.head.appendChild(style);
  }

  function ensureSwitch() {
    const panel = document.querySelector('.trend-panel');
    if (!panel) return;
    let switcher = document.querySelector('#chartModeSwitch');
    if (!switcher) {
      switcher = document.createElement('div');
      switcher.id = 'chartModeSwitch';
      switcher.className = 'chart-mode-switch';
      switcher.innerHTML = `
        <button type="button" class="chart-mode-btn active" data-chart-mode="replacement">REPLACEMENT</button>
        <button type="button" class="chart-mode-btn" data-chart-mode="dismantle">DISMANTLING</button>
      `;
      panel.insertBefore(switcher, panel.firstChild);
      switcher.querySelectorAll('[data-chart-mode]').forEach(button => {
        button.addEventListener('click', () => setMode(button.dataset.chartMode));
      });
    }
    syncButtons();
  }

  function syncButtons() {
    document.querySelectorAll('#chartModeSwitch [data-chart-mode]').forEach(button => {
      button.classList.toggle('active', button.dataset.chartMode === mode);
    });
    const panel = document.querySelector('.trend-panel');
    if (panel) panel.dataset.chartMode = mode;
  }

  async function fetchDismantle() {
    const id = userId();
    if (!id) throw new Error('Mini App harus dibuka dari Telegram.');
    const response = await fetch(`/api/dismantle-orders?telegram_id=${encodeURIComponent(id)}`, {cache:'no-store'});
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.message || 'Gagal membaca data dismantling.');
    dismantlePayload = data;
    return data;
  }

  function drawTrendColumns(trend) {
    const chart = document.querySelector('#trendChart');
    if (!chart) return;
    const rows = Array.isArray(trend) ? trend : [];
    const max = Math.max(1, ...rows.map(item => Number(item.total || 0)));
    chart.dataset.fluidChart = '0';
    chart.replaceChildren();
    rows.forEach(item => {
      const col = document.createElement('div');
      col.className = 'trend-col';
      const height = Math.max(5, Math.round(Number(item.total || 0) / max * 100));
      col.innerHTML = `<span class="trend-value">${fmt(item.total)}</span><div class="trend-bar-wrap"><div class="trend-bar" style="height:${height}%"></div></div><span class="trend-label">${shortDay(item.label)}</span>`;
      chart.appendChild(col);
    });
  }

  function renderDismantle(data) {
    if (mode !== 'dismantle') return;
    ensureSwitch();
    const panel = document.querySelector('.trend-panel');
    const title = panel?.querySelector('.panel-head strong');
    const total = document.querySelector('#trendTotal');
    if (title) title.textContent = 'TREND DISMANTLING HARIAN';

    let trend = data?.trend || [];
    if (window.state?.area === 'JGR') {
      trend = trend.map(item => ({...item, total:0}));
      if (total) total.textContent = '0 selesai • Manyar saja';
    } else if (total) {
      total.textContent = `${fmt(trend.reduce((sum, item) => sum + Number(item.total || 0), 0))} selesai`;
    }

    drawTrendColumns(trend);
    requestAnimationFrame(() => {
      if (typeof window.upgradeTrendChart === 'function') window.upgradeTrendChart();
    });
  }

  function renderReplacement() {
    if (mode !== 'replacement') return;
    ensureSwitch();
    const panel = document.querySelector('.trend-panel');
    const title = panel?.querySelector('.panel-head strong');
    if (title) title.textContent = 'TREND ORDER HARIAN';
    if (typeof window.renderTrend === 'function') window.renderTrend();
  }

  async function setMode(nextMode) {
    if (!['replacement','dismantle'].includes(nextMode)) return;
    mode = nextMode;
    syncButtons();
    tg?.HapticFeedback?.selectionChanged?.();
    if (mode === 'replacement') {
      renderReplacement();
      return;
    }
    if (loading) return;
    loading = true;
    const total = document.querySelector('#trendTotal');
    if (total) total.textContent = 'memuat...';
    try {
      renderDismantle(await fetchDismantle());
    } catch (error) {
      console.error(error);
      if (total) total.textContent = 'gagal memuat';
      drawTrendColumns([]);
    } finally {
      loading = false;
    }
  }

  function refreshSelectedMode() {
    ensureSwitch();
    if (mode === 'dismantle') {
      fetchDismantle().then(renderDismantle).catch(console.error);
    } else {
      renderReplacement();
    }
  }

  injectStyles();
  ensureSwitch();

  window.addEventListener('kerja:ajax-success', event => {
    if (event.detail?.url === '/api/dashboard') setTimeout(refreshSelectedMode, 0);
    if (event.detail?.url === '/api/dismantle-orders' && mode === 'dismantle' && dismantlePayload) {
      setTimeout(() => renderDismantle(dismantlePayload), 0);
    }
  });

  document.querySelectorAll('[data-area],[data-period]').forEach(button => {
    button.addEventListener('click', () => setTimeout(refreshSelectedMode, 180));
  });

  new MutationObserver(() => ensureSwitch()).observe(document.body, {childList:true, subtree:true});
})();
