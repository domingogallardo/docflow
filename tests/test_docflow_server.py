from __future__ import annotations

import http.client
import json
import threading
import time
from pathlib import Path
from http.server import ThreadingHTTPServer

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
        status, payload = _post_json(port, "/api/bump", {"path": "Posts/Posts 2026/doc.html"})
        assert status == 200
        assert payload["ok"] is True
        assert html.stat().st_mtime > time.time()
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
    finally:
        server.shutdown()
        server.server_close()
