(function(){
  const script = document.currentScript;
  const rel = script.dataset.path || '';
  let bumped = (script.dataset.bumped === '1');
  let published = (script.dataset.published === '1');
  let publishing = false;
  let unpublishing = false;
  let deleting = false;
  function el(tag, attrs, text){
    const e = document.createElement(tag);
    if(attrs){ for(const k in attrs){ e.setAttribute(k, attrs[k]); } }
    if(text){ e.textContent = text; }
    return e;
  }
  function toast(kind, text, href){
    let t = document.getElementById('dg-toast');
    if(!t){ t = el('div', {id:'dg-toast'}, ''); document.body.appendChild(t); }
    t.className = kind ? kind + ' show' : 'show';
    t.textContent = text || '';
    if(href){ const a = el('a', {href, target:'_blank', rel:'noopener'}, 'View'); t.appendChild(a); }
    clearTimeout(window.__dg_toast_timer);
    window.__dg_toast_timer = setTimeout(()=>{ t.classList.remove('show'); }, 2200);
  }
  async function call(action){
    const body = new URLSearchParams({path: rel, action}).toString();
    const res = await fetch('/__bump', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body});
    return res.ok;
  }
  function goList(){
    const p = window.location.pathname;
    const parent = p.endsWith('/') ? p : p.substring(0, p.lastIndexOf('/') + 1);
    window.location.href = parent || '/';
  }
  async function publish(){
    if(deleting || publishing || published) return;
    publishing = true; render(); msg.textContent = '⏳ publishing…'; msg.className = 'meta';
    const ok = await call('publish');
    msg.textContent = ok ? '✓ published' : '× error';
    msg.className = ok ? 'meta ok' : 'meta err';
    if(ok){
      published = true; render();
      toast('ok', 'Published');
    } else {
      publishing = false; render();
      toast('err', 'Publish failed');
    }
  }
  async function unpublish(){
    if(deleting || unpublishing || !published) return;
    unpublishing = true; render(); msg.textContent = '⏳ unpublishing…'; msg.className = 'meta';
    const ok = await call('unpublish');
    msg.textContent = ok ? '✓ unpublished' : '× error';
    msg.className = ok ? 'meta ok' : 'meta err';
    if(ok){
      published = false; unpublishing = false; render();
      toast('ok', 'Unpublished');
    } else {
      unpublishing = false; render();
      toast('err', 'Unpublish failed');
    }
  }
  async function removeFile(){
    if(deleting) return;
    const fname = rel.split('/').pop() || rel || 'this file';
    const question = `Are you sure you want to delete "${fname}"?`;
    if(!window.confirm(question)) return;
    deleting = true;
    render();
    msg.textContent = '⏳ deleting…'; msg.className = 'meta';
    const ok = await call('delete');
    msg.textContent = ok ? '✓ deleted' : '× error';
    msg.className = ok ? 'meta ok' : 'meta err';
    deleting = false;
    if(ok){
      toast('ok', 'Deleted');
      setTimeout(()=>{ goList(); }, 350);
    } else {
      render();
      toast('err', 'Delete failed');
    }
  }
  function render(){
    bar.innerHTML = '';
    const btn = el('button', null, bumped ? 'Unbump' : 'Bump');
    btn.addEventListener('click', async ()=>{
      if(deleting) return;
      const ok = await call(bumped ? 'unbump_now' : 'bump');
      msg.textContent = ok ? '✓ done' : '× error'; msg.className = ok ? 'meta ok' : 'meta err';
      if(ok){ bumped = !bumped; render(); }
    });
    if(deleting){ btn.setAttribute('disabled',''); }
    bar.appendChild(btn);
    if(!published){
      const pub = el('button', null, 'Publish');
      pub.title = 'Copy to /web/public/read and deploy';
      if(publishing){ pub.textContent = 'Publishing…'; pub.setAttribute('disabled',''); }
      if(deleting){ pub.setAttribute('disabled',''); }
      pub.addEventListener('click', publish);
      bar.appendChild(pub);
    }
    if(published){
      const unp = el('button', null, 'Unpublish');
      unp.title = 'Remove from /web/public/read and deploy';
      if(unpublishing){ unp.textContent = 'Unpublishing…'; unp.setAttribute('disabled',''); }
      if(deleting){ unp.setAttribute('disabled',''); }
      unp.addEventListener('click', unpublish);
      bar.appendChild(unp);
    }
    const del = el('button', null, deleting ? 'Deleting…' : 'Delete');
    del.title = 'Delete the file and return to the listing';
    if(deleting){
      del.setAttribute('disabled','');
    } else {
      del.addEventListener('click', removeFile);
    }
    bar.appendChild(del);
  }
  function isEditingTarget(t){ return t && (t.tagName==='INPUT' || t.tagName==='TEXTAREA' || t.isContentEditable); }
  const bar = el('div', {id:'dg-overlay'});
  const msg = el('span', {class:'meta', id:'dg-msg'}, '');
  document.addEventListener('keydown', async (e)=>{
    if(isEditingTarget(document.activeElement)) return;
    if(deleting) return;
    const k = (e.key || '').toLowerCase();
    if(k==='b'){
      e.preventDefault(); const ok = await call('bump'); if(ok){ bumped=true; render(); msg.textContent='✓ done'; msg.className='meta ok'; }
    }
    if(k==='u'){
      e.preventDefault(); const ok = await call('unbump_now'); if(ok){ bumped=false; render(); msg.textContent='✓ done'; msg.className='meta ok'; }
    }
    if(k==='l' && !e.metaKey && !e.ctrlKey && !e.altKey){ e.preventDefault(); goList(); }
    if(k==='p' && !published && !publishing){ e.preventDefault(); publish(); }
    if(k==='d' && published && !unpublishing){ e.preventDefault(); unpublish(); }
  });
  document.addEventListener('DOMContentLoaded', ()=>{ document.body.appendChild(bar); render(); });
})();
