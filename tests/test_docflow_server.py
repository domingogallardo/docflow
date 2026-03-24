from __future__ import annotations

import http.client
import json
import shutil
import subprocess
from datetime import datetime
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

import pytest

from utils import docflow_server
from utils.reading_position_store import reading_position_state_path, save_reading_position_for_path
from utils.site_state import (
    is_done,
    is_reading,
    is_working,
    load_done_state,
    load_reading_state,
    load_working_state,
)


def _start_server(base_dir: Path) -> tuple[ThreadingHTTPServer, int]:
    app = docflow_server.DocflowApp(base_dir)
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


def _get_bytes_with_headers(port: int, path: str) -> tuple[int, bytes, dict[str, str]]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path)
        res = conn.getresponse()
        body = res.read()
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
        status, payload = _post_json(port, "/api/to-reading", {"path": rel})
        assert status == 200
        assert payload["ok"] is True
        assert payload["data"]["stage"] == "reading"
        assert is_reading(base, rel) is True
        assert is_working(base, rel) is False
        assert is_done(base, rel) is False

        status, payload = _post_json(port, "/api/to-working", {"path": rel})
        assert status == 200
        assert payload["ok"] is True
        assert payload["data"]["stage"] == "working"
        assert is_reading(base, rel) is False
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
        assert payload["data"]["stage"] == "reading"
        assert payload["data"]["transition"] == "reopen"
        assert is_reading(base, rel) is True
        assert is_working(base, rel) is False
        assert is_done(base, rel) is False

        status, payload = _post_json(port, "/api/to-browse", {"path": rel})
        assert status == 200
        assert payload["ok"] is True
        assert payload["data"]["stage"] == "browse"
        assert is_reading(base, rel) is False
        assert is_working(base, rel) is False
        assert is_done(base, rel) is False
    finally:
        server.shutdown()
        server.server_close()


