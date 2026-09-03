(() => {
  if (window.__orderankuAndroidFixInstalled) return;
  window.__orderankuAndroidFixInstalled = true;

  const TAP_MOVE_THRESHOLD = 12;
  const TAP_MAX_DURATION_MS = 800;
  const SYNTHETIC_CLICK_BLOCK_MS = 750;

  const getAreas = () => {
    try {
      return (typeof state !== 'undefined' ? state.myOpenOrders?.areas : window.state?.myOpenOrders?.areas) || [];
    } catch (_) {
      return window.state?.myOpenOrders?.areas || [];
    }
  };

  function openAreaByButton(button, event) {
    if (!button) return false;
    const index = Number(button.dataset.areaIndex);
    const area = getAreas()[index];
    if (!area || typeof window.renderMyOpenArea !== 'function') return false;

    event?.preventDefault?.();
    event?.stopPropagation?.();
    try {
      window.renderMyOpenArea(area);
      window.scrollTo({ top: 0, behavior: 'auto' });
      return true;
    } catch (error) {
      console.error('Orderanku area navigation failed', error);
      window.showToast?.('Gagal membuka area. Coba refresh.');
      return false;
    }
  }

  function bindTouchGuard(button) {
    if (button.dataset.androidBound === '1') return;
    button.dataset.androidBound = '1';
    button.style.touchAction = 'pan-y';

    let startX = 0;
    let startY = 0;
    let startAt = 0;
    let moved = false;
    let suppressClickUntil = 0;

    button.addEventListener('touchstart', event => {
      const touch = event.touches?.[0];
      if (!touch) return;
      startX = touch.clientX;
      startY = touch.clientY;
      startAt = Date.now();
      moved = false;
    }, { passive: true });

    button.addEventListener('touchmove', event => {
      const touch = event.touches?.[0];
      if (!touch) return;
      const dx = touch.clientX - startX;
      const dy = touch.clientY - startY;
      if (Math.hypot(dx, dy) > TAP_MOVE_THRESHOLD) moved = true;
    }, { passive: true });

    button.addEventListener('touchcancel', () => {
      moved = true;
      suppressClickUntil = Date.now() + SYNTHETIC_CLICK_BLOCK_MS;
    }, { passive: true });

    button.addEventListener('touchend', event => {
      const duration = Date.now() - startAt;
      suppressClickUntil = Date.now() + SYNTHETIC_CLICK_BLOCK_MS;

      // Scroll/swipe bukan tap. Jangan buka area dan jangan ganggu momentum scroll.
      if (moved || duration > TAP_MAX_DURATION_MS) return;

      // Tap yang valid: buka area sendiri agar tetap andal di Telegram Android WebView.
      event.preventDefault();
      event.stopImmediatePropagation();
      openAreaByButton(button, event);
    }, { passive: false });

    // Synthetic click biasanya muncul sesudah touchend. Tangkap di capture phase
    // supaya listener click lama di app.js tidak ikut membuka area saat user scroll.
    button.addEventListener('click', event => {
      if (Date.now() < suppressClickUntil) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    }, true);
  }

  function bindButtons() {
    const list = document.querySelector('#myOrdersList');
    const areas = getAreas();
    if (!list || !areas.length) return;

    const buttons = [...list.querySelectorAll(':scope > button.tool-action')];

    // Saat berada di detail area, tombol pertama adalah "Kembali" dan bukan kartu area.
    if (buttons.some(button => /kembali ke daftar area/i.test(button.textContent || ''))) return;

    // renderMyOrderAreas() menghasilkan tepat satu .tool-action per area.
    if (buttons.length !== areas.length) return;

    buttons.forEach((button, index) => {
      button.classList.add('order-area-button');
      button.dataset.areaIndex = String(index);
      bindTouchGuard(button);
    });
  }

  const list = document.querySelector('#myOrdersList');
  if (list) {
    new MutationObserver(() => queueMicrotask(bindButtons)).observe(list, { childList: true, subtree: true });
  }

  const originalRenderAreas = window.renderMyOrderAreas;
  if (typeof originalRenderAreas === 'function' && !originalRenderAreas.__directTouchBound) {
    const wrapped = function(...args) {
      const result = originalRenderAreas.apply(this, args);
      queueMicrotask(bindButtons);
      return result;
    };
    wrapped.__directTouchBound = true;
    window.renderMyOrderAreas = wrapped;
  }

  bindButtons();
})();
