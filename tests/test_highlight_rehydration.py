from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from utils import docflow_server
from utils.highlight_store import load_highlights_for_path, save_highlights_for_path


def _start_server(base_dir: Path) -> tuple[ThreadingHTTPServer, int]:
    app = docflow_server.DocflowApp(base_dir, bump_years=1)
    app.rebuild()
    handler_cls = docflow_server.make_handler(app)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def test_rehydrate_highlights_keeps_offsets_after_node_splits(tmp_path: Path):
    playwright = pytest.importorskip("playwright.sync_api")
    sync_playwright = playwright.sync_playwright

    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    words = [f"word{i:04d}" for i in range(600)]
    full_text = " ".join(words)
    (posts / "doc.html").write_text(f"<html><body><p>{full_text}</p></body></html>", encoding="utf-8")

    rel = "Posts/Posts 2026/doc.html"
    early = " ".join(words[10:18])
    late = " ".join(words[220:230])

    def _entry(hid: str, fragment: str) -> dict[str, str]:
        idx = full_text.index(fragment)
        return {
            "id": hid,
            "text": fragment,
            "prefix": full_text[max(0, idx - 32) : idx],
            "suffix": full_text[idx + len(fragment) : idx + len(fragment) + 32],
        }

    # Regression case: applying the early highlight first used to split text nodes
    # and leave stale offsets for the later one during page rehydration.
    save_highlights_for_path(base, rel, {"highlights": [_entry("h1", early), _entry("h2", late)]})

    server, port = _start_server(base)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{port}/posts/raw/Posts%202026/doc.html", wait_until="domcontentloaded")
            page.wait_for_selector("#dg-overlay")
            page.evaluate("() => window.ArticleJS.getHighlightProgress()")
            rendered = page.evaluate(
                """
                () => {
                  const marks = [...document.querySelectorAll('span.articlejs-highlight[data-highlight-id]')];
                  const byId = {};
                  for (const mark of marks) {
                    const id = mark.getAttribute('data-highlight-id');
                    if (!id) continue;
                    byId[id] = (byId[id] || '') + mark.textContent;
                  }
                  return byId;
                }
                """
            )
            browser.close()

        assert rendered.get("h1") == early
        assert rendered.get("h2") == late
    finally:
        server.shutdown()
        server.server_close()


def test_highlight_selection_same_text_node_mid_tail_span(tmp_path: Path):
    playwright = pytest.importorskip("playwright.sync_api")
    sync_playwright = playwright.sync_playwright

    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    words = [f"token{i:03d}" for i in range(450)]
    full_text = " ".join(words)
    target = " ".join(words[320:330])
    (posts / "doc.html").write_text(f"<html><body><p>{full_text}</p></body></html>", encoding="utf-8")

    rel = "Posts/Posts 2026/doc.html"

    server, port = _start_server(base)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{port}/posts/raw/Posts%202026/doc.html", wait_until="domcontentloaded")
            page.wait_for_selector("#dg-overlay")
            page.evaluate("() => window.ArticleJS.getHighlightProgress()")
            result = page.evaluate(
                """
                async (needle) => {
                  const root = document.body;
                  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
                  let targetNode = null;
                  let start = -1;
                  while (walker.nextNode()) {
                    const node = walker.currentNode;
                    const idx = (node.nodeValue || '').indexOf(needle);
                    if (idx >= 0) {
                      targetNode = node;
                      start = idx;
                      break;
                    }
                  }
                  if (!targetNode || start < 0) {
                    return { ok: false, reason: 'needle-not-found' };
                  }
                  const range = document.createRange();
                  range.setStart(targetNode, start);
                  range.setEnd(targetNode, start + needle.length);
                  const selection = window.getSelection();
                  selection.removeAllRanges();
                  selection.addRange(range);
                  const saveResult = await window.ArticleJS.highlightSelection();
                  const marks = [...document.querySelectorAll('span.articlejs-highlight[data-highlight-id]')];
                  const byId = {};
                  for (const mark of marks) {
                    const id = mark.getAttribute('data-highlight-id');
                    if (!id) continue;
                    byId[id] = (byId[id] || '') + (mark.textContent || '');
                  }
                  return { saveResult, byId };
                }
                """,
                target,
            )
            browser.close()

        assert result["saveResult"]["ok"] is True
        assert target in result["byId"].values()

        payload = load_highlights_for_path(base, rel)
        texts = [item.get("text") for item in payload.get("highlights", []) if isinstance(item, dict)]
        assert target in texts
    finally:
        server.shutdown()
        server.server_close()


def test_highlight_selection_across_list_items_keeps_separator_text(tmp_path: Path):
    playwright = pytest.importorskip("playwright.sync_api")
    sync_playwright = playwright.sync_playwright

    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    expected = "ARC-AGI-1: 98%, $0.52/task\nARC-AGI-2: 77%, $0.96/task"
    html = (
        "<html><body><ul>\n"
        "<li>ARC-AGI-1: 98%, $0.52/task</li>\n"
        "<li>ARC-AGI-2: 77%, $0.96/task</li>\n"
        "</ul>\n"
        "<p>Tail context to keep suffix anchors inside content.</p>"
        "</body></html>"
    )
    (posts / "doc.html").write_text(html, encoding="utf-8")

    rel = "Posts/Posts 2026/doc.html"

    server, port = _start_server(base)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{port}/posts/raw/Posts%202026/doc.html", wait_until="domcontentloaded")
            page.wait_for_selector("#dg-overlay")
            page.evaluate("() => window.ArticleJS.getHighlightProgress()")
            result = page.evaluate(
                """
                async () => {
                  const first = document.querySelector('li');
                  const second = first && first.nextElementSibling;
                  if (!first || !second || !first.firstChild || !second.firstChild) {
                    return { ok: false, reason: 'list-nodes-missing' };
                  }
                  const range = document.createRange();
                  range.setStart(first.firstChild, 0);
                  range.setEnd(second.firstChild, (second.firstChild.nodeValue || '').length);
                  const selection = window.getSelection();
                  selection.removeAllRanges();
                  selection.addRange(range);
                  return window.ArticleJS.highlightSelection();
                }
                """
            )
            browser.close()

        assert result["ok"] is True, result

        payload = load_highlights_for_path(base, rel)
        texts = [item.get("text") for item in payload.get("highlights", []) if isinstance(item, dict)]
        expected_norm = " ".join(expected.split())
        assert any(" ".join(str(text or "").split()) == expected_norm for text in texts)
    finally:
        server.shutdown()
        server.server_close()
