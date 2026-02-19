from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from utils import docflow_server
from utils.highlight_store import save_highlights_for_path


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
