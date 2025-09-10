/* Minimal base JS for /read/ pages
 * - No visual changes
 * - Console API: ArticleJS.active / ArticleJS.ping()
 * - Quote capture helpers with Text Fragments and Markdown
 */
(function () {
  var version = '1.0.0';

  // -- Minimal helpers: fixed behavior (3 head words + 3 tail words) --
  function baseUrlWithoutHash() {
    try { return String(location.href).split('#')[0]; } catch (_) { return ''; }
  }
  function getSelectionText() {
    try {
      var sel = window.getSelection && window.getSelection();
      var t = sel && sel.toString ? sel.toString() : '';
      return String(t).replace(/\s+/g, ' ').trim();
    } catch (_) { return ''; }
  }
  function buildFragment(text) {
    text = String(text).replace(/\s+/g, ' ').trim();
    if (!text) return '';
    var words = text.split(/\s+/);
    if (words.length <= 6) {
      return '#:~:text=' + encodeURIComponent(text);
    }
    var head = words.slice(0, 3).join(' ').replace(/[\s\.,;:!\?\-–—]+$/, '');
    var tail = words.slice(words.length - 3).join(' ').replace(/^[\s\.,;:!\?\-–—]+/, '');
    return '#:~:text=' + encodeURIComponent(head) + ',' + encodeURIComponent(tail);
  }
  function buildMarkdown(quote, url) {
    var q = String(quote).replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return '> ' + q + ' [link](' + url + ')';
  }
  // (UA checks eliminados para simplificar)


  function copyToClipboard(text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text).then(function(){ return true; }, function(){ return false; });
      }
    } catch (_) {}
    return Promise.resolve(false);
  }
  function copyQuote(preCaptured) {
    var text = (typeof preCaptured === 'string' && preCaptured) ? preCaptured : getSelectionText();
    var url = baseUrlWithoutHash() + buildFragment(text);
    var md = buildMarkdown(text || document.title || '', url);
    return copyToClipboard(md).then(function(ok){ return { ok: ok, text: text, url: url, markdown: md }; });
  }

  var api = { active: true, version: version, copyQuote: copyQuote };

  // ---- Discreet overlay button to copy current selection as Markdown ----
  function ensureOverlay() {
    var id = 'articlejs-quote-btn';
    var btn = document.getElementById(id);
    if (btn) return btn;
    btn = document.createElement('button');
    btn.id = id;
    btn.type = 'button';
    btn.textContent = '❝ Copiar cita';
    btn.setAttribute('aria-label', 'Copiar cita seleccionada');
    btn.title = 'Copiar cita seleccionada';
    // Inline, minimal styling (discreet, rounded pill)
    btn.style.cssText = [
      'position:fixed',
      'right:12px',
      'bottom:calc(12px + env(safe-area-inset-bottom, 0))',
      'z-index:2147483646',
      'background:#333',
      'color:#fff',
      'border:0',
      'border-radius:999px',
      'padding:10px 12px',
      'font:13px -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif',
      'line-height:1',
      'box-shadow:0 4px 14px rgba(0,0,0,.18)',
      'opacity:.92',
      'transform:translateY(8px)',
      'transition:opacity .15s ease, transform .15s ease',
      'display:none',
      'cursor:pointer'
    ].join(';');
    document.documentElement.appendChild(btn);

    // Track selection so iOS tap (which clears selection on focus change) still captures it
    var lastSelection = '';
    var pressedSelection = '';

    // Toast (reuses button as anchor for screen readers)
    var toast = document.createElement('div');
    toast.id = 'articlejs-toast';
    toast.setAttribute('role', 'status');
    toast.setAttribute('aria-live', 'polite');
    toast.style.cssText = [
      'position:fixed',
      'right:12px',
      'bottom:calc(56px + env(safe-area-inset-bottom, 0))',
      'z-index:2147483646',
      'background:#0a0',
      'color:#fff',
      'border-radius:10px',
      'padding:8px 10px',
      'font:13px -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif',
      'box-shadow:0 6px 18px rgba(0,0,0,.18)',
      'opacity:0',
      'transform:translateY(8px)',
      'transition:opacity .15s ease, transform .15s ease',
      'pointer-events:none'
    ].join(';');
    document.documentElement.appendChild(toast);

    var toastTimer = 0;
    function showToast(text, ok) {
      toast.textContent = text || (ok ? 'Copiado' : 'No se pudo copiar');
      toast.style.background = ok ? '#0a0' : '#a00';
      toast.style.opacity = '1';
      toast.style.transform = 'translateY(0)';
      if (toastTimer) window.clearTimeout(toastTimer);
      toastTimer = window.setTimeout(function(){
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(8px)';
      }, 1600);
    }

    function updateVisibility() {
      var t = getSelectionText();
      if (t) lastSelection = t;
      var visible = t && t.length >= 2;
      btn.style.display = visible ? 'block' : 'none';
      btn.style.opacity = visible ? '.95' : '.92';
      btn.style.transform = visible ? 'translateY(0)' : 'translateY(8px)';
    }

    document.addEventListener('selectionchange', updateVisibility, { passive: true });
    // (sin resize/visibilitychange): suficiente con selectionchange

    // iOS: captura temprana de selección para usarla en el click (sin copiar aún)
    btn.addEventListener('pointerdown', function(){ pressedSelection = getSelectionText() || lastSelection; }, { passive: true, capture: true });
    // Pointer Events cubre tap/click en Safari/iOS modernos

    btn.addEventListener('click', function(){
      btn.disabled = true;
      var useText = pressedSelection || lastSelection || getSelectionText();
      pressedSelection = '';
      if (!useText || useText.length < 2) {
        showToast('Selecciona un texto', false);
        btn.disabled = false;
        updateVisibility();
        return;
      }
      copyQuote(useText)
        .then(function(res){ showToast((res && res.ok) ? 'Copiado' : 'No se pudo copiar', !!(res && res.ok)); })
        .catch(function(){ showToast('No se pudo copiar', false); })
        .finally(function(){ btn.disabled = false; updateVisibility(); });
    });

    // Initial state
    if (document.readyState === 'complete') updateVisibility();
    else window.addEventListener('load', updateVisibility, { once: true, passive: true });
    return btn;
  }

  try { Object.defineProperty(window, 'ArticleJS', { value: api, enumerable: true }); }
  catch (e) { window.ArticleJS = api; }
  if (typeof console !== 'undefined' && console.debug) {
    console.debug('[article-js] active', version);
  }
  // Initialize overlay late to ensure DOM is ready
  if (document && document.addEventListener) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', ensureOverlay, { once: true, passive: true });
    } else {
      ensureOverlay();
    }
  }
  // (sin fallback extra): delegamos el salto a fragmentos en el navegador
})();
