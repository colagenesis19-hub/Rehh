// INJOKO HTML branding patch: keeps the existing Mini App structure intact.
(function(){
  'use strict';
  const replaceText = () => {
    document.title = 'INJOKO - Dashboard';
    document.querySelectorAll('body *').forEach(el => {
      if (el.children.length !== 0) return;
      const text = el.textContent || '';
      if (/Kerja BOT/i.test(text)) el.textContent = text.replace(/Kerja BOT/gi, 'INJOKO');
      if (/Payroll/i.test(el.textContent || '')) el.textContent = el.textContent.replace(/Payroll/gi, 'Rekon');
    });
    document.querySelectorAll('.payroll-nav small').forEach(el => { el.textContent = 'Rekon'; });
    const inputSub = document.querySelector('#inputPage .tool-sub');
    if (inputSub) inputSub.textContent = 'Pilih workflow. Data yang tersedia akan terisi otomatis; teknisi hanya mengisi yang masih kosong.';
  };
  const boot = () => {
    replaceText();
    if (!document.body || window.__injokoHtmlObserver) return;
    const observer = new MutationObserver(replaceText);
    observer.observe(document.body, {subtree:true, childList:true, characterData:true});
    window.__injokoHtmlObserver = observer;
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true});
  else boot();
})();
