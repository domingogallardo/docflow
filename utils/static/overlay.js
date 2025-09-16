(function(){
  const script = document.currentScript;
  const rel = script.dataset.path || '';
  let bumped = (script.dataset.bumped === '1');
  let published = (script.dataset.published === '1');
  let publishing = false;
  let unpublishing = false;
  let processing = false;
  const publicBase = script.dataset.publicBase || '';
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
    if(href){ const a = el('a', {href, target:'_blank', rel:'noopener'}, 'Ver'); t.appendChild(a); }
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
    if(publishing || !bumped || published) return;
    publishing = true; render(); msg.textContent = '⏳ publicando…'; msg.className = 'meta';
    const ok = await call('publish');
    msg.textContent = ok ? '✓ publicado' : '× error';
    msg.className = ok ? 'meta ok' : 'meta err';
    if(ok){
      published = true; render();
      const fname = rel.split('/').pop();
      const base = publicBase ? (publicBase.endsWith('/') ? publicBase : publicBase + '/') : '';
      const url = base ? (base + encodeURIComponent(fname)) : '';
      toast('ok', 'Publicado', url);
    } else {
      publishing = false; render();
      toast('err', 'Error publicando');
    }
  }
  async function processed(){
    if(processing || !bumped || !published) return;
    processing = true; render(); msg.textContent = 'procesando…';
    const ok = await call('processed');
    msg.textContent = ok ? '✓ procesado' : '× error';
    msg.className = ok ? 'meta ok' : 'meta err';
    if(ok){
      bumped = false; processing = false; render();
      toast('ok', 'Procesado');
    } else {
      processing = false; render();
      toast('err', 'Error en procesado');
    }
  }
  async function unpublish(){
    if(unpublishing || !published) return;
    unpublishing = true; render(); msg.textContent = '⏳ despublicando…'; msg.className = 'meta';
    const ok = await call('unpublish');
    msg.textContent = ok ? '✓ despublicado' : '× error';
    msg.className = ok ? 'meta ok' : 'meta err';
    if(ok){
      published = false; unpublishing = false; render();
      toast('ok', 'Despublicado');
    } else {
      unpublishing = false; render();
      toast('err', 'Error despublicando');
    }
  }
  function render(){
    bar.innerHTML = '';
    bar.appendChild(el('strong', null, '📄 ' + rel));
    const btn = el('button', null, bumped ? 'Unbump' : 'Bump');
    btn.addEventListener('click', async ()=>{
      const ok = await call(bumped ? 'unbump_now' : 'bump');
      msg.textContent = ok ? '✓ hecho' : '× error'; msg.className = ok ? 'meta ok' : 'meta err';
      if(ok){ bumped = !bumped; render(); }
    });
    bar.appendChild(btn);
    if(bumped && !published){
      const pub = el('button', null, 'Publicar');
      pub.title = 'Copiar a /web/public/read y desplegar';
      if(publishing){ pub.textContent = 'Publicando…'; pub.setAttribute('disabled',''); }
      pub.addEventListener('click', publish);
      bar.appendChild(pub);
    }
    if(published){
      const unp = el('button', null, 'Despublicar');
      unp.title = 'Eliminar de /web/public/read y desplegar';
      if(unpublishing){ unp.textContent = 'Despublicando…'; unp.setAttribute('disabled',''); }
      unp.addEventListener('click', unpublish);
      bar.appendChild(unp);
      if(bumped){
        const done = el('button', null, 'Procesado');
        done.title = 'Unbump (local y público) + añadir a read_posts.md + desplegar';
        if(processing){ done.textContent = 'Procesando…'; done.setAttribute('disabled',''); }
        done.addEventListener('click', processed);
        bar.appendChild(done);
      }
    }
    const raw = el('a', {href:'?raw=1', title:'Ver sin overlay'}, 'raw');
    bar.appendChild(raw); bar.appendChild(msg);
  }
  function isEditingTarget(t){ return t && (t.tagName==='INPUT' || t.tagName==='TEXTAREA' || t.isContentEditable); }
  const bar = el('div', {id:'dg-overlay'});
  const msg = el('span', {class:'meta', id:'dg-msg'}, '');
  document.addEventListener('keydown', async (e)=>{
    if(isEditingTarget(document.activeElement)) return;
    const k = (e.key || '').toLowerCase();
    if(k==='b'){
      e.preventDefault(); const ok = await call('bump'); if(ok){ bumped=true; render(); msg.textContent='✓ hecho'; msg.className='meta ok'; }
    }
    if(k==='u'){
      e.preventDefault(); const ok = await call('unbump_now'); if(ok){ bumped=false; render(); msg.textContent='✓ hecho'; msg.className='meta ok'; }
    }
    if(k==='l' && !e.metaKey && !e.ctrlKey && !e.altKey){ e.preventDefault(); goList(); }
    if(k==='p' && bumped && !published && !publishing){ e.preventDefault(); publish(); }
    if(k==='d' && published && !unpublishing){ e.preventDefault(); unpublish(); }
    if(k==='x' && bumped && published && !processing){ e.preventDefault(); processed(); }
  });
  document.addEventListener('DOMContentLoaded', ()=>{ document.body.appendChild(bar); render(); });
})();
