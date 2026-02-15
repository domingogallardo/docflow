from __future__ import annotations

import http.client
import json
import threading
import time
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import quote

from utils import docflow_server
from utils.site_state import get_bumped_entry, is_published


def _start_server(base_dir: Path) -> tuple[ThreadingHTTPServer, int]:
    app = docflow_server.DocflowApp(base_dir, bump_years=1)
    app.rebuild()
    handler_cls = docflow_server.make_handler(app)

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def _post_json(port: int, path: str, payload: dict[str, object]) -> tuple[int, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        body = json.dumps(payload)
        conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
        res = conn.getresponse()
        data = json.loads(res.read().decode("utf-8"))
        return res.status, data
    finally:
        conn.close()


def _get(port: int, path: str) -> tuple[int, str]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path)
        res = conn.getresponse()
        return res.status, res.read().decode("utf-8", errors="ignore")
    finally:
        conn.close()


def _put_json(port: int, path: str, payload: dict[str, object]) -> tuple[int, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        body = json.dumps(payload)
        conn.request("PUT", path, body=body, headers={"Content-Type": "application/json"})
        res = conn.getresponse()
        data = json.loads(res.read().decode("utf-8"))
        return res.status, data
    finally:
        conn.close()


def test_api_publish_and_read_listing(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    html = posts / "doc.html"
    html.write_text("<html><body>Doc</body></html>", encoding="utf-8")

    server, port = _start_server(base)
    try:
        status, payload = _post_json(port, "/api/publish", {"path": "Posts/Posts 2026/doc.html"})
        assert status == 200
        assert payload["ok"] is True
        assert is_published(base, "Posts/Posts 2026/doc.html") is True

        read_status, read_html = _get(port, "/read/")
        assert read_status == 200
        assert "doc.html" in read_html
    finally:
        server.shutdown()
        server.server_close()


def test_api_bump_unbump_roundtrip(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    html = posts / "doc.html"
    html.write_text("<html><body>Doc</body></html>", encoding="utf-8")

    original_mtime = html.stat().st_mtime

    server, port = _start_server(base)
    try:
        mtime_before_bump = html.stat().st_mtime
        status, payload = _post_json(port, "/api/bump", {"path": "Posts/Posts 2026/doc.html"})
        assert status == 200
        assert payload["ok"] is True
        assert abs(html.stat().st_mtime - mtime_before_bump) < 0.001
        assert get_bumped_entry(base, "Posts/Posts 2026/doc.html") is not None

        status, payload = _post_json(port, "/api/unbump", {"path": "Posts/Posts 2026/doc.html"})
        assert status == 200
        assert payload["ok"] is True
        assert abs(html.stat().st_mtime - original_mtime) < 0.001
        assert get_bumped_entry(base, "Posts/Posts 2026/doc.html") is None
    finally:
        server.shutdown()
        server.server_close()


def test_raw_route_serves_library_file(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    html = posts / "doc.html"
    html.write_text("<html><body>Raw Doc</body></html>", encoding="utf-8")

    server, port = _start_server(base)
    try:
        status, body = _get(port, "/posts/raw/Posts%202026/doc.html")
        assert status == 200
        assert "Raw Doc" in body
        assert "dg-overlay" in body
        assert '/read/article.js' in body
        assert "/api/publish" in body or "data-published" in body
    finally:
        server.shutdown()
        server.server_close()


def test_api_highlights_roundtrip_and_rebuild_markers(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    html = posts / "doc.html"
    html.write_text("<html><body>Raw Doc</body></html>", encoding="utf-8")

    rel_path = "Posts/Posts 2026/doc.html"
    encoded = quote(rel_path, safe="")

    server, port = _start_server(base)
    try:
        status, body = _get(port, f"/api/highlights?path={encoded}")
        assert status == 200
        payload = json.loads(body)
        assert payload["path"] == rel_path
        assert payload["highlights"] == []

        status, payload = _put_json(
            port,
            f"/api/highlights?path={encoded}",
            {"highlights": [{"id": "h1", "text": "Raw Doc"}]},
        )
        assert status == 200
        assert payload["path"] == rel_path
        assert payload["highlights"][0]["text"] == "Raw Doc"

        status, body = _get(port, f"/api/highlights?path={encoded}")
        assert status == 200
        payload = json.loads(body)
        assert payload["highlights"][0]["id"] == "h1"

        browse_status, browse_html = _get(port, "/browse/posts/Posts%202026/")
        assert browse_status == 200
        assert "🟡" in browse_html
    finally:
        server.shutdown()
        server.server_close()


def test_raw_pdf_route_has_no_overlay_injection(tmp_path: Path):
    base = tmp_path / "base"
    pdfs = base / "Pdfs" / "Pdfs 2026"
    pdfs.mkdir(parents=True)
    pdf = pdfs / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\\n%test\\n")

    server, port = _start_server(base)
    try:
        status, body = _get(port, "/pdfs/raw/Pdfs%202026/doc.pdf")
        assert status == 200
        assert "dg-overlay" not in body
    finally:
        server.shutdown()
        server.server_close()


def test_publish_does_not_rewrite_unrelated_browse_branch(tmp_path: Path):
    base = tmp_path / "base"
    posts_2025 = base / "Posts" / "Posts 2025"
    posts_2026 = base / "Posts" / "Posts 2026"
    posts_2025.mkdir(parents=True)
    posts_2026.mkdir(parents=True)

    (posts_2025 / "old.html").write_text("<html><body>Old</body></html>", encoding="utf-8")
    (posts_2026 / "new.html").write_text("<html><body>New</body></html>", encoding="utf-8")

    server, port = _start_server(base)
    try:
        untouched_page = base / "_site" / "browse" / "posts" / "Posts 2025" / "index.html"
        untouched_mtime_before = untouched_page.stat().st_mtime

        time.sleep(1.1)
        status, payload = _post_json(port, "/api/publish", {"path": "Posts/Posts 2026/new.html"})
        assert status == 200
        assert payload["ok"] is True

        assert abs(untouched_page.stat().st_mtime - untouched_mtime_before) < 0.001
        status, html = _get(port, "/browse/posts/Posts%202026/")
        assert status == 200
        assert "🟢" in html
    finally:
        server.shutdown()
        server.server_close()
