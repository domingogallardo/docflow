/* Minimal base JS for /read/ pages
 * - Discreet overlay actions (copy quote + highlight)
 * - Console API: ArticleJS.active / ArticleJS.ping()
 * - Quote capture helpers with Text Fragments and Markdown
 * - Highlights persisted to /data/highlights/
 */
(function () {
  var version = '1.1.0';

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

  function captureSelectionRange() {
    try {
      var sel = window.getSelection && window.getSelection();
      if (!sel || !sel.rangeCount) return null;
      var range = sel.getRangeAt(0);
      if (!range || range.collapsed) return null;
      return range.cloneRange();
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

  function nowIso() {
    try { return new Date().toISOString(); } catch (_) { return ''; }
  }

  function makeId() {
    return 'h_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  }

  function getRootElement() {
    return document && document.body ? document.body : null;
  }

  function getHighlightKey() {
    var path = '';
    try { path = String(location.pathname || ''); } catch (_) { path = ''; }
    var name = path.split('/').pop() || 'read-index';
    if (!name || name === 'read' || name === 'read.html') name = 'read-index';
    try { name = decodeURIComponent(name); } catch (_) {}
    return encodeURIComponent(name);
  }

  function getHighlightStoreUrl() {
    var key = getHighlightKey();
    if (!key) return '';
    return '/data/highlights/' + key + '.json';
  }

  function ensureHighlightStyles() {
    if (!document) return;
    var id = 'articlejs-highlight-style';
    if (document.getElementById(id)) return;
    var style = document.createElement('style');
    style.id = id;
    style.textContent = [
      '.articlejs-highlight {',
      '  background-image: linear-gradient(transparent 60%, rgba(255, 229, 122, 0.85) 60%);',
      '  box-decoration-break: clone;',
      '  -webkit-box-decoration-break: clone;',
      '  padding: 0 2px;',
      '  border-radius: 2px;',
      '}'
    ].join('\n');
    var head = document.head || document.documentElement;
    if (head) head.appendChild(style);
  }

  function isSkippableTextNode(node) {
    if (!node || !node.parentNode) return true;
    var el = node.parentElement;
    while (el) {
      if (el.getAttribute && el.getAttribute('data-articlejs-ui') === '1') return true;
      var tag = (el.nodeName || '').toLowerCase();
      if (tag === 'script' || tag === 'style' || tag === 'noscript') return true;
      el = el.parentElement;
    }
    return false;
  }

  function buildTextIndex(root) {
    var nodes = [];
    var text = '';
    if (!root || !document.createTreeWalker || typeof NodeFilter === 'undefined') {
      return { text: text, nodes: nodes };
    }
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function(node) {
        if (!node || !node.nodeValue) return NodeFilter.FILTER_REJECT;
        if (isSkippableTextNode(node)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    while (walker.nextNode()) {
      var node = walker.currentNode;
      var value = node.nodeValue || '';
      if (!value) continue;
      var start = text.length;
      text += value;
      nodes.push({ node: node, start: start, end: start + value.length });
    }
    return { text: text, nodes: nodes };
  }

  function findMatchIndex(fullText, target, prefix, suffix) {
    if (!target) return -1;
    var start = 0;
    while (true) {
      var idx = fullText.indexOf(target, start);
      if (idx === -1) return -1;
      var ok = true;
      if (prefix) {
        var actualPrefix = fullText.slice(Math.max(0, idx - prefix.length), idx);
        var expectedPrefix = prefix.slice(prefix.length - actualPrefix.length);
        if (actualPrefix !== expectedPrefix) ok = false;
      }
      if (suffix && ok) {
        var actualSuffix = fullText.slice(idx + target.length, idx + target.length + suffix.length);
        var expectedSuffix = suffix.slice(0, actualSuffix.length);
        if (actualSuffix !== expectedSuffix) ok = false;
      }
      if (ok) return idx;
      start = idx + target.length;
    }
  }

  function rangeFromIndices(indexData, startIndex, endIndex) {
    if (!indexData || !indexData.nodes || startIndex < 0 || endIndex <= startIndex) return null;
    var nodes = indexData.nodes;
    var startNode = null;
    var startOffset = 0;
    var endNode = null;
    var endOffset = 0;
    for (var i = 0; i < nodes.length; i++) {
      var entry = nodes[i];
      if (!startNode && startIndex >= entry.start && startIndex <= entry.end) {
        startNode = entry.node;
        startOffset = Math.min(startIndex - entry.start, entry.node.nodeValue.length);
      }
      if (!endNode && endIndex >= entry.start && endIndex <= entry.end) {
        endNode = entry.node;
        endOffset = Math.min(endIndex - entry.start, entry.node.nodeValue.length);
      }
      if (startNode && endNode) break;
    }
    if (!startNode || !endNode) return null;
    var range = document.createRange();
    range.setStart(startNode, startOffset);
    range.setEnd(endNode, endOffset);
    return range;
  }

  function wrapTextNode(node, startOffset, endOffset, id) {
    if (!node || node.nodeType !== 3 || !node.parentNode) return;
    var length = node.nodeValue ? node.nodeValue.length : 0;
    if (startOffset < 0) startOffset = 0;
    if (endOffset > length) endOffset = length;
    if (startOffset >= endOffset) return;
    var selected = node;
    if (startOffset > 0) {
      selected = node.splitText(startOffset);
    }
    if (endOffset < selected.nodeValue.length) {
      selected.splitText(endOffset - startOffset);
    }
    var mark = document.createElement('span');
    mark.className = 'articlejs-highlight';
    mark.setAttribute('data-highlight-id', id);
    selected.parentNode.insertBefore(mark, selected);
    mark.appendChild(selected);
  }

  function applyRangeHighlight(range, id) {
    if (!range || range.collapsed || !id) return false;
    var root = range.commonAncestorContainer;
    if (root && root.nodeType === 3) root = root.parentNode;
    if (!root || !document.createTreeWalker || typeof NodeFilter === 'undefined') return false;
    var nodes = [];
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function(node) {
        if (!node || !node.nodeValue) return NodeFilter.FILTER_REJECT;
        if (isSkippableTextNode(node)) return NodeFilter.FILTER_REJECT;
        try {
          if (!range.intersectsNode(node)) return NodeFilter.FILTER_REJECT;
        } catch (_) {
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    while (walker.nextNode()) {
      nodes.push(walker.currentNode);
    }
    for (var i = nodes.length - 1; i >= 0; i--) {
      var node = nodes[i];
      var start = (node === range.startContainer) ? range.startOffset : 0;
      var end = (node === range.endContainer) ? range.endOffset : (node.nodeValue || '').length;
      wrapTextNode(node, start, end, id);
    }
    return true;
  }

  function applyHighlightFromData(highlight, indexData) {
    if (!highlight || !highlight.text || !indexData) return false;
    var id = highlight.id || makeId();
    highlight.id = id;
    var idx = findMatchIndex(indexData.text || '', highlight.text, highlight.prefix || '', highlight.suffix || '');
    if (idx < 0) return false;
    var range = rangeFromIndices(indexData, idx, idx + highlight.text.length);
    if (!range) return false;
    return applyRangeHighlight(range, id);
  }

  function unwrapHighlight(id) {
    if (!id || !document.querySelectorAll) return;
    var nodes = document.querySelectorAll('span.articlejs-highlight[data-highlight-id="' + id + '"]');
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var parent = el.parentNode;
      if (!parent) continue;
      while (el.firstChild) {
        parent.insertBefore(el.firstChild, el);
      }
      parent.removeChild(el);
      if (parent.normalize) parent.normalize();
    }
  }

  function getPrefixText(range, root, maxLen) {
    try {
      var r = range.cloneRange();
      r.setStart(root, 0);
      r.setEnd(range.startContainer, range.startOffset);
      var text = r.toString();
      if (maxLen && text.length > maxLen) text = text.slice(-maxLen);
      return text;
    } catch (_) {
      return '';
    }
  }

  function getSuffixText(range, root, maxLen) {
    try {
      var r = range.cloneRange();
      r.setStart(range.endContainer, range.endOffset);
      r.setEnd(root, root.childNodes.length);
      var text = r.toString();
      if (maxLen && text.length > maxLen) text = text.slice(0, maxLen);
      return text;
    } catch (_) {
      return '';
    }
  }

  function buildHighlightFromRange(range, root) {
    if (!range || range.collapsed || !root) return null;
    if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return null;
    var text = range.toString();
    if (!text || text.length < 2) return null;
    var prefix = getPrefixText(range, root, 32);
    var suffix = getSuffixText(range, root, 32);
    return {
      id: makeId(),
      text: text,
      prefix: prefix,
      suffix: suffix,
      created_at: nowIso()
    };
  }

  var highlightState = { loaded: false, highlights: [] };

  function readHighlights() {
    var url = getHighlightStoreUrl();
    if (!url || !window.fetch) return Promise.resolve(null);
    return fetch(url, { method: 'GET', cache: 'no-store', credentials: 'include' })
      .then(function(res) {
        if (res.status === 404) return null;
        if (!res.ok) throw new Error('load failed');
        return res.text();
      })
      .then(function(text) {
        if (!text) return null;
        try { return JSON.parse(text); } catch (_) { return null; }
      })
      .catch(function() { return null; });
  }

  function writeHighlights(highlights) {
    var url = getHighlightStoreUrl();
    if (!url || !window.fetch) return Promise.resolve(false);
    var payload = {
      version: 1,
      url: baseUrlWithoutHash(),
      title: document.title || '',
      updated_at: nowIso(),
      highlights: highlights || []
    };
    return fetch(url, {
      method: 'PUT',
      cache: 'no-store',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function(res) {
      if (!res.ok) throw new Error('save failed');
      return true;
    });
  }

  function ensureHighlightState() {
    if (highlightState.loaded) return Promise.resolve(highlightState.highlights);
    return readHighlights().then(function(payload) {
      var list = (payload && payload.highlights) ? payload.highlights : [];
      var cleaned = [];
      for (var i = 0; i < list.length; i++) {
        var item = list[i];
        if (!item || !item.text) continue;
        if (!item.id) item.id = makeId();
        cleaned.push(item);
      }
      highlightState.highlights = cleaned;
      highlightState.loaded = true;
      return highlightState.highlights;
    }).catch(function() {
      highlightState.loaded = true;
      highlightState.highlights = [];
      return highlightState.highlights;
    });
  }

  function initHighlights() {
    var root = getRootElement();
    if (!root) return;
    ensureHighlightStyles();
    ensureHighlightState().then(function() {
      if (!highlightState.highlights.length) return;
      var indexData = buildTextIndex(root);
      for (var i = 0; i < highlightState.highlights.length; i++) {
        applyHighlightFromData(highlightState.highlights[i], indexData);
      }
    });
  }

  function isDuplicateHighlight(highlight, list) {
    if (!highlight || !list) return false;
    for (var i = 0; i < list.length; i++) {
      var item = list[i];
      if (!item) continue;
      if (item.text === highlight.text && item.prefix === highlight.prefix && item.suffix === highlight.suffix) {
        return true;
      }
    }
    return false;
  }

  function addHighlightFromRange(range) {
    var root = getRootElement();
    var highlight = buildHighlightFromRange(range, root);
    if (!highlight) return Promise.resolve({ ok: false, reason: 'empty' });
    return ensureHighlightState().then(function() {
      if (isDuplicateHighlight(highlight, highlightState.highlights)) {
        return { ok: false, reason: 'duplicate' };
      }
      var indexData = buildTextIndex(root);
      if (!applyHighlightFromData(highlight, indexData)) {
        return { ok: false, reason: 'apply' };
      }
      highlightState.highlights.push(highlight);
      return writeHighlights(highlightState.highlights)
        .then(function() { return { ok: true }; })
        .catch(function() {
          unwrapHighlight(highlight.id);
          highlightState.highlights = highlightState.highlights.filter(function(item) {
            return item && item.id !== highlight.id;
          });
          return { ok: false, reason: 'save' };
        });
    });
  }

  function removeHighlightById(id) {
    if (!id) return Promise.resolve({ ok: false, reason: 'missing' });
    return ensureHighlightState().then(function() {
      var idx = -1;
      for (var i = 0; i < highlightState.highlights.length; i++) {
        if (highlightState.highlights[i] && highlightState.highlights[i].id === id) {
          idx = i;
          break;
        }
      }
      var existing = idx >= 0 ? highlightState.highlights[idx] : null;
      unwrapHighlight(id);
      if (idx >= 0) {
        highlightState.highlights.splice(idx, 1);
      }
      return writeHighlights(highlightState.highlights)
        .then(function() { return { ok: true }; })
        .catch(function() {
          if (existing) {
            highlightState.highlights.splice(idx, 0, existing);
            var root = getRootElement();
            if (root) {
              var indexData = buildTextIndex(root);
              applyHighlightFromData(existing, indexData);
            }
          }
          return { ok: false, reason: 'save' };
        });
    });
  }

  function highlightSelection() {
    return addHighlightFromRange(captureSelectionRange());
  }

  var api = {
    active: true,
    version: version,
    copyQuote: copyQuote,
    highlightSelection: highlightSelection,
    removeHighlight: removeHighlightById
  };

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
    btn.setAttribute('data-articlejs-ui', '1');
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

    var highlightBtn = document.createElement('button');
    highlightBtn.id = 'articlejs-highlight-btn';
    highlightBtn.type = 'button';
    highlightBtn.textContent = 'Highlight';
    highlightBtn.setAttribute('aria-label', 'Highlight selected text');
    highlightBtn.title = 'Highlight selected text';
    highlightBtn.setAttribute('data-articlejs-ui', '1');
    highlightBtn.style.cssText = [
      'position:fixed',
      'right:12px',
      'bottom:calc(56px + env(safe-area-inset-bottom, 0))',
      'z-index:2147483646',
      'background:#146c43',
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
    document.documentElement.appendChild(highlightBtn);

    // Track selection so iOS tap (which clears selection on focus change) still captures it
    var lastSnapshot = null;
    var lastRange = null;
    var pressedSnapshot = null;
    var pressedRange = null;

    // Toast (reuses button as anchor for screen readers)
    var toast = document.createElement('div');
    toast.id = 'articlejs-toast';
    toast.setAttribute('role', 'status');
    toast.setAttribute('aria-live', 'polite');
    toast.setAttribute('data-articlejs-ui', '1');
    toast.style.cssText = [
      'position:fixed',
      'right:12px',
      'bottom:calc(100px + env(safe-area-inset-bottom, 0))',
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
        var range = captureSelectionRange();
        if (range) {
          lastRange = range;
        }
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
      highlightBtn.style.display = visible ? 'block' : 'none';
      highlightBtn.style.opacity = visible ? '.95' : '.92';
      highlightBtn.style.transform = visible ? 'translateY(0)' : 'translateY(8px)';
    }

    document.addEventListener('selectionchange', updateVisibility, { passive: true });
    // (no resize/visibilitychange): selectionchange is enough

    // iOS: capture selection early to use it on click (no copy yet)
    btn.addEventListener('pointerdown', function(){ pressedSnapshot = captureSelectionSnapshot() || lastSnapshot; }, { passive: true, capture: true });
    // Pointer Events cubre tap/click en Safari/iOS modernos
    highlightBtn.addEventListener('pointerdown', function(){ pressedRange = captureSelectionRange() || lastRange; }, { passive: true, capture: true });

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

    highlightBtn.addEventListener('click', function(){
      highlightBtn.disabled = true;
      var useRange = pressedRange || captureSelectionRange() || lastRange;
      pressedRange = null;
      if (!useRange) {
        showToast('Select some text', false);
        highlightBtn.disabled = false;
        updateVisibility();
        return;
      }
      addHighlightFromRange(useRange)
        .then(function(res) {
          if (res && res.ok) {
            showToast('Highlighted', true);
          } else if (res && res.reason === 'duplicate') {
            showToast('Already highlighted', false);
          } else if (res && res.reason === 'save') {
            showToast('Save failed', false);
          } else if (res && res.reason === 'empty') {
            showToast('Select some text', false);
          } else {
            showToast('Highlight failed', false);
          }
        })
        .catch(function(){ showToast('Highlight failed', false); })
        .finally(function(){ highlightBtn.disabled = false; updateVisibility(); });
    });

    document.addEventListener('click', function(event) {
      if (!(event.altKey || event.shiftKey)) return;
      var target = event.target;
      if (target && target.nodeType === 3) target = target.parentElement;
      if (!target || !target.closest) return;
      var mark = target.closest('span.articlejs-highlight');
      if (!mark) return;
      var id = mark.getAttribute('data-highlight-id');
      if (!id) return;
      event.preventDefault();
      event.stopPropagation();
      removeHighlightById(id)
        .then(function(res) {
          if (res && res.ok) showToast('Highlight removed', true);
          else showToast('Save failed', false);
        })
        .catch(function(){ showToast('Save failed', false); });
    }, false);

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
  function initArticleUi() {
    ensureOverlay();
    initHighlights();
  }
  // Initialize overlay late to ensure DOM is ready
  if (document && document.addEventListener) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initArticleUi, { once: true, passive: true });
    } else {
      initArticleUi();
    }
  }
  // (no extra fallback): the browser handles fragment navigation
})();
