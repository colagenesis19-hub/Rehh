(() => {
  if (window.__dismantleUiInstalled) return;
  window.__dismantleUiInstalled = true;

  const tg = window.Telegram?.WebApp;
  let payload = null;

  const escD = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const userId = () => tg?.initDataUnsafe?.user?.id || null;

  function injectStyle() {
    if (document.querySelector('#dismantleStyles')) return;
    const style = document.createElement('style');
    style.id = 'dismantleStyles';
    style.textContent = `
      .dismantle-entry{margin:12px 0;border:1px solid #31506f;background:linear-gradient(180deg,#11263a,#0b1b2c);border-radius:20px;padding:16px;display:flex;align-items:center;justify-content:space-between;gap:12px;color:#eef7ff;box-shadow:0 12px 30px rgba(0,0,0,.18)}
      .dismantle-entry .de-left{display:flex;align-items:center;gap:12px;min-width:0}.dismantle-entry .de-icon{width:52px;height:52px;border-radius:16px;background:#ff9f2d;display:grid;place-items:center;font-size:26px;flex:0 0 auto}.dismantle-entry strong{display:block;font-size:14px}.dismantle-entry small{display:block;color:#8ca0b5;margin-top:4px;font-size:10px}.dismantle-entry .de-count{min-width:42px;height:42px;border-radius:50%;display:grid;place-items:center;border:1px solid #6b612b;background:#3d381a;color:#ffd65d;font-weight:800}
      .dismantle-overlay{position:fixed;inset:0;z-index:350;background:#071522;color:#eef7ff;overflow:auto;padding:calc(18px + env(safe-area-inset-top)) 14px calc(110px + env(safe-area-inset-bottom));}.dismantle-overlay.hidden{display:none}.dismantle-head{display:flex;align-items:center;gap:12px;margin-bottom:14px}.dismantle-back{width:42px;height:42px;border-radius:50%;border:1px solid #294963;background:#0b1e31;color:#fff;font-size:25px}.dismantle-head h2{margin:0;font-size:22px}.dismantle-head p{margin:3px 0 0;color:#8399ae;font-size:11px}
      .dismantle-kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0}.dismantle-kpis div{border:1px solid #29445f;background:#0b1c2e;border-radius:16px;padding:12px;text-align:center}.dismantle-kpis span{display:block;font-size:9px;color:#7f95ab}.dismantle-kpis strong{font-size:22px;display:block;margin-top:4px}
      .dismantle-chart{border:1px solid #29445f;background:#0b1c2e;border-radius:18px;padding:14px;margin:12px 0}.dismantle-chart h3{margin:0 0 12px;font-size:13px}.dismantle-bars{height:150px;display:flex;align-items:flex-end;gap:8px}.dismantle-bar-col{flex:1;min-width:0;text-align:center}.dismantle-bar-wrap{height:110px;display:flex;align-items:flex-end;justify-content:center}.dismantle-bar{width:min(24px,70%);min-height:4px;border-radius:8px 8px 3px 3px;background:linear-gradient(180deg,#ffb23e,#ff7f22)}.dismantle-bar-col b{display:block;font-size:10px;margin:4px 0}.dismantle-bar-col small{font-size:8px;color:#71869c}
      .dismantle-list{display:grid;gap:10px}.dismantle-order{border:1px solid #29445f;background:#0b1b2b;border-radius:16px;padding:14px}.dismantle-order strong{display:block;font-size:13px}.dismantle-order .do-inet{color:#5edcff;margin-top:3px;font-size:12px}.dismantle-order small{display:block;color:#8599ad;line-height:1.6;margin-top:8px;font-size:10px}.dismantle-done{width:100%;margin-top:12px;border:0;border-radius:13px;background:#1f9d62;color:white;padding:12px;font-weight:800;font-size:12px}.dismantle-done:disabled{opacity:.55}.dismantle-empty{border:1px dashed #36526d;border-radius:16px;padding:24px;text-align:center;color:#8498ad}
    `;
    document.head.appendChild(style);
  }

  function ensureEntry() {
    const page = document.querySelector('#ordersPage');
    const summary = document.querySelector('#myOrderSummary');
    if (!page || !summary) return;
    let entry = document.querySelector('#dismantleEntry');
    if (!entry) {
      entry = document.createElement('button');
      entry.type = 'button';
      entry.id = 'dismantleEntry';
      entry.className = 'dismantle-entry';
      entry.innerHTML = `<span class="de-left"><span class="de-icon">🧰</span><span><strong>DISMANTLE • NTE CRASH</strong><small id="dismantleEntrySub">Memuat order dismantle...</small></span></span><span id="dismantleEntryCount" class="de-count">0</span>`;
      entry.addEventListener('click', openDismantle);
      summary.parentNode.insertBefore(entry, summary);
    }
  }

  function ensureOverlay() {
    if (document.querySelector('#dismantleOverlay')) return;
    const overlay = document.createElement('section');
    overlay.id = 'dismantleOverlay';
    overlay.className = 'dismantle-overlay hidden';
    overlay.innerHTML = `
      <div class="dismantle-head"><button id="dismantleBack" class="dismantle-back">‹</button><div><h2>Order Dismantle</h2><p>NTE CRASH • data saja, tanpa CONFIG / REPORT / STO</p></div></div>
      <div class="dismantle-kpis"><div><span>OPEN</span><strong id="dismantleOpen">0</strong></div><div><span>SELESAI</span><strong id="dismantleDone">0</strong></div><div><span>TOTAL</span><strong id="dismantleTotal">0</strong></div></div>
      <section class="dismantle-chart"><h3>📊 Perolehan Dismantle • 7 Hari</h3><div id="dismantleBars" class="dismantle-bars"></div></section>
      <div style="display:flex;justify-content:space-between;align-items:center;margin:18px 2px 10px"><strong>Order OPEN</strong><span id="dismantleListCount" style="font-size:11px;color:#7f95ab">0 order</span></div>
      <div id="dismantleList" class="dismantle-list"></div>
    `;
    document.body.appendChild(overlay);
    document.querySelector('#dismantleBack').addEventListener('click', () => overlay.classList.add('hidden'));
  }

  async function fetchDismantle() {
    const id = userId();
    if (!id) throw new Error('Mini App harus dibuka dari Telegram.');
    const response = await fetch(`/api/dismantle-orders?telegram_id=${encodeURIComponent(id)}`, {cache:'no-store'});
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.message || 'Gagal membaca dismantle.');
    payload = data;
    return data;
  }

  function renderEntry(data) {
    ensureEntry();
    const count = document.querySelector('#dismantleEntryCount');
    const sub = document.querySelector('#dismantleEntrySub');
    if (count) count.textContent = String(data?.open_count || 0);
    if (sub) sub.textContent = `${data?.open_count || 0} order OPEN • ${data?.done_count || 0} selesai`;
  }

  function renderChart(data) {
    const box = document.querySelector('#dismantleBars');
    if (!box) return;
    const trend = data?.trend || [];
    const max = Math.max(1, ...trend.map(x => Number(x.total || 0)));
    box.innerHTML = trend.map(item => {
      const total = Number(item.total || 0);
      const height = total ? Math.max(12, Math.round(total / max * 100)) : 4;
      return `<div class="dismantle-bar-col"><div class="dismantle-bar-wrap"><div class="dismantle-bar" style="height:${height}%"></div></div><b>${total}</b><small>${escD(item.label)}</small></div>`;
    }).join('');
  }

  function renderOrders(data) {
    document.querySelector('#dismantleOpen').textContent = String(data.open_count || 0);
    document.querySelector('#dismantleDone').textContent = String(data.done_count || 0);
    document.querySelector('#dismantleTotal').textContent = String(data.total_count || 0);
    document.querySelector('#dismantleListCount').textContent = `${data.open_count || 0} order`;
    renderChart(data);
    const list = document.querySelector('#dismantleList');
    const orders = data.orders || [];
    if (!orders.length) {
      list.innerHTML = '<div class="dismantle-empty">✅ Semua order dismantle sudah selesai dikerjakan.</div>';
      return;
    }
    list.innerHTML = orders.map((o, i) => `
      <article class="dismantle-order" data-dismantle-id="${Number(o.id)}">
        <strong>${i + 1}. ${escD(o.customer_name || '-')}</strong>
        <div class="do-inet">🌐 ${escD(o.service_number || '-')}</div>
        <small>🏠 ${escD(o.address || '-')}<br>📞 CP: ${escD(o.customer_phone || '-')}<br>👷 ${escD(o.assigned_nik || '-')} • ${escD(o.assigned_name || '-')}</small>
        <button class="dismantle-done" data-finish-dismantle="${Number(o.id)}">✓ Selesai Dikerjakan</button>
      </article>
    `).join('');
    list.querySelectorAll('[data-finish-dismantle]').forEach(button => button.addEventListener('click', finishOrder));
  }

  async function openDismantle() {
    ensureOverlay();
    const overlay = document.querySelector('#dismantleOverlay');
    overlay.classList.remove('hidden');
    document.querySelector('#dismantleList').innerHTML = '<div class="dismantle-empty">Memuat order dismantle...</div>';
    try {
      const data = await fetchDismantle();
      renderEntry(data);
      renderOrders(data);
    } catch (error) {
      document.querySelector('#dismantleList').innerHTML = `<div class="dismantle-empty">❌ ${escD(error.message)}</div>`;
    }
  }

  async function finishOrder(event) {
    const button = event.currentTarget;
    const id = Number(button.dataset.finishDismantle || 0);
    const order = payload?.orders?.find(item => Number(item.id) === id);
    if (!id || !order) return;
    if (!window.confirm(`Tandai INET ${order.service_number} selesai dikerjakan?`)) return;
    button.disabled = true;
    button.textContent = 'Menyimpan...';
    try {
      const response = await fetch('/api/dismantle-orders/complete', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({telegram_id:String(userId()), id:String(id)})
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.message || 'Gagal menyimpan.');
      tg?.HapticFeedback?.notificationOccurred?.('success');
      const refreshed = await fetchDismantle();
      renderEntry(refreshed);
      renderOrders(refreshed);
    } catch (error) {
      button.disabled = false;
      button.textContent = '✓ Selesai Dikerjakan';
      window.alert(error.message || 'Gagal menyimpan dismantle.');
    }
  }

  async function refreshEntry() {
    try { renderEntry(await fetchDismantle()); } catch (_) { ensureEntry(); }
  }

  injectStyle();
  ensureEntry();
  ensureOverlay();
  refreshEntry();
  new MutationObserver(() => ensureEntry()).observe(document.body, {childList:true, subtree:true});
})();
