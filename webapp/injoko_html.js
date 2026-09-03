// INJOKO HTML branding patch.
// Intentionally runs only after the DOM is ready and does not observe every mutation.
(function(){
  'use strict';

  function replaceTextOnce(){
    document.title = 'INJOKO - Dashboard';

    document.querySelectorAll('body *').forEach(function(el){
      if (el.children.length !== 0) return;
      var text = el.textContent || '';
      if (/Kerja BOT/i.test(text)) {
        el.textContent = text.replace(/Kerja BOT/gi, 'INJOKO');
      } else if (/Payroll/i.test(text)) {
        el.textContent = text.replace(/Payroll/gi, 'Rekon');
      }
    });

    document.querySelectorAll('.payroll-nav small').forEach(function(el){
      el.textContent = 'Rekon';
    });

    var inputSub = document.querySelector('#inputPage .tool-sub');
    if (inputSub) {
      inputSub.textContent = 'Pilih workflow. Data yang tersedia akan terisi otomatis; teknisi hanya mengisi yang masih kosong.';
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', replaceTextOnce, {once:true});
  } else {
    replaceTextOnce();
  }
})();
