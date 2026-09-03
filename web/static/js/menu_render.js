// web/static/js/menu_render.js
// Render menu berdasarkan role yang dikembalikan oleh api/me.php
async function renderMenu() {
  try {
    const res = await fetch('/api/me.php');
    const data = await res.json();
    let role = 'TECHNICIAN';
    if (data.ok && data.user && data.user.role) role = data.user.role;

    // Update header branding
    const brandEls = document.querySelectorAll('.app-brand, #app-title');
    brandEls.forEach(e => e.textContent = 'BOT TEKNISI');

    // Replace PAYROLL menu label -> REKON
    const payrollEls = Array.from(document.querySelectorAll('[data-menu="payroll"], .menu-payroll'));
    payrollEls.forEach(e => e.textContent = 'REKON');

    // Bottom nav items: ensure icons/labels as requested
    const navDashboard = document.querySelector('[data-nav="dashboard"]'); if (navDashboard) navDashboard.innerHTML = '⌂<div>Dashboard</div>';
    const navOrder = document.querySelector('[data-nav="orderanku"]'); if (navOrder) navOrder.innerHTML = '▤<div>Orderanku</div>';
    const navInput = document.querySelector('[data-nav="input"]'); if (navInput) navInput.innerHTML = '＋<div>Input</div>';
    const navLaporan = document.querySelector('[data-nav="laporan"]'); if (navLaporan) navLaporan.innerHTML = '▥<div>Laporan</div>';
    const navRekon = document.querySelector('[data-nav="rekon"]'); if (navRekon) navRekon.innerHTML = '◎<div>Rekon</div>';

    // Role-based input menu
    const inputContainer = document.getElementById('input-menu');
    if (!inputContainer) return;
    inputContainer.innerHTML = '';
    if (role === 'TECHNICIAN') {
      inputContainer.innerHTML = `
        <button class="input-btn" data-action="config">CONFIG</button>
        <button class="input-btn" data-action="report">REPORT</button>
        <button class="input-btn" data-action="sto">STO</button>
        <button class="input-btn" data-action="lengkap">LENGKAP</button>
      `;
    } else if (role === 'HSA' || role === 'OSA' || role === 'ADMIN') {
      inputContainer.innerHTML = `<button class="input-btn" data-action="assign">ASSIGN WO</button>`;
    } else {
      // default: restrict to orderanku/dashboard
      inputContainer.innerHTML = `<div>Input tidak tersedia untuk role Anda</div>`;
    }
  } catch (err) {
    console.error('renderMenu error', err);
  }
}

// Run on load
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', renderMenu); else renderMenu();
