// Lightweight INJOKO-only dashboard patch. Runs once; no MutationObserver loop.
(function(){
  'use strict';
  function apply(){
    const page=document.querySelector('#dashboardPage');
    if(!page)return;
    const strip=page.querySelector('.filter-strip');
    if(strip){const groups=strip.querySelectorAll('.segmented');if(groups[0])groups[0].remove();}
    const areaPanel=page.querySelector('.area-panel');
    if(areaPanel)areaPanel.remove();
    if(typeof state!=='undefined')state.area='ALL';
    const label=page.querySelector('#activeAreaLabel');
    if(label)label.textContent='INJOKO';
    page.querySelectorAll('[data-area],[data-area-shortcut]').forEach(el=>el.remove());
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',apply,{once:true});else apply();
  setTimeout(apply,300);
})();
