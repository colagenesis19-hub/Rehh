// INJOKO-only dashboard: no MYR / MANYAR / JGR / JAGIR source or area filters.
(function(){
  'use strict';

  function isDashboard(){
    const page=document.querySelector('#dashboardPage');
    return !!page && !page.classList.contains('hidden');
  }

  function cleanDashboard(){
    const page=document.querySelector('#dashboardPage');
    if(!page) return;

    // Dashboard INJOKO is a single-source dashboard. Remove legacy area selector.
    const strip=page.querySelector('.filter-strip');
    if(strip){
      const groups=strip.querySelectorAll('.segmented');
      if(groups[0]) groups[0].remove();
      strip.style.display='grid';
    }

    // INJOKO has no Manyar/Jagir area breakdown on the main dashboard.
    page.querySelector('.area-panel')?.remove();

    // Force the dashboard state to the single INJOKO scope.
    if(typeof state!=='undefined') state.area='ALL';

    const areaLabel=document.querySelector('#activeAreaLabel');
    if(areaLabel) areaLabel.textContent='INJOKO';

    const periodPill=document.querySelector('#periodPillLabel');
    if(periodPill && !periodPill.textContent.trim()) periodPill.textContent='Hari Ini';

    // Remove legacy source/area wording if injected by another enhancement.
    const walker=document.createTreeWalker(page,NodeFilter.SHOW_TEXT);
    const nodes=[];
    while(walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node=>{
      let t=node.nodeValue||'';
      const cleaned=t.replace(/ORDER SHEET\s*\(MYR\)\s*\+\s*WORK ORDER JAGIR\s*\(JGR\)/gi,'INJOKO')
        .replace(/WORK ORDER JAGIR\s*\(JGR\)/gi,'INJOKO')
        .replace(/ORDER SHEET\s*\(MYR\)/gi,'INJOKO');
      if(cleaned!==t) node.nodeValue=cleaned;
    });
  }

  function init(){
    cleanDashboard();
    const root=document.querySelector('#dashboardPage');
    if(root && !root.dataset.injokoOnlyObserver){
      const observer=new MutationObserver(()=>{ if(isDashboard()) cleanDashboard(); });
      observer.observe(root,{childList:true,subtree:true,characterData:true});
      root.dataset.injokoOnlyObserver='1';
    }
  }

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
  setTimeout(init,300);
  setTimeout(init,1200);
})();
