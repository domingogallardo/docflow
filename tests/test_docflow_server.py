from __future__ import annotations

import http.client
import json
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from utils import docflow_server
from utils.site_state import get_bumped_entry, is_done, is_working


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


def _get_with_headers(port: int, path: str) -> tuple[int, str, dict[str, str]]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path)
        res = conn.getresponse()
        body = res.read().decode("utf-8", errors="ignore")
        headers = {k.lower(): v for k, v in res.getheaders()}
        return res.status, body, headers
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


def test_api_to_done_moves_to_done_listing(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    html = posts / "doc.html"
    html.write_text("<html><body>Doc</body></html>", encoding="utf-8")

    server, port = _start_server(base)
    try:
        status, payload = _post_json(port, "/api/to-done", {"path": "Posts/Posts 2026/doc.html"})
        assert status == 200
        assert payload["ok"] is True
        assert is_done(base, "Posts/Posts 2026/doc.html") is True
        assert is_working(base, "Posts/Posts 2026/doc.html") is False

        working_status, working_html = _get(port, "/working/")
        assert working_status == 200
        assert "doc.html" not in working_html

        done_status, done_html = _get(port, "/done/")
        assert done_status == 200
        assert "doc.html" in done_html
    finally:
        server.shutdown()
        server.server_close()


def test_api_stage_transitions_roundtrip(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    rel = "Posts/Posts 2026/doc.html"
    (posts / "doc.html").write_text("<html><body>Doc</body></html>", encoding="utf-8")

    server, port = _start_server(base)
    try:
        status, payload = _post_json(port, "/api/to-working", {"path": rel})
        assert status == 200
        assert payload["ok"] is True
        assert payload["data"]["stage"] == "working"
        assert is_working(base, rel) is True
        assert is_done(base, rel) is False

        status, payload = _post_json(port, "/api/to-done", {"path": rel})
        assert status == 200
        assert payload["ok"] is True
        assert payload["data"]["stage"] == "done"
        assert is_working(base, rel) is False
        assert is_done(base, rel) is True

        status, payload = _post_json(port, "/api/reopen", {"path": rel})
        assert status == 200
        assert payload["ok"] is True
        assert payload["data"]["stage"] == "working"
        assert payload["data"]["transition"] == "reopen"
        assert is_working(base, rel) is True
        assert is_done(base, rel) is False

        status, payload = _post_json(port, "/api/to-browse", {"path": rel})
        assert status == 200
        assert payload["ok"] is True
        assert payload["data"]["stage"] == "browse"
        assert is_working(base, rel) is False
        assert is_done(base, rel) is False
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


def test_api_bump_is_restricted_to_browse_stage(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    rel = "Posts/Posts 2026/doc.html"
    (posts / "doc.html").write_text("<html><body>Doc</body></html>", encoding="utf-8")

    server, port = _start_server(base)
    try:
        status, payload = _post_json(port, "/api/to-working", {"path": rel})
        assert status == 200
        assert payload["ok"] is True

        status, payload = _post_json(port, "/api/bump", {"path": rel})
        assert status == 409
        assert payload["ok"] is False
        assert "only allowed in browse stage" in payload["error"]

        status, payload = _post_json(port, "/api/to-done", {"path": rel})
        assert status == 200
        assert payload["ok"] is True

        status, payload = _post_json(port, "/api/bump", {"path": rel})
        assert status == 409
        assert payload["ok"] is False
        assert "only allowed in browse stage" in payload["error"]

        status, payload = _post_json(port, "/api/to-browse", {"path": rel})
        assert status == 200
        assert payload["ok"] is True

        status, payload = _post_json(port, "/api/bump", {"path": rel})
        assert status == 200
        assert payload["ok"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_api_delete_removes_local_markdown_and_state_entries(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    html = posts / "doc.html"
    html.write_text("<html><body>Doc</body></html>", encoding="utf-8")
    md = posts / "doc.md"
    md.write_text("# Doc\n", encoding="utf-8")

    rel_path = "Posts/Posts 2026/doc.html"

    server, port = _start_server(base)
    try:
        status, payload = _post_json(port, "/api/bump", {"path": rel_path})
        assert status == 200
        assert payload["ok"] is True

        status, payload = _post_json(port, "/api/to-working", {"path": rel_path})
        assert status == 200
        assert payload["ok"] is True

        status, payload = _post_json(port, "/api/delete", {"path": rel_path})
        assert status == 200
        assert payload["ok"] is True
        assert payload["data"]["deleted_md"] is True
        assert payload["data"]["redirect"] == "/browse/posts/Posts%202026/"

        assert not html.exists()
        assert not md.exists()
        assert is_done(base, rel_path) is False
        assert is_working(base, rel_path) is False
        assert get_bumped_entry(base, rel_path) is None

        working_status, working_html = _get(port, "/working/")
        assert working_status == 200
        assert "doc.html" not in working_html

        done_status, done_html = _get(port, "/done/")
        assert done_status == 200
        assert "doc.html" not in done_html
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
        assert '/working/article.js' in body
        assert 'name="viewport"' in body
        assert "data-stage" in body
        assert 'data-bumped="0"' in body
        assert 'data-browse-url="/browse/posts/Posts%202026/"' in body
        assert "window.addEventListener('pageshow'" in body
        assert "back_forward" in body
        assert "Index: Browse" in body
        assert "to-working" in body
        assert "Rebuild" in body
        assert "Delete" in body
        assert "dg-hl-nav" in body
        assert "articlejs:highlight-progress" in body
        assert "Previous highlight" in body
        assert "Next highlight" in body
        assert "textContent = '^'" in body
        assert "textContent = '˅'" in body
    finally:
        server.shutdown()
        server.server_close()


def test_raw_route_overlay_marks_bumped_state(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    rel = "Posts/Posts 2026/doc.html"
    (posts / "doc.html").write_text("<html><body>Raw Doc</body></html>", encoding="utf-8")

    server, port = _start_server(base)
    try:
        status, payload = _post_json(port, "/api/to-browse", {"path": rel})
        assert status == 200
        assert payload["ok"] is True

        status, payload = _post_json(port, "/api/bump", {"path": rel})
        assert status == 200
        assert payload["ok"] is True

        status, body = _get(port, "/posts/raw/Posts%202026/doc.html")
        assert status == 200
        assert 'data-bumped="1"' in body
    finally:
        server.shutdown()
        server.server_close()


def test_read_route_is_removed(tmp_path: Path):
    base = tmp_path / "base"
    (base / "Posts" / "Posts 2026").mkdir(parents=True)

    server, port = _start_server(base)
    try:
        status, _ = _get(port, "/read/")
        assert status == 404
        status, _ = _get(port, "/read")
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()


def test_api_rebuild_file_recreates_html_from_markdown(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    html = posts / "doc.html"
    html.write_text("<html><body>Old HTML</body></html>", encoding="utf-8")
    md = posts / "doc.md"
    md.write_text("# Fresh Title\n\nUpdated body.\n", encoding="utf-8")

    rel_path = "Posts/Posts 2026/doc.html"

    server, port = _start_server(base)
    try:
        status, payload = _post_json(port, "/api/rebuild-file", {"path": rel_path})
        assert status == 200
        assert payload["ok"] is True
        assert payload["data"]["rebuilt"] is True
        assert payload["data"]["path"] == rel_path
        assert payload["data"]["markdown"] == "Posts/Posts 2026/doc.md"

        rebuilt_html = html.read_text(encoding="utf-8")
        assert "Fresh Title" in rebuilt_html
        assert "Updated body." in rebuilt_html
    finally:
        server.shutdown()
        server.server_close()


def test_api_rebuild_file_requires_associated_markdown(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    html = posts / "doc.html"
    html.write_text("<html><body>Only HTML</body></html>", encoding="utf-8")

    server, port = _start_server(base)
    try:
        status, payload = _post_json(port, "/api/rebuild-file", {"path": "Posts/Posts 2026/doc.html"})
        assert status == 404
        assert payload["ok"] is False
        assert "Associated Markdown file not found" in payload["error"]
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


def test_raw_directory_route_redirects_to_browse(tmp_path: Path):
    base = tmp_path / "base"
    tweets = base / "Tweets" / "Tweets 2026"
    tweets.mkdir(parents=True)
    (tweets / "doc.html").write_text("<html><body>Tweet Doc</body></html>", encoding="utf-8")

    server, port = _start_server(base)
    try:
        status, _body, headers = _get_with_headers(port, "/tweets/raw/Tweets%202026/")
        assert status == 302
        assert headers.get("location") == "/browse/tweets/Tweets%202026/"
    finally:
        server.shutdown()
        server.server_close()


def test_to_done_does_not_rewrite_unrelated_browse_branch(tmp_path: Path):
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
        status, payload = _post_json(port, "/api/to-done", {"path": "Posts/Posts 2026/new.html"})
        assert status == 200
        assert payload["ok"] is True

        assert abs(untouched_page.stat().st_mtime - untouched_mtime_before) < 0.001
        status, html = _get(port, "/browse/posts/Posts%202026/")
        assert status == 200
        assert "new.html" not in html
        assert "🟢" not in html
    finally:
        server.shutdown()
        server.server_close()


def test_api_to_working_rebuilds_only_browse_and_working(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    rel = "Posts/Posts 2026/doc.html"
    (posts / "doc.html").write_text("<html><body>Doc</body></html>", encoding="utf-8")

    app = docflow_server.DocflowApp(base)
    calls: list[str] = []

    def _browse(*_args, **_kwargs):
        calls.append("browse")
        return {"mode": "partial"}

    def _working(*_args, **_kwargs):
        calls.append("working")

    def _done(*_args, **_kwargs):
        calls.append("done")

    monkeypatch.setattr(docflow_server.build_browse_index, "rebuild_browse_for_path", _browse)
    monkeypatch.setattr(docflow_server.build_working_index, "write_site_working_index", _working)
    monkeypatch.setattr(docflow_server.build_done_index, "write_site_done_index", _done)

    result = app.api_to_working(rel)
    assert result["stage"] == "working"
    assert result["changed"] is True
    assert calls == ["browse", "working"]


def test_api_to_done_from_working_rebuilds_only_working_and_done(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    rel = "Posts/Posts 2026/doc.html"
    (posts / "doc.html").write_text("<html><body>Doc</body></html>", encoding="utf-8")
    docflow_server.set_working_path(base, rel)

    app = docflow_server.DocflowApp(base)
    calls: list[str] = []

    def _browse(*_args, **_kwargs):
        calls.append("browse")
        return {"mode": "partial"}

    def _working(*_args, **_kwargs):
        calls.append("working")

    def _done(*_args, **_kwargs):
        calls.append("done")

    monkeypatch.setattr(docflow_server.build_browse_index, "rebuild_browse_for_path", _browse)
    monkeypatch.setattr(docflow_server.build_working_index, "write_site_working_index", _working)
    monkeypatch.setattr(docflow_server.build_done_index, "write_site_done_index", _done)

    result = app.api_to_done(rel)
    assert result["stage"] == "done"
    assert result["changed"] is True
    assert calls == ["working", "done"]
