/* Minimal base JS for /read/ pages
 * - No visual changes
 * - Console API: ArticleJS.active / ArticleJS.ping()
 * - Quote capture helpers with Text Fragments and Markdown
 */
(function () {
  var version = '0.2.0';

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

  function buildTextFragmentFromText(text, mode) {
    // mode: 'simple' | 'range'. Default: 'simple'
    text = normText(text);
    if (!text) return '';
    if (mode === 'range') {
      // Use a start+end pair for better matching on complex pages
      var n = text.length;
      var head = text.slice(0, Math.min(60, n));
      var tail = text.slice(Math.max(0, n - 60));
      return '#:~:text=' + encodeURIComponent(head) + ',' + encodeURIComponent(tail);
    }
    // Simple full-text match
    return '#:~:text=' + encodeURIComponent(text);
  }

  function buildUrlWithFragment(text, opts) {
    opts = opts || {};
    var fragment = buildTextFragmentFromText(text, opts.mode || 'simple');
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
    var style = (opts.style || 'standard'); // 'standard' or 'requested'
    var q = mdEscape(quote);
    if (style === 'requested') {
      // Non-standard form as requested: "> cita (link)[URL]"
      return '> ' + q + ' (' + label + ')[' + url + ']';
    }
    // Standard Markdown: "> cita ([label](URL))"
    return '> ' + q + ' ([' + label + '](' + url + '))';
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
    var built = buildUrlWithFragment(text, opts);
    var md = buildQuoteMarkdown(text || document.title || '', built.url, opts);
    return { text: text, url: built.url, fragment: built.fragment, markdown: md };
  }

  function copyQuoteLink(opts) {
    var q = quoteFromSelection(opts);
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
})();