def test_api_to_done_keeps_working_start_time_in_done_state(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    rel = "Posts/Posts 2026/doc.html"
    (posts / "doc.html").write_text("<html><body>Doc</body></html>", encoding="utf-8")

    server, port = _start_server(base)
    try:
        status, payload = _post_json(port, "/api/to-reading", {"path": rel})
        assert status == 200
        assert payload["ok"] is True

        status, payload = _post_json(port, "/api/to-working", {"path": rel})
        assert status == 200
        assert payload["ok"] is True

        working_state = load_working_state(base)
        working_started_at = working_state["items"][rel]["working_at"]
        assert isinstance(working_started_at, str)

        status, payload = _post_json(port, "/api/to-done", {"path": rel})
        assert status == 200
        assert payload["ok"] is True

        done_state = load_done_state(base)
        done_entry = done_state["items"][rel]
        assert done_entry["working_started_at"] == working_started_at
        assert is_working(base, rel) is False
    finally:
        server.shutdown()
        server.server_close()


def test_api_to_done_keeps_reading_start_time_in_done_state(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    rel = "Posts/Posts 2026/doc.html"
    (posts / "doc.html").write_text("<html><body>Doc</body></html>", encoding="utf-8")

    server, port = _start_server(base)
    try:
        status, payload = _post_json(port, "/api/to-reading", {"path": rel})
        assert status == 200
        assert payload["ok"] is True

        reading_state = load_reading_state(base)
        reading_started_at = reading_state["items"][rel]["reading_at"]
        assert isinstance(reading_started_at, str)

        status, payload = _post_json(port, "/api/to-done", {"path": rel})
        assert status == 200
        assert payload["ok"] is True

        done_state = load_done_state(base)
        done_entry = done_state["items"][rel]
        assert done_entry["reading_started_at"] == reading_started_at
        assert is_reading(base, rel) is False
    finally:
        server.shutdown()
        server.server_close()


def test_api_to_done_appends_entry_to_done_links_file(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    rel = "Posts/Posts 2026/doc.html"
    (posts / "doc.html").write_text("<html><body>Doc</body></html>", encoding="utf-8")

    done_links_file = tmp_path / "obsidian" / "Leidos.md"
    monkeypatch.setenv("DONE_LINKS_FILE", str(done_links_file))
    monkeypatch.setenv("DONE_LINKS_BASE_URL", "http://localhost:8080")

    app = docflow_server.DocflowApp(base)
    result = app.api_to_done(rel)
    assert result["stage"] == "done"
    assert result["changed"] is True

    content = done_links_file.read_text(encoding="utf-8")
    today = datetime.now().strftime("%d/%m/%Y")
    expected = f"- **{today}**: [doc.html](http://localhost:8080/posts/raw/Posts%202026/doc.html)"
    assert expected in content


def test_api_to_done_links_file_skips_duplicate_url(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    rel = "Posts/Posts 2026/doc.html"
    (posts / "doc.html").write_text("<html><body>Doc</body></html>", encoding="utf-8")

    done_links_file = tmp_path / "obsidian" / "Leidos.md"
    done_links_file.parent.mkdir(parents=True, exist_ok=True)
    existing = (
        '- **01/03/2026**: [doc.html]'
        '(http://localhost:8080/posts/raw/Posts%202026/doc.html "doc.html")\n'
    )
    done_links_file.write_text(existing, encoding="utf-8")

    monkeypatch.setenv("DONE_LINKS_FILE", str(done_links_file))
    monkeypatch.setenv("DONE_LINKS_BASE_URL", "http://localhost:8080")

    app = docflow_server.DocflowApp(base)
    result = app.api_to_done(rel)
    assert result["stage"] == "done"
    assert result["changed"] is True

    content = done_links_file.read_text(encoding="utf-8")
    assert content.count("http://localhost:8080/posts/raw/Posts%202026/doc.html") == 1


def test_api_to_done_prepends_entry_as_first_bullet(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    rel = "Posts/Posts 2026/new.html"
    (posts / "new.html").write_text("<html><body>Doc</body></html>", encoding="utf-8")

    done_links_file = tmp_path / "obsidian" / "Leidos.md"
    done_links_file.parent.mkdir(parents=True, exist_ok=True)
    done_links_file.write_text(
        "- **01/03/2026**: [old-1.html](http://localhost:8080/posts/raw/Posts%202026/old-1.html)\n"
        "- **28/02/2026**: [old-2.html](http://localhost:8080/posts/raw/Posts%202026/old-2.html)\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DONE_LINKS_FILE", str(done_links_file))
    monkeypatch.setenv("DONE_LINKS_BASE_URL", "http://localhost:8080")

    app = docflow_server.DocflowApp(base)
    result = app.api_to_done(rel)
    assert result["stage"] == "done"
    assert result["changed"] is True

    bullets = [line for line in done_links_file.read_text(encoding="utf-8").splitlines() if line.startswith("- ")]
    assert bullets
    assert "new.html" in bullets[0]


def test_api_to_reading_roundtrip(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    html = posts / "doc.html"
    html.write_text("<html><body>Doc</body></html>", encoding="utf-8")

    server, port = _start_server(base)
    try:
        status, payload = _post_json(port, "/api/to-reading", {"path": "Posts/Posts 2026/doc.html"})
        assert status == 200
        assert payload["ok"] is True
        assert payload["data"]["stage"] == "reading"
        assert is_reading(base, "Posts/Posts 2026/doc.html") is True

        status, payload = _post_json(port, "/api/to-browse", {"path": "Posts/Posts 2026/doc.html"})
        assert status == 200
        assert payload["ok"] is True
        assert payload["data"]["stage"] == "browse"
        assert is_reading(base, "Posts/Posts 2026/doc.html") is False
    finally:
        server.shutdown()
        server.server_close()


def test_api_to_working_is_restricted_to_reading_stage(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    rel = "Posts/Posts 2026/doc.html"
    (posts / "doc.html").write_text("<html><body>Doc</body></html>", encoding="utf-8")

    server, port = _start_server(base)
    try:
        status, payload = _post_json(port, "/api/to-working", {"path": rel})
        assert status == 409
        assert payload["ok"] is False
        assert "only allowed from reading stage" in payload["error"]

        status, payload = _post_json(port, "/api/to-reading", {"path": rel})
        assert status == 200
        assert payload["ok"] is True

        status, payload = _post_json(port, "/api/to-working", {"path": rel})
        assert status == 200
        assert payload["ok"] is True

        status, payload = _post_json(port, "/api/to-done", {"path": rel})
        assert status == 200
        assert payload["ok"] is True

        status, payload = _post_json(port, "/api/to-working", {"path": rel})
        assert status == 409
        assert payload["ok"] is False
        assert "only allowed from reading stage" in payload["error"]

        status, payload = _post_json(port, "/api/reopen", {"path": rel})
        assert status == 200
        assert payload["ok"] is True

        status, payload = _post_json(port, "/api/to-working", {"path": rel})
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
    save_reading_position_for_path(
        base,
        rel_path,
        {"updated_at": "2026-03-17T10:00:00Z", "scroll_y": 320, "max_scroll": 1000, "progress": 0.32},
    )
    reading_position_path = reading_position_state_path(base, rel_path)
    assert reading_position_path.exists()

    server, port = _start_server(base)
    try:
        status, payload = _post_json(port, "/api/to-reading", {"path": rel_path})
        assert status == 200
        assert payload["ok"] is True

        status, payload = _post_json(port, "/api/to-working", {"path": rel_path})
        assert status == 200
        assert payload["ok"] is True

        status, payload = _post_json(port, "/api/delete", {"path": rel_path})
        assert status == 200
        assert payload["ok"] is True
        assert payload["data"]["deleted_md"] is True
        assert payload["data"]["removed_reading_position"] is True
        assert payload["data"]["redirect"] == "/browse/posts/Posts%202026/"

        assert not html.exists()
        assert not md.exists()
        assert not reading_position_path.exists()
        assert is_done(base, rel_path) is False
        assert is_reading(base, rel_path) is False
        assert is_working(base, rel_path) is False

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
    (posts / "doc.md").write_text("# Raw Doc\n", encoding="utf-8")

    server, port = _start_server(base)
    try:
        status, body = _get(port, "/posts/raw/Posts%202026/doc.html")
        assert status == 200
        assert "Raw Doc" in body
        assert "dg-overlay" in body
        assert '/working/article.js' in body
        assert 'name="viewport"' in body
        assert "data-stage" in body
        assert 'data-browse-url="/browse/posts/Posts%202026/"' in body
        assert "window.addEventListener('pageshow'" in body
        assert "back_forward" in body
        assert "Inside Browse" in body
        assert "PDF" in body
        assert "MD" in body
        assert "/api/export-pdf?path=" in body
        assert "/api/export-markdown?path=" in body
        assert "to-reading" in body
        assert "to-done" in body
        assert "Rebuild" in body
        assert "Delete" in body
        assert "dg-hl-nav" in body
        assert "dg-row-status" in body
        assert "dg-row-actions" in body
        assert "dg-row-highlights" in body
        assert "Jump to highlight:" in body
        assert "articlejs:highlight-progress" in body
        assert "Previous highlight" in body
        assert "Next highlight" in body
        assert "makeChevronIcon('up')" in body
        assert "makeChevronIcon('down')" in body
        assert "http://www.w3.org/2000/svg" in body
        assert "white-space: pre-wrap" in body
        assert "overflow-wrap: anywhere" in body
    finally:
        server.shutdown()
        server.server_close()


def test_raw_route_overlay_marks_reading_stage(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    rel = "Posts/Posts 2026/doc.html"
    (posts / "doc.html").write_text("<html><body>Raw Doc</body></html>", encoding="utf-8")

    server, port = _start_server(base)
    try:
        status, payload = _post_json(port, "/api/to-reading", {"path": rel})
        assert status == 200
        assert payload["ok"] is True

        status, body = _get(port, "/posts/raw/Posts%202026/doc.html")
        assert status == 200
        assert 'data-stage="reading"' in body
        assert "/api/export-pdf?path=" in body
        assert "to-working" in body
        assert "to-done" in body
    finally:
        server.shutdown()
        server.server_close()


def test_api_export_pdf_serves_inline_pdf_bytes(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    (posts / "doc.html").write_text("<html><body>Raw Doc</body></html>", encoding="utf-8")

    def _fake_export(_self: docflow_server.DocflowApp, _rel_path: str) -> tuple[bytes, str]:
        return b"%PDF-1.4\n%mock\n", "doc.pdf"

    monkeypatch.setattr(docflow_server.DocflowApp, "api_export_pdf", _fake_export)

    server, port = _start_server(base)
    try:
        status, body, headers = _get_bytes_with_headers(
            port,
            "/api/export-pdf?path=Posts%2FPosts%202026%2Fdoc.html",
        )
        assert status == 200
        assert headers.get("content-type") == "application/pdf"
        content_disposition = headers.get("content-disposition") or ""
        assert 'inline; filename="doc.pdf"' in content_disposition
        assert "filename*=UTF-8''doc.pdf" in content_disposition
        assert headers.get("cache-control") == "no-store"
        assert body.startswith(b"%PDF")
    finally:
        server.shutdown()
        server.server_close()


def test_api_export_pdf_content_disposition_supports_unicode_filename(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    (posts / "doc.html").write_text("<html><body>Raw Doc</body></html>", encoding="utf-8")

    def _fake_export(_self: docflow_server.DocflowApp, _rel_path: str) -> tuple[bytes, str]:
        return b"%PDF-1.4\n%mock\n", "ARC‑AGI evaluación.pdf"

    monkeypatch.setattr(docflow_server.DocflowApp, "api_export_pdf", _fake_export)

    server, port = _start_server(base)
    try:
        status, body, headers = _get_bytes_with_headers(
            port,
            "/api/export-pdf?path=Posts%2FPosts%202026%2Fdoc.html",
        )
        assert status == 200
        assert headers.get("content-type") == "application/pdf"
        content_disposition = headers.get("content-disposition") or ""
        assert 'inline; filename="ARC-AGI evaluacion.pdf"' in content_disposition
        assert "filename*=UTF-8''ARC%E2%80%91AGI%20evaluaci%C3%B3n.pdf" in content_disposition
        assert body.startswith(b"%PDF")
    finally:
        server.shutdown()
        server.server_close()


def test_api_export_markdown_serves_attachment_bytes(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    (posts / "doc.html").write_text("<html><body>Raw Doc</body></html>", encoding="utf-8")
    (posts / "doc.md").write_text("# Doc\n", encoding="utf-8")

    def _fake_export(_self: docflow_server.DocflowApp, _rel_path: str) -> tuple[bytes, str]:
        return b"# Doc\n", "doc.md"

    monkeypatch.setattr(docflow_server.DocflowApp, "api_export_markdown", _fake_export)

    server, port = _start_server(base)
    try:
        status, body, headers = _get_bytes_with_headers(
            port,
            "/api/export-markdown?path=Posts%2FPosts%202026%2Fdoc.html",
        )
        assert status == 200
        assert headers.get("content-type") == "text/markdown; charset=utf-8"
        content_disposition = headers.get("content-disposition") or ""
        assert 'attachment; filename="doc.md"' in content_disposition
        assert "filename*=UTF-8''doc.md" in content_disposition
        assert headers.get("cache-control") == "no-store"
        assert body == b"# Doc\n"
    finally:
        server.shutdown()
        server.server_close()


def test_api_export_markdown_content_disposition_supports_unicode_filename(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    (posts / "doc.html").write_text("<html><body>Raw Doc</body></html>", encoding="utf-8")
    (posts / "doc.md").write_text("# Doc\n", encoding="utf-8")

    def _fake_export(_self: docflow_server.DocflowApp, _rel_path: str) -> tuple[bytes, str]:
        return b"# Doc\n", "nested/ARC‑AGI evaluación.html"

    monkeypatch.setattr(docflow_server.DocflowApp, "api_export_markdown", _fake_export)

    server, port = _start_server(base)
    try:
        status, body, headers = _get_bytes_with_headers(
            port,
            "/api/export-markdown?path=Posts%2FPosts%202026%2Fdoc.html",
        )
        assert status == 200
        assert headers.get("content-type") == "text/markdown; charset=utf-8"
        content_disposition = headers.get("content-disposition") or ""
        assert 'attachment; filename="ARC-AGI evaluacion.md"' in content_disposition
        assert "filename*=UTF-8''ARC%E2%80%91AGI%20evaluaci%C3%B3n.md" in content_disposition
        assert body == b"# Doc\n"
    finally:
        server.shutdown()
        server.server_close()


def test_api_export_markdown_content_disposition_forces_md_extension(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    (posts / "doc.html").write_text("<html><body>Raw Doc</body></html>", encoding="utf-8")
    (posts / "doc.md").write_text("# Doc\n", encoding="utf-8")

    def _fake_export(_self: docflow_server.DocflowApp, _rel_path: str) -> tuple[bytes, str]:
        return b"# Doc\n", "doc"

    monkeypatch.setattr(docflow_server.DocflowApp, "api_export_markdown", _fake_export)

    server, port = _start_server(base)
    try:
        status, body, headers = _get_bytes_with_headers(
            port,
            "/api/export-markdown?path=Posts%2FPosts%202026%2Fdoc.html",
        )
        assert status == 200
        assert headers.get("content-type") == "text/markdown; charset=utf-8"
        content_disposition = headers.get("content-disposition") or ""
        assert 'attachment; filename="doc.md"' in content_disposition
        assert "filename*=UTF-8''doc.md" in content_disposition
        assert body == b"# Doc\n"
    finally:
        server.shutdown()
        server.server_close()


def test_is_pandoc_yaml_metadata_parse_error_detects_known_messages():
    assert docflow_server._is_pandoc_yaml_metadata_parse_error(
        stderr='Error parsing YAML metadata at "/tmp/x.md" (line 10, column 1): YAML parse exception',
        stdout="",
    )
    assert docflow_server._is_pandoc_yaml_metadata_parse_error(
        stderr="",
        stdout="YAML parse exception at line 1, column 2",
    )
    assert not docflow_server._is_pandoc_yaml_metadata_parse_error(
        stderr="Error producing PDF. Something else",
        stdout="",
    )


def test_extract_pdflatex_unicode_error_codepoints_parses_hex_values():
    points = docflow_server._extract_pdflatex_unicode_error_codepoints(
        stderr=(
            "Error producing PDF.\n"
            "! LaTeX Error: Unicode character ⚡ (U+26A1)\n"
            "! LaTeX Error: Unicode character ≈ (U+2248)\n"
        ),
        stdout="",
    )
    assert points == {0x26A1, 0x2248}


@pytest.mark.parametrize(
    ("stderr", "stdout", "expected"),
    [
        ("Could not convert image /tmp/a.svg", "", True),
        ("", "Unknown graphics extension: .so", True),
        ("pdfTeX error: reading image file failed", "", True),
        ("Error producing PDF. Something else", "", False),
    ],
)
def test_is_pandoc_image_asset_error_detects_known_messages(stderr: str, stdout: str, expected: bool):
    assert docflow_server._is_pandoc_image_asset_error(stderr=stderr, stdout=stdout) is expected


def test_pdf_image_scale_header_tex_caps_height_without_upscaling():
    header_tex = docflow_server._pdf_image_scale_header_tex()
    assert "\\setlength\\docflowmaximgheight{7cm}" in header_tex
    assert "\\ifdim\\Gin@nat@height>\\docflowmaximgheight" in header_tex
    assert "\\else\\Gin@nat@height\\fi" in header_tex
    assert "\\ifdim\\Gin@nat@width>\\linewidth" in header_tex
    assert "\\setkeys{Gin}{width=\\docflowmaxwidth,height=\\docflowmaxheight,keepaspectratio}" in header_tex


def test_pdf_media_filter_lua_disables_svg_when_converter_missing():
    lua = docflow_server._pdf_media_filter_lua(keep_svg=False)
    assert "local KEEP_SVG = false" in lua
    assert "local ALLOW_REMOTE_IMAGES = true" in lua
    assert "function Header(el)" in lua
    assert "gsub('%%', ' percent ')" in lua
    assert "format=([a-z0-9]+)" in lua
    assert "is_known_extensionless_remote_image_src" in lua
    assert "is_known_proxy_image_src" in lua
    assert "res%.cloudinary%.com/.+/image/upload/" in lua
    assert "substackcdn%.com/image/fetch/" in lua
    assert "s = s:gsub('&amp;', '&')" in lua
    assert "pbs%.twimg%.com/media/" in lua
    assert "return allowed_ext[ext] == true" in lua


def test_pdf_media_filter_lua_enables_svg_when_converter_present():
    lua = docflow_server._pdf_media_filter_lua(keep_svg=True)
    assert "local KEEP_SVG = true" in lua
    assert "local ALLOW_REMOTE_IMAGES = true" in lua
    assert "if ext == 'svg' then" in lua
    assert "return KEEP_SVG" in lua


def test_pdf_media_filter_lua_can_disable_remote_images():
    lua = docflow_server._pdf_media_filter_lua(keep_svg=False, allow_remote_images=False)
    assert "local ALLOW_REMOTE_IMAGES = false" in lua
    assert "s:match('^https?://')" in lua


def test_pdf_media_filter_lua_allows_extensionless_cloudinary_images():
    lua = docflow_server._pdf_media_filter_lua(keep_svg=False)
    assert "is_known_extensionless_remote_image_src(path)" in lua
    assert "res%.cloudinary%.com/.+/image/upload/" in lua
    assert "res%.cloudinary%.com/.+/image/fetch/" in lua


def test_pdf_media_filter_lua_allows_substack_webp_proxy_images():
    lua = docflow_server._pdf_media_filter_lua(keep_svg=False)
    assert "ext == 'webp'" in lua
    assert "substackcdn%.com/image/fetch/" in lua


def test_render_pdf_bytes_retries_markdown_without_yaml_metadata_block(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    base.mkdir(parents=True)
    source = tmp_path / "source.md"
    source.write_text("# T\\n\\n---\\n[link](https://example.com)\\n", encoding="utf-8")
    app = docflow_server.DocflowApp(base)

    calls: list[list[str]] = []

    def _fake_run(cmd: list[str], **_kwargs):
        calls.append(cmd)
        output_idx = cmd.index("-o") + 1
        output_pdf = Path(cmd[output_idx])
        if len(calls) == 1:
            raise subprocess.CalledProcessError(
                returncode=43,
                cmd=cmd,
                output="",
                stderr='Error parsing YAML metadata at "/tmp/source.md" (line 412, column 1): YAML parse exception',
            )
        output_pdf.write_bytes(b"%PDF-1.4\\n%mock\\n")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(docflow_server.subprocess, "run", _fake_run)

    payload = app._render_pdf_bytes(
        source,
        ".md",
        "/usr/bin/pandoc",
        "/usr/bin/pdflatex",
    )
    assert payload.startswith(b"%PDF")
    assert len(calls) == 2
    assert "--lua-filter" in calls[0]
    assert "--lua-filter" in calls[1]
    assert "--from=markdown-yaml_metadata_block" not in calls[0]
    assert "--from=markdown-yaml_metadata_block" in calls[1]


def test_render_pdf_bytes_retries_after_pdflatex_unicode_error(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    base.mkdir(parents=True)
    source = tmp_path / "source.html"
    source.write_text("<h1>Approx ≈ value</h1>", encoding="utf-8")
    app = docflow_server.DocflowApp(base)

    calls: list[list[str]] = []

    def _fake_run(cmd: list[str], **_kwargs):
        calls.append(cmd)
        source_tmp = Path(cmd[1])
        output_idx = cmd.index("-o") + 1
        output_pdf = Path(cmd[output_idx])
        current_text = source_tmp.read_text(encoding="utf-8")
        if len(calls) == 1:
            assert "≈" in current_text
            raise subprocess.CalledProcessError(
                returncode=43,
                cmd=cmd,
                output="",
                stderr=(
                    "Error producing PDF.\n"
                    "! LaTeX Error: Unicode character ≈ (U+2248)\n"
                    "not set up for use with LaTeX."
                ),
            )
        assert "≈" not in current_text
        output_pdf.write_bytes(b"%PDF-1.4\\n%mock\\n")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(docflow_server.subprocess, "run", _fake_run)

    payload = app._render_pdf_bytes(
        source,
        ".html",
        "/usr/bin/pandoc",
        "/usr/bin/pdflatex",
    )
    assert payload.startswith(b"%PDF")
    assert len(calls) == 2


def test_render_pdf_bytes_retries_without_remote_images_after_asset_error(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    base.mkdir(parents=True)
    source = tmp_path / "source.html"
    source.write_text('<img src="https://pbs.twimg.com/card_img/1/x?format=jpg&amp;name=small">', encoding="utf-8")
    app = docflow_server.DocflowApp(base)

    calls: list[list[str]] = []

    def _fake_run(cmd: list[str], **_kwargs):
        calls.append(cmd)
        filter_idx = cmd.index("--lua-filter") + 1
        filter_lua = Path(cmd[filter_idx]).read_text(encoding="utf-8")
        output_idx = cmd.index("-o") + 1
        output_pdf = Path(cmd[output_idx])

        if len(calls) == 1:
            assert "ALLOW_REMOTE_IMAGES = true" in filter_lua
            raise subprocess.CalledProcessError(
                returncode=43,
                cmd=cmd,
                output="",
                stderr="Error producing PDF.\n! LaTeX Error: Unknown graphics extension: .so.",
            )

        assert "ALLOW_REMOTE_IMAGES = false" in filter_lua
        output_pdf.write_bytes(b"%PDF-1.4\\n%mock\\n")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(docflow_server.subprocess, "run", _fake_run)

    payload = app._render_pdf_bytes(
        source,
        ".html",
        "/usr/bin/pandoc",
        "/usr/bin/pdflatex",
    )
    assert payload.startswith(b"%PDF")
    assert len(calls) == 2


def test_render_pdf_bytes_accepts_nonzero_pandoc_exit_when_pdf_exists(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    base.mkdir(parents=True)
    source = tmp_path / "source.html"
    source.write_text("<h1>hello</h1>", encoding="utf-8")
    app = docflow_server.DocflowApp(base)

    def _fake_run(cmd: list[str], **_kwargs):
        output_idx = cmd.index("-o") + 1
        output_pdf = Path(cmd[output_idx])
        output_pdf.write_bytes(b"%PDF-1.4\\n%mock\\n")
        return subprocess.CompletedProcess(cmd, 1, "stdout warn", "stderr warn")

    monkeypatch.setattr(docflow_server.subprocess, "run", _fake_run)

    payload = app._render_pdf_bytes(
        source,
        ".html",
        "/usr/bin/pandoc",
        "/usr/bin/pdflatex",
    )
    assert payload.startswith(b"%PDF")


def test_sanitize_pdf_source_text_replaces_common_pdflatex_breakers():
    raw = (
        "x\u2208y\u00B7z \u221A \u2265 \u2260 \u2212 \u2211 \u222B \u221E "
        "\u03B4\u0394\u03C0\u03A9\u03BC\u03BD "
        "\u2B50\u2605\u2666\u26A1 \uF8FF a\u2032b c\u2074 d\u2085 "
        "p\u2009q r\u200As \u2061\u200D\uFE0F\uFFFD"
    )
    cleaned = docflow_server._sanitize_pdf_source_text(raw)

    assert "\u2208" not in cleaned
    assert "\u00B7" not in cleaned
    assert "\u221A" not in cleaned
    assert "\u2265" not in cleaned
    assert "\u2260" not in cleaned
    assert "\u2212" not in cleaned
    assert "\u2211" not in cleaned
    assert "\u222B" not in cleaned
    assert "\u221E" not in cleaned
    assert "\u03B4" not in cleaned
    assert "\u0394" not in cleaned
    assert "\u03C0" not in cleaned
    assert "\u03A9" not in cleaned
    assert "\u03BC" not in cleaned
    assert "\u03BD" not in cleaned
    assert "\u2B50" not in cleaned
    assert "\u2605" not in cleaned
    assert "\u2666" not in cleaned
    assert "\u26A1" not in cleaned
    assert "\uF8FF" not in cleaned
    assert "\u2009" not in cleaned
    assert "\u200A" not in cleaned
    assert "\u2061" not in cleaned
    assert "\u200D" not in cleaned
    assert "\uFE0F" not in cleaned
    assert "\uFFFD" not in cleaned

    assert "in" in cleaned
    assert "sqrt" in cleaned
    assert ">=" in cleaned
    assert "!=" in cleaned
    assert "sum" in cleaned
    assert "integral" in cleaned
    assert "infinity" in cleaned
    assert "deltaDeltapiOmegamunu" in cleaned
    assert "Apple" in cleaned
    assert "a'b" in cleaned
    assert "c4" in cleaned
    assert "d5" in cleaned
    assert "p q" in cleaned
    assert "r s" in cleaned


def test_sanitize_pdf_source_text_strips_supplementary_plane_emoji():
    raw = "ok \U0001F60A keep \U0001F633 done"
    cleaned = docflow_server._sanitize_pdf_source_text(raw)
    assert "\U0001F60A" not in cleaned
    assert "\U0001F633" not in cleaned
    assert cleaned == "ok  keep  done"


def test_sanitize_pdf_source_text_strips_bmp_emoji_like_symbols():
    raw = "⚡In today\u2019s edition ✅ ready ✨ done"
    cleaned = docflow_server._sanitize_pdf_source_text(raw)
    assert "⚡" not in cleaned
    assert "✅" not in cleaned
    assert "✨" not in cleaned
    assert cleaned == "In today\u2019s edition  ready  done"


def test_sanitize_pdf_source_text_normalizes_mathematical_unicode_letters():
    raw = "Author 𝕖"
    cleaned = docflow_server._sanitize_pdf_source_text(raw)
    assert "𝕖" not in cleaned
    assert cleaned == "Author e"


def test_api_export_pdf_generates_real_pdf_when_tools_available(tmp_path: Path):
    if shutil.which("pandoc") is None or shutil.which("pdflatex") is None:
        pytest.skip("pandoc and pdflatex are required for PDF export test")

    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    # Exercise the sanitizer path for unicode symbols seen in real documents.
    (posts / "doc.md").write_text("# Real PDF\n\n⚡In today\n\nx ∈ y\n\nfoo · bar\n", encoding="utf-8")

    server, port = _start_server(base)
    try:
        status, body, headers = _get_bytes_with_headers(
            port,
            "/api/export-pdf?path=Posts%2FPosts%202026%2Fdoc.md",
        )
        assert status == 200
        assert headers.get("content-type") == "application/pdf"
        content_disposition = headers.get("content-disposition") or ""
        assert 'inline; filename="doc.pdf"' in content_disposition
        assert "filename*=UTF-8''doc.pdf" in content_disposition
        assert headers.get("cache-control") == "no-store"
        assert body.startswith(b"%PDF")
    finally:
        server.shutdown()
        server.server_close()


def test_api_export_pdf_requires_query_path(tmp_path: Path):
    base = tmp_path / "base"
    (base / "Posts" / "Posts 2026").mkdir(parents=True)

    server, port = _start_server(base)
    try:
        status, body = _get(port, "/api/export-pdf")
        payload = json.loads(body)
        assert status == 400
        assert payload["ok"] is False
        assert "Query parameter 'path' is required" in payload["error"]
    finally:
        server.shutdown()
        server.server_close()


def test_api_export_pdf_returns_404_for_missing_file(tmp_path: Path):
    base = tmp_path / "base"
    (base / "Posts" / "Posts 2026").mkdir(parents=True)

    server, port = _start_server(base)
    try:
        status, body = _get(port, "/api/export-pdf?path=Posts%2FPosts%202026%2Fmissing.html")
        payload = json.loads(body)
        assert status == 404
        assert payload["ok"] is False
        assert "File not found" in payload["error"]
    finally:
        server.shutdown()
        server.server_close()


def test_api_export_pdf_returns_400_for_unsupported_extension(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    (posts / "doc.txt").write_text("text", encoding="utf-8")

    server, port = _start_server(base)
    try:
        status, body = _get(port, "/api/export-pdf?path=Posts%2FPosts%202026%2Fdoc.txt")
        payload = json.loads(body)
        assert status == 400
        assert payload["ok"] is False
        assert "only supported for .md/.html files" in payload["error"]
    finally:
        server.shutdown()
        server.server_close()


def test_api_export_pdf_returns_503_when_pandoc_missing(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    (posts / "doc.md").write_text("# Doc\n", encoding="utf-8")

    original_which = docflow_server.shutil.which

    def _which(name: str) -> str | None:
        if name == "pandoc":
            return None
        return original_which(name)

    monkeypatch.setattr(docflow_server, "_PDF_PANDOC_CANDIDATES", ())
    monkeypatch.setattr(docflow_server.shutil, "which", _which)

    server, port = _start_server(base)
    try:
        status, body = _get(port, "/api/export-pdf?path=Posts%2FPosts%202026%2Fdoc.md")
        payload = json.loads(body)
        assert status == 503
        assert payload["ok"] is False
        assert "Missing required executable: pandoc" == payload["error"]
    finally:
        server.shutdown()
        server.server_close()


def test_api_export_pdf_returns_503_when_pdflatex_missing(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    (posts / "doc.md").write_text("# Doc\n", encoding="utf-8")

    original_which = docflow_server.shutil.which

    def _which(name: str) -> str | None:
        if name == "pdflatex":
            return None
        return original_which(name)

    monkeypatch.setattr(docflow_server, "_PDF_PDFLATEX_CANDIDATES", ())
    monkeypatch.setattr(docflow_server.shutil, "which", _which)

    server, port = _start_server(base)
    try:
        status, body = _get(port, "/api/export-pdf?path=Posts%2FPosts%202026%2Fdoc.md")
        payload = json.loads(body)
        assert status == 503
        assert payload["ok"] is False
        assert "Missing required executable: pdflatex" == payload["error"]
    finally:
        server.shutdown()
        server.server_close()


def test_api_export_pdf_prefers_html_source(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    html = posts / "doc.html"
    md = posts / "doc.md"
    html.write_text("<html><body>HTML Doc</body></html>", encoding="utf-8")
    md.write_text("# Markdown Doc\n", encoding="utf-8")

    app = docflow_server.DocflowApp(base)
    captured: dict[str, Path] = {}

    monkeypatch.setattr(docflow_server.shutil, "which", lambda _name: "/usr/bin/fake")

    def _fake_render(source_abs: Path, _suffix: str, _pandoc: str, _pdflatex: str) -> bytes:
        captured["source_abs"] = source_abs
        return b"%PDF-1.4\n%mock\n"

    monkeypatch.setattr(app, "_render_pdf_bytes", _fake_render)

    data, filename = app.api_export_pdf("Posts/Posts 2026/doc.html")
    assert data.startswith(b"%PDF")
    assert filename == "doc.pdf"
    assert captured["source_abs"] == html


def test_api_export_pdf_falls_back_to_markdown_when_html_missing(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    md = posts / "doc.md"
    md.write_text("# Markdown Doc\\n", encoding="utf-8")

    app = docflow_server.DocflowApp(base)
    captured: dict[str, Path] = {}

    monkeypatch.setattr(docflow_server.shutil, "which", lambda _name: "/usr/bin/fake")

    def _fake_render(source_abs: Path, _suffix: str, _pandoc: str, _pdflatex: str) -> bytes:
        captured["source_abs"] = source_abs
        return b"%PDF-1.4\n%mock\n"

    monkeypatch.setattr(app, "_render_pdf_bytes", _fake_render)

    data, filename = app.api_export_pdf("Posts/Posts 2026/doc.md")
    assert data.startswith(b"%PDF")
    assert filename == "doc.pdf"
    assert captured["source_abs"] == md


def test_api_export_pdf_prefers_html_even_when_path_points_to_markdown(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    md = posts / "doc.md"
    html = posts / "doc.html"
    md.write_text("# Markdown Doc\\n", encoding="utf-8")
    html.write_text("<html><body>HTML Doc</body></html>", encoding="utf-8")

    app = docflow_server.DocflowApp(base)
    captured: dict[str, Path] = {}

    monkeypatch.setattr(docflow_server.shutil, "which", lambda _name: "/usr/bin/fake")

    def _fake_render(source_abs: Path, _suffix: str, _pandoc: str, _pdflatex: str) -> bytes:
        captured["source_abs"] = source_abs
        return b"%PDF-1.4\\n%mock\\n"

    monkeypatch.setattr(app, "_render_pdf_bytes", _fake_render)

    data, filename = app.api_export_pdf("Posts/Posts 2026/doc.md")
    assert data.startswith(b"%PDF")
    assert filename == "doc.pdf"
    assert captured["source_abs"] == html


def test_api_export_markdown_uses_associated_markdown_when_path_points_to_html(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    html = posts / "doc.html"
    md = posts / "doc.md"
    html.write_text("<html><body>HTML Doc</body></html>", encoding="utf-8")
    md.write_text("# Markdown Doc\n", encoding="utf-8")

    app = docflow_server.DocflowApp(base)

    data, filename = app.api_export_markdown("Posts/Posts 2026/doc.html")
    assert data == b"# Markdown Doc\n"
    assert filename == "doc.md"


def test_api_export_markdown_rejects_html_without_associated_markdown(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    (posts / "doc.html").write_text("<html><body>HTML Doc</body></html>", encoding="utf-8")

    app = docflow_server.DocflowApp(base)

    with pytest.raises(docflow_server.ApiError, match="Associated Markdown file not found"):
        app.api_export_markdown("Posts/Posts 2026/doc.html")


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


def test_api_reading_position_roundtrip(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    html = posts / "doc.html"
    html.write_text("<html><body>Raw Doc</body></html>", encoding="utf-8")

    rel_path = "Posts/Posts 2026/doc.html"
    encoded = quote(rel_path, safe="")

    server, port = _start_server(base)
    try:
        status, body = _get(port, f"/api/reading-position?path={encoded}")
        assert status == 200
        payload = json.loads(body)
        assert payload["path"] == rel_path
        assert payload["scroll_y"] is None
        assert payload["progress"] is None

        status, payload = _put_json(
            port,
            f"/api/reading-position?path={encoded}",
            {
                "updated_at": "2026-03-17T10:00:00Z",
                "scroll_y": 420,
                "max_scroll": 1200,
                "progress": 0.35,
                "viewport_height": 900,
                "document_height": 2100,
            },
        )
        assert status == 200
        assert payload["path"] == rel_path
        assert payload["scroll_y"] == 420
        assert payload["progress"] == 0.35

        status, body = _get(port, f"/api/reading-position?path={encoded}")
        assert status == 200
        payload = json.loads(body)
        assert payload["scroll_y"] == 420
        assert payload["progress"] == 0.35

        status, _payload = _put_json(
            port,
            f"/api/reading-position?path={encoded}",
            {
                "updated_at": "2026-03-17T10:01:00Z",
                "scroll_y": 0,
                "max_scroll": 1200,
                "progress": 0,
                "viewport_height": 900,
                "document_height": 2100,
            },
        )
        assert status == 200

        status, body = _get(port, f"/api/reading-position?path={encoded}")
        assert status == 200
        payload = json.loads(body)
        assert payload["scroll_y"] is None
        assert payload["progress"] is None
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


def test_api_to_working_rebuilds_only_reading_and_working(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    rel = "Posts/Posts 2026/doc.html"
    (posts / "doc.html").write_text("<html><body>Doc</body></html>", encoding="utf-8")

    app = docflow_server.DocflowApp(base)
    docflow_server.set_reading_path(base, rel)
    calls: list[str] = []

    def _browse(*_args, **_kwargs):
        calls.append("browse")
        return {"mode": "partial"}

    def _reading(*_args, **_kwargs):
        calls.append("reading")

    def _working(*_args, **_kwargs):
        calls.append("working")

    def _done(*_args, **_kwargs):
        calls.append("done")

    monkeypatch.setattr(docflow_server.build_browse_index, "rebuild_browse_for_path", _browse)
    monkeypatch.setattr(docflow_server.build_reading_index, "write_site_reading_index", _reading)
    monkeypatch.setattr(docflow_server.build_working_index, "write_site_working_index", _working)
    monkeypatch.setattr(docflow_server.build_done_index, "write_site_done_index", _done)

    result = app.api_to_working(rel)
    assert result["stage"] == "working"
    assert result["changed"] is True
    assert calls == ["reading", "working"]


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

    def _reading(*_args, **_kwargs):
        calls.append("reading")

    def _working(*_args, **_kwargs):
        calls.append("working")

    def _done(*_args, **_kwargs):
        calls.append("done")

    monkeypatch.setattr(docflow_server.build_browse_index, "rebuild_browse_for_path", _browse)
    monkeypatch.setattr(docflow_server.build_reading_index, "write_site_reading_index", _reading)
    monkeypatch.setattr(docflow_server.build_working_index, "write_site_working_index", _working)
    monkeypatch.setattr(docflow_server.build_done_index, "write_site_done_index", _done)

    result = app.api_to_done(rel)
    assert result["stage"] == "done"
    assert result["changed"] is True
    assert calls == ["working", "done"]
