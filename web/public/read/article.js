/* Minimal base JS for /read/ pages
 * - No visual changes
 * - Console API: ArticleJS.active / ArticleJS.ping()
 * - Quote capture helpers with Text Fragments and Markdown
 */
(function () {
  var version = '1.0.0';

  // -- Minimal helpers: longer head/tail slices to scope text fragments better --
  function baseUrlWithoutHash() {
    try { return String(location.href).split('#')[0]; } catch (_) { return ''; }
  }
  function normalizeWhitespace(value) {
    return String(value || '').replace(/\s+/g, ' ').trim();
  }

  function getSelectionText() {
    try {
      var sel = window.getSelection && window.getSelection();
      var t = sel && sel.toString ? sel.toString() : '';
      return normalizeWhitespace(t);
    } catch (_) { return ''; }
  }

  function escapeMarkdownText(value) {
    return String(value || '')
      .replace(/[\\`*_{}\[\]]/g, '\\$&')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function toAbsoluteUrl(href) {
    if (!href) return '';
    try {
      return new URL(String(href), baseUrlWithoutHash()).toString();
    } catch (_) {
      return String(href);
    }
  }

  function markdownFromChildren(node) {
    var out = '';
    if (!node) return out;
    for (var child = node.firstChild; child; child = child.nextSibling) {
      out += markdownFromNode(child);
    }
    return out;
  }

  function markdownFromNode(node) {
    if (!node) return '';
    if (node.nodeType === 3) {
      return escapeMarkdownText(node.nodeValue || '');
    }
    if (node.nodeType !== 1) {
      return '';
    }
    var tag = (node.nodeName || '').toLowerCase();
    if (tag === 'a') {
      var inner = markdownFromChildren(node);
      if (!inner) inner = escapeMarkdownText(node.textContent || '');
      var href = node.getAttribute('href') || '';
      if (!href) return inner;
      var abs = toAbsoluteUrl(href);
      return '[' + inner + '](' + abs + ')';
    }
    if (tag === 'br') {
      return '\n';
    }
    if (tag === 'code') {
      return '`' + markdownFromChildren(node) + '`';
    }
    if (tag === 'em' || tag === 'i') {
      return '*' + markdownFromChildren(node) + '*';
    }
    if (tag === 'strong' || tag === 'b') {
      return '**' + markdownFromChildren(node) + '**';
    }
    return markdownFromChildren(node);
  }

  function fragmentToMarkdown(fragmentRoot) {
    if (!fragmentRoot) return '';
    return markdownFromChildren(fragmentRoot);
  }

  function snapshotFromText(text) {
    var normalized = normalizeWhitespace(text);
    if (!normalized) return null;
    var escaped = escapeMarkdownText(normalized);
    return { text: normalized, markdown: normalizeWhitespace(escaped) };
  }

  function captureSelectionSnapshot() {
    try {
      var sel = window.getSelection && window.getSelection();
      if (!sel || !sel.rangeCount) return null;
      var container = document.createElement('div');
      var hasContent = false;
      for (var i = 0; i < sel.rangeCount; i++) {
        var range = sel.getRangeAt(i);
        if (!range || range.collapsed) continue;
        hasContent = true;
        container.appendChild(range.cloneContents());
      }
      if (!hasContent) return null;
      var text = normalizeWhitespace(container.textContent || '');
      if (!text) return null;
      var markdown = fragmentToMarkdown(container);
      markdown = normalizeWhitespace(markdown || '');
      if (!markdown) markdown = normalizeWhitespace(escapeMarkdownText(text));
      return { text: text, markdown: markdown };
    } catch (_) {
      return null;
    }
  }

  function ensureSnapshot(value) {
    if (!value) return null;
    if (typeof value === 'string') return snapshotFromText(value);
    if (typeof value === 'object' && typeof value.text === 'string') {
      var normalized = normalizeWhitespace(value.text);
      if (!normalized) return null;
      var markdown = (typeof value.markdown === 'string') ? value.markdown : '';
      if (!markdown) markdown = escapeMarkdownText(normalized);
      return {
        text: normalized,
        markdown: normalizeWhitespace(markdown)
      };
    }
    return null;
  }
  function stripEdgePunctuation(value) {
    return String(value || '').replace(/^[\s\.,;:!\?\-–—]+/, '').replace(/[\s\.,;:!\?\-–—]+$/, '');
  }

  function buildFragment(text) {
    text = stripEdgePunctuation(String(text).replace(/\s+/g, ' ').trim());
    if (!text) return '';
    var words = text.split(/\s+/);
    if (words.length <= 10) {
      return '#:~:text=' + encodeURIComponent(stripEdgePunctuation(text));
    }
    var snippetSize = Math.max(4, Math.min(8, Math.ceil(words.length / 4)));
    if (words.length <= snippetSize * 2) {
      return '#:~:text=' + encodeURIComponent(text);
    }
    var head = words.slice(0, snippetSize).join(' ').replace(/[\s\.,;:!\?\-–—]+$/, '');
    var tail = words.slice(words.length - snippetSize).join(' ').replace(/^[\s\.,;:!\?\-–—]+/, '');
    if (!head || !tail) {
      return '#:~:text=' + encodeURIComponent(text);
    }
    return '#:~:text=' + encodeURIComponent(head) + ',' + encodeURIComponent(tail);
  }
  function buildMarkdown(displayText, inlineMarkdown, url) {
    var quoteMd = inlineMarkdown && inlineMarkdown.length ? inlineMarkdown : escapeMarkdownText(displayText || '');
    var linkUrl = String(url || '');
    if (linkUrl && (linkUrl.indexOf('(') !== -1 || linkUrl.indexOf(')') !== -1)) {
      linkUrl = linkUrl.replace(/\(/g, '%28').replace(/\)/g, '%29');
    }
    return '> ' + quoteMd + ' [link](<' + linkUrl + '>)';
  }
  // (UA checks removed to keep it simple)


  function fallbackCopyUsingExecCommand(text) {
    var doc = document;
    if (!doc) return false;
    var root = doc.body || doc.documentElement;
    if (!root) return false;

    var textarea = doc.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.cssText = [
      'position:fixed',
      'top:-9999px',
      'opacity:0',
      'pointer-events:none'
    ].join(';');

    var selection = null;
    var ranges = [];
    try {
      selection = doc.getSelection && doc.getSelection();
      if (selection && selection.rangeCount) {
        for (var i = 0; i < selection.rangeCount; i++) {
          try { ranges.push(selection.getRangeAt(i)); } catch (_) {}
        }
      }
    } catch (_) {
      selection = null;
      ranges = [];
    }

    var active = null;
    try { active = doc.activeElement || null; }
    catch (_) { active = null; }

    root.appendChild(textarea);

    var ok = false;
    try {
      textarea.focus();
      textarea.select();
      try {
        ok = !!(doc.execCommand && doc.execCommand('copy'));
      } catch (_) {
        ok = false;
      }
    } catch (_) {
      ok = false;
    }

    if (selection && selection.removeAllRanges) {
      try {
        selection.removeAllRanges();
        for (var j = 0; j < ranges.length; j++) {
          try { selection.addRange(ranges[j]); } catch (_) {}
        }
      } catch (_) {}
    }

    if (active && typeof active.focus === 'function' && active !== textarea) {
      try { active.focus(); } catch (_) {}
    }

    if (typeof textarea.remove === 'function') textarea.remove();
    else if (textarea.parentNode) textarea.parentNode.removeChild(textarea);

    return ok;
  }

  function copyToClipboard(text) {
    text = String(text || '');
    if (!text) return Promise.resolve(false);

    function fallback() {
      return Promise.resolve(fallbackCopyUsingExecCommand(text));
    }

    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text)
          .then(function(){ return true; })
          .catch(function(){ return fallback(); });
      }
    } catch (_) {}
    return fallback();
  }
  function copyQuote(preCaptured) {
    var snapshot = ensureSnapshot(preCaptured) || captureSelectionSnapshot() || null;
    var selectionText = snapshot ? snapshot.text : '';
    var displayText = selectionText || normalizeWhitespace(document.title || '');
    if (!displayText) displayText = '';
    var inlineMarkdown = snapshot ? snapshot.markdown : '';
    if (!inlineMarkdown) inlineMarkdown = normalizeWhitespace(escapeMarkdownText(displayText));
    var url = baseUrlWithoutHash() + buildFragment(selectionText);
    var md = buildMarkdown(displayText, inlineMarkdown, url);
    return copyToClipboard(md).then(function(ok){
      return { ok: ok, text: selectionText || displayText, url: url, markdown: md };
    });
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
    btn.textContent = '❝ Copy quote';
    btn.setAttribute('aria-label', 'Copy selected quote');
    btn.title = 'Copy selected quote';
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
    var lastSnapshot = null;
    var pressedSnapshot = null;

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
      toast.textContent = text || (ok ? 'Copied' : 'Copy failed');
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
      if (t) {
        var snap = captureSelectionSnapshot();
        if (snap) {
          lastSnapshot = snap;
        } else if (!lastSnapshot || lastSnapshot.text !== t) {
          lastSnapshot = snapshotFromText(t);
        }
      }
      var visible = t && t.length >= 2;
      btn.style.display = visible ? 'block' : 'none';
      btn.style.opacity = visible ? '.95' : '.92';
      btn.style.transform = visible ? 'translateY(0)' : 'translateY(8px)';
    }

    document.addEventListener('selectionchange', updateVisibility, { passive: true });
    // (no resize/visibilitychange): selectionchange is enough

    // iOS: capture selection early to use it on click (no copy yet)
    btn.addEventListener('pointerdown', function(){ pressedSnapshot = captureSelectionSnapshot() || lastSnapshot; }, { passive: true, capture: true });
    // Pointer Events cubre tap/click en Safari/iOS modernos

    btn.addEventListener('click', function(){
      btn.disabled = true;
      var useSnapshot = pressedSnapshot || captureSelectionSnapshot() || lastSnapshot;
      pressedSnapshot = null;
      if (!useSnapshot || !useSnapshot.text || useSnapshot.text.length < 2) {
        showToast('Select some text', false);
        btn.disabled = false;
        updateVisibility();
        return;
      }
      copyQuote(useSnapshot)
        .then(function(res){ showToast((res && res.ok) ? 'Copied' : 'Copy failed', !!(res && res.ok)); })
        .catch(function(){ showToast('Copy failed', false); })
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
  // (no extra fallback): the browser handles fragment navigation
})();
