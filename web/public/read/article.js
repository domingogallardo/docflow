/* Minimal base JS for /read/ pages
 * - No visual changes
 * - Console API: ArticleJS.active / ArticleJS.ping()
 * - Quote capture helpers with Text Fragments and Markdown
 */
(function () {
  var version = '0.3.0';

  function baseUrlWithoutHash() {
    try { return String(location.href).split('#')[0]; } catch (_) { return ''; }
  }

  function normText(s) {
    if (!s) return '';
    // Collapse whitespace and trim
    s = String(s).replace(/\s+/g, ' ').trim();
    // Avoid very long fragments (practical reliability + URL length)
    var MAX = 400;
    if (s.length > MAX) s = s.slice(0, MAX) + '…';
    return s;
  }

  function selectionText() {
    try {
      var sel = window.getSelection && window.getSelection();
      var t = sel && sel.toString ? sel.toString() : '';
      return normText(t);
    } catch (_) { return ''; }
  }

  function buildTextFragmentFromText(text, mode, opts) {
    // mode: 'simple' | 'range'
    text = normText(text);
    if (!text) return '';
    mode = mode || 'range';
    if (mode === 'range') {
      opts = opts || {};
      var hw = Math.max(1, opts.headWords || 3);
      var tw = Math.max(1, opts.tailWords || 3);
      var words = text.split(/\s+/);
      if (words.length <= hw + tw) {
        // Too short; fall back to simple
        return '#:~:text=' + encodeURIComponent(text);
      }
      var head = words.slice(0, hw).join(' ').replace(/[\s\.,;:!\?\-–—]+$/,'');
      var tail = words.slice(words.length - tw).join(' ').replace(/^[\s\.,;:!\?\-–—]+/,'');
      return '#:~:text=' + encodeURIComponent(head) + ',' + encodeURIComponent(tail);
    }
    // Simple full-text match
    return '#:~:text=' + encodeURIComponent(text);
  }

  function buildUrlWithFragment(text, opts) {
    opts = opts || {};
    var fragment = buildTextFragmentFromText(text, opts.mode || 'range', opts);
    var base = baseUrlWithoutHash();
    return { url: base + fragment, fragment: fragment };
  }

  function mdEscape(s) {
    // Minimal escaping for Markdown blockquote content
    return String(s).replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function buildQuoteMarkdown(quote, url, opts) {
    opts = opts || {};
    var label = (opts.label || 'link');
    var q = mdEscape(quote);
    // Markdown inline link after the quote: "> cita [label](URL)"
    return '> ' + q + ' [' + label + '](' + url + ')';
  }

  function copyToClipboard(text) {
    return new Promise(function (resolve) {
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(function(){ resolve(true); }, function(){ resolve(false); });
          return;
        }
      } catch (_) {}
      try {
        var ta = document.createElement('textarea');
        ta.value = text; ta.setAttribute('readonly',''); ta.style.position='fixed'; ta.style.opacity='0'; ta.style.top='-1000px';
        document.body.appendChild(ta); ta.select();
        var ok = false;
        try { ok = document.execCommand('copy'); } catch (_) { ok = false; }
        document.body.removeChild(ta);
        resolve(!!ok);
      } catch (_) { resolve(false); }
    });
  }

  function quoteFromSelection(opts) {
    opts = opts || {};
    var text = selectionText();
    // Defaults biased towards Safari working highlights
    if (!('mode' in opts)) opts.mode = 'range';
    if (!('headWords' in opts)) opts.headWords = 3;
    if (!('tailWords' in opts)) opts.tailWords = 3;
    var built = buildUrlWithFragment(text, opts);
    var md = buildQuoteMarkdown(text || document.title || '', built.url, opts);
    return { text: text, url: built.url, fragment: built.fragment, markdown: md };
  }

  function copyQuoteLink(opts) {
    var q = quoteFromSelection(opts || {});
    return copyToClipboard(q.markdown).then(function(ok){
      if (typeof console !== 'undefined') {
        if (ok) console.log('✓ Copiado', q.markdown);
        else console.warn('No se pudo copiar automáticamente. Resultado:', q.markdown);
      }
      return q;
    });
  }

  var api = {
    active: true,
    version: version,
    ping: function () { return 'ok'; },
    // Quote helpers
    selectionText: selectionText,
    buildUrlWithFragment: buildUrlWithFragment,
    buildQuoteMarkdown: buildQuoteMarkdown,
    quoteFromSelection: quoteFromSelection,
    copyQuoteLink: copyQuoteLink
  };

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
      var t = selectionText();
      if (t && t.length >= 2) {
        btn.style.display = 'block';
        btn.style.opacity = '.95';
        btn.style.transform = 'translateY(0)';
      } else {
        btn.style.opacity = '.92';
        btn.style.transform = 'translateY(8px)';
        btn.style.display = 'none';
      }
    }

    document.addEventListener('selectionchange', updateVisibility, { passive: true });
    window.addEventListener('resize', updateVisibility, { passive: true });
    document.addEventListener('visibilitychange', updateVisibility, { passive: true });

    btn.addEventListener('click', function(){
      btn.disabled = true;
      copyQuoteLink({ label: 'link', style: 'requested' })
        .then(function(res){ showToast('Copiado', true); })
        .catch(function(){ showToast('No se pudo copiar', false); })
        .finally(function(){ btn.disabled = false; updateVisibility(); });
    });

    // Initial state
    if (document.readyState === 'complete') updateVisibility();
    else window.addEventListener('load', updateVisibility, { once: true, passive: true });
    return btn;
  }

  try {
    Object.defineProperty(window, 'ArticleJS', {
      value: api,
      enumerable: true,
      configurable: false,
      writable: false
    });
  } catch (e) {
    window.ArticleJS = api;
  }
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
})();
