(function () {
  var script = document.currentScript;
  var relPath = script && script.dataset ? script.dataset.path : '';
  if (!relPath) {
    try { relPath = decodeURIComponent(String(location.pathname || '').replace(/^\//, '')); }
    catch (_) { relPath = String(location.pathname || '').replace(/^\//, ''); }
  }

  function ensureHighlightStyles() {
    if (!document) return;
    var id = 'docflow-highlight-style';
    if (document.getElementById(id)) return;
    var style = document.createElement('style');
    style.id = id;
    style.textContent = [
      '.docflow-highlight {',
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
      if (el.id === 'dg-overlay' || el.id === 'dg-toast') return true;
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
      acceptNode: function (node) {
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
    mark.className = 'docflow-highlight';
    if (id) mark.setAttribute('data-highlight-id', id);
    selected.parentNode.insertBefore(mark, selected);
    mark.appendChild(selected);
  }

  function applyRangeHighlight(range, id) {
    if (!range || range.collapsed) return false;
    var root = range.commonAncestorContainer;
    if (root && root.nodeType === 3) root = root.parentNode;
    if (!root || !document.createTreeWalker || typeof NodeFilter === 'undefined') return false;
    var nodes = [];
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
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

  function buildRanges(highlights, indexData) {
    var ranges = [];
    for (var i = 0; i < highlights.length; i++) {
      var highlight = highlights[i];
      if (!highlight || !highlight.text) continue;
      var idx = findMatchIndex(indexData.text || '', highlight.text, highlight.prefix || '', highlight.suffix || '');
      if (idx < 0) continue;
      ranges.push({
        start: idx,
        end: idx + highlight.text.length,
        id: highlight.id || ''
      });
    }
    return ranges;
  }

  function consolidateRanges(ranges) {
    if (!ranges.length) return [];
    ranges.sort(function (a, b) {
      if (a.start !== b.start) return a.start - b.start;
      return b.end - a.end;
    });
    var merged = [];
    var current = null;
    for (var i = 0; i < ranges.length; i++) {
      var range = ranges[i];
      if (!current) {
        current = { start: range.start, end: range.end, ids: range.id ? [range.id] : [] };
        continue;
      }
      if (range.start < current.end) {
        current.end = Math.max(current.end, range.end);
        if (range.id) current.ids.push(range.id);
        continue;
      }
      merged.push(current);
      current = { start: range.start, end: range.end, ids: range.id ? [range.id] : [] };
    }
    if (current) merged.push(current);
    return merged;
  }

  function applyHighlights(highlights) {
    var root = document && document.body ? document.body : null;
    if (!root) return;
    ensureHighlightStyles();
    var indexData = buildTextIndex(root);
    if (!indexData || !indexData.text) return;
    var ranges = buildRanges(highlights || [], indexData);
    var consolidated = consolidateRanges(ranges);
    for (var i = consolidated.length - 1; i >= 0; i--) {
      var item = consolidated[i];
      var range = rangeFromIndices(indexData, item.start, item.end);
      if (!range) continue;
      var id = item.ids && item.ids.length ? item.ids.join(',') : 'h_' + i;
      applyRangeHighlight(range, id);
    }
  }

  function loadHighlights() {
    if (!relPath) return Promise.resolve(null);
    var url = '/__highlights?path=' + encodeURIComponent(relPath);
    return fetch(url, { credentials: 'same-origin' })
      .then(function (res) { return res.ok ? res.json() : null; })
      .catch(function () { return null; });
  }

  function init() {
    loadHighlights().then(function (payload) {
      if (!payload || !payload.highlights || !payload.highlights.length) return;
      applyHighlights(payload.highlights);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
