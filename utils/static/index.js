(()=>{
  function send(action, rel, target){
    const params = {path: rel, action};
    if(target){ params.target = target; }
    const body = new URLSearchParams(params).toString();
    return fetch('/__bump', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body});
  }
  document.addEventListener('click', (e)=>{
    const a = e.target.closest('[data-dg-act]');
    if(!a) return;
    e.preventDefault();
    const action = a.getAttribute('data-dg-act');
    const rel = a.getAttribute('data-dg-path');
    const tgt = a.getAttribute('data-dg-target');
    if(!action || !rel) return;
    a.textContent = '…'; a.setAttribute('disabled','');
    send(action, rel, tgt).then(r=>{ if(r.ok){ location.reload(); } else { alert('Error'); a.removeAttribute('disabled'); } });
  });
})();
