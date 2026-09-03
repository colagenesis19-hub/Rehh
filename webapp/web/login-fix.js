(function(){
  'use strict';
  function init(){
    const form=document.getElementById('loginForm');
    const nik=document.getElementById('loginNik');
    const password=document.getElementById('loginPassword');
    const error=document.getElementById('loginError');
    const login=document.getElementById('loginView');
    const app=document.getElementById('appView');
    if(!form||!nik||!password)return;
    form.addEventListener('submit',async function(ev){
      ev.preventDefault();
      ev.stopImmediatePropagation();
      if(error) error.textContent='Memeriksa login...';
      try{
        const res=await fetch('/api/web-login',{
          method:'POST',
          credentials:'same-origin',
          cache:'no-store',
          headers:{'Content-Type':'application/json','Accept':'application/json'},
          body:JSON.stringify({nik:nik.value.trim(),password:password.value})
        });
        const data=await res.json().catch(function(){return {ok:false,message:'Server mengirim response tidak valid.'};});
        if(!res.ok||!data.ok) throw new Error(data.message||data.error||('Login gagal (HTTP '+res.status+')'));
        password.value='';
        login.classList.add('hidden');
        app.classList.remove('hidden');
        window.dispatchEvent(new CustomEvent('injoko-web-login',{detail:data.user||null}));
      }catch(err){
        if(error) error.textContent=err.message||'Login gagal.';
      }
    },true);
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init); else init();
})();
