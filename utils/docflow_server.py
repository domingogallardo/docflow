#!/usr/bin/env python3
"""Single local server for docflow intranet.

Features:
- Serves generated site files from BASE_DIR/_site
- Serves raw files from BASE_DIR via dedicated routes (/posts/raw/..., /pdfs/raw/...)
- Exposes API actions under /api/* (publish, unpublish, bump, unbump, rebuild)
"""

from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import time
from urllib.parse import urlparse, unquote

# Support direct execution: `python utils/docflow_server.py ...`
if __package__ in (None, ""):
    _REPO_ROOT = Path(__file__).resolve().parents[1]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from utils import build_browse_index, build_read_index
from utils.site_paths import (
    PathValidationError,
    normalize_rel_path,
    rel_path_from_abs,
    resolve_base_dir,
    resolve_library_path,
    resolve_raw_path,
    site_root,
)
from utils.site_state import get_bumped_entry, is_published, pop_bumped_path, publish_path, set_bumped_path, unpublish_path


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _add_years(dt: datetime, years: int) -> datetime:
    try:
        return dt.replace(year=dt.year + years)
    except ValueError:
        return dt.replace(month=2, day=28, year=dt.year + years)


class DocflowApp:
    def __init__(self, base_dir: Path, *, bump_years: int = 100):
        self.base_dir = base_dir
        self.bump_years = bump_years
        self._bump_lock = threading.Lock()
        self._bump_counter = 0

    @property
    def site_dir(self) -> Path:
        return site_root(self.base_dir)

    def rebuild(self) -> None:
        build_browse_index.build_browse_site(self.base_dir)
        build_read_index.write_site_read_index(self.base_dir)

    def _next_bump_mtime(self) -> float:
        with self._bump_lock:
            self._bump_counter += 1
            counter = self._bump_counter
        base = _add_years(datetime.now().replace(microsecond=0), self.bump_years)
        return float(int(base.timestamp()) + counter)

    def _related_paths(self, abs_path: Path) -> list[Path]:
        paths: list[Path] = [abs_path]
        suffix = abs_path.suffix.lower()
        if suffix in (".html", ".htm"):
            candidate = abs_path.with_suffix(".md")
            if candidate.is_file():
                paths.append(candidate)
        elif suffix == ".md":
            for ext in (".html", ".htm"):
                candidate = abs_path.with_suffix(ext)
                if candidate.is_file():
                    paths.append(candidate)
        return paths

    def _set_mtime(self, abs_path: Path, mtime: float) -> None:
        for path in self._related_paths(abs_path):
            st = path.stat()
            os.utime(path, (st.st_atime, mtime))

    def _resolve_existing_file(self, rel_path: str) -> tuple[str, Path]:
        try:
            normalized = normalize_rel_path(rel_path)
            abs_path = resolve_library_path(self.base_dir, normalized)
        except PathValidationError as exc:
            raise ApiError(400, str(exc)) from exc

        if not abs_path.exists():
            raise ApiError(404, f"File not found: {normalized}")
        if not abs_path.is_file():
            raise ApiError(400, "Path must be a file")

        return normalized, abs_path

    def api_publish(self, rel_path: str) -> dict[str, object]:
        normalized, _ = self._resolve_existing_file(rel_path)
        changed = publish_path(self.base_dir, normalized)
        self.rebuild()
        return {"changed": changed, "path": normalized}

    def api_unpublish(self, rel_path: str) -> dict[str, object]:
        normalized = normalize_rel_path(rel_path)
        changed = unpublish_path(self.base_dir, normalized)
        self.rebuild()
        return {"changed": changed, "path": normalized}

    def api_bump(self, rel_path: str) -> dict[str, object]:
        normalized, abs_path = self._resolve_existing_file(rel_path)
        entry = get_bumped_entry(self.base_dir, normalized)

        st = abs_path.stat()
        original_mtime = float(entry.get("original_mtime", st.st_mtime)) if entry else float(st.st_mtime)
        bumped_mtime = self._next_bump_mtime()

        self._set_mtime(abs_path, bumped_mtime)
        set_bumped_path(
            self.base_dir,
            normalized,
            original_mtime=original_mtime,
            bumped_mtime=bumped_mtime,
        )
        self.rebuild()
        return {"path": normalized, "bumped_mtime": bumped_mtime}

    def api_unbump(self, rel_path: str) -> dict[str, object]:
        normalized, abs_path = self._resolve_existing_file(rel_path)
        entry = pop_bumped_path(self.base_dir, normalized)
        if entry is None:
            raise ApiError(409, f"Path is not bumped: {normalized}")

        original_mtime = float(entry.get("original_mtime", time.time()))
        self._set_mtime(abs_path, original_mtime)
        self.rebuild()
        return {"path": normalized, "restored_mtime": original_mtime}

    def api_rebuild(self) -> dict[str, object]:
        self.rebuild()
        return {"rebuilt": True}

    def handle_api(self, action: str, payload: dict[str, object]) -> dict[str, object]:
        action = action.strip("/")
        if action == "rebuild":
            return self.api_rebuild()

        raw_path = payload.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ApiError(400, "Field 'path' is required")

        if action == "publish":
            return self.api_publish(raw_path)
        if action == "unpublish":
            return self.api_unpublish(raw_path)
        if action == "bump":
            return self.api_bump(raw_path)
        if action == "unbump":
            return self.api_unbump(raw_path)

        raise ApiError(404, f"Unknown API action: {action}")

    def resolve_site_file(self, request_path: str) -> Path | None:
        if request_path == "/":
            target = self.site_dir / "index.html"
            return target if target.is_file() else None

        rel = request_path.lstrip("/")
        try:
            normalized = normalize_rel_path(unquote(rel))
        except PathValidationError:
            return None

        candidate = (self.site_dir / normalized).resolve()
        site_abs = self.site_dir.resolve()
        if not (candidate == site_abs or str(candidate).startswith(str(site_abs) + os.sep)):
            return None

        if candidate.is_dir():
            index = candidate / "index.html"
            return index if index.is_file() else None

        if candidate.is_file():
            return candidate

        return None


def _send_json(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, object]) -> None:
    body = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _send_file(handler: BaseHTTPRequestHandler, path: Path) -> None:
    data = path.read_bytes()
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


OVERLAY_CSS = """
#dg-overlay {
  position: fixed;
  right: 16px;
  bottom: 16px;
  z-index: 2147483000;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding: 8px;
  border: 1px solid #cfcfcf;
  border-radius: 10px;
  background: #ffffff;
  box-shadow: 0 4px 16px rgba(0,0,0,0.15);
  font: 12px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;
}
#dg-overlay button {
  padding: 4px 8px;
  border: 1px solid #bfbfbf;
  border-radius: 6px;
  background: #f6f6f6;
  color: #333;
  cursor: pointer;
}
#dg-overlay button[disabled] {
  opacity: .6;
  cursor: default;
}
""".strip()


OVERLAY_JS = """
(function() {
  const script = document.currentScript;
  const relPath = script.getAttribute('data-path') || '';
  if (!relPath) return;

  let bumped = script.getAttribute('data-bumped') === '1';
  let published = script.getAttribute('data-published') === '1';
  let busy = false;

  function callApi(action, path) {
    const body = path ? { path } : {};
    return fetch(`/api/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
  }

  function makeButton(label, action) {
    const button = document.createElement('button');
    button.textContent = label;
    button.addEventListener('click', async () => {
      if (busy) return;
      busy = true;
      render();
      try {
        const res = await callApi(action, relPath);
        if (!res.ok) {
          alert(`Action failed: ${action}`);
          busy = false;
          render();
          return;
        }
        if (action === 'bump') bumped = true;
        if (action === 'unbump') bumped = false;
        if (action === 'publish') published = true;
        if (action === 'unpublish') published = false;
        window.location.reload();
      } catch (error) {
        alert(`Action error: ${action}`);
        busy = false;
        render();
      }
    });
    return button;
  }

  function render() {
    bar.innerHTML = '';
    bar.appendChild(makeButton(bumped ? 'Unbump' : 'Bump', bumped ? 'unbump' : 'bump'));
    bar.appendChild(makeButton(published ? 'Unpublish' : 'Publish', published ? 'unpublish' : 'publish'));
    if (busy) {
      for (const btn of bar.querySelectorAll('button')) btn.setAttribute('disabled', '');
    }
  }

  const bar = document.createElement('div');
  bar.id = 'dg-overlay';
  document.addEventListener('DOMContentLoaded', () => {
    document.body.appendChild(bar);
    render();
  });
})();
""".strip()


def _inject_html_overlay(*, html_text: str, rel_path: str, published: bool, bumped: bool) -> bytes:
    path_attr = html.escape(rel_path, quote=True)
    tags = (
        f"<style>{OVERLAY_CSS}</style>"
        f"<script defer data-path=\"{path_attr}\" data-published=\"{'1' if published else '0'}\" "
        f"data-bumped=\"{'1' if bumped else '0'}\">{OVERLAY_JS}</script>"
    )
    lower = html_text.lower()
    idx = lower.rfind("</body>")
    merged = html_text + tags if idx == -1 else html_text[:idx] + tags + html_text[idx:]
    return merged.encode("utf-8", "surrogateescape")


def _send_overlay_html(handler: BaseHTTPRequestHandler, app: DocflowApp, abs_path: Path, rel_path: str) -> None:
    try:
        text = abs_path.read_text(encoding="utf-8", errors="surrogateescape")
    except Exception:
        _send_file(handler, abs_path)
        return

    published = is_published(app.base_dir, rel_path)
    bumped = get_bumped_entry(app.base_dir, rel_path) is not None
    payload = _inject_html_overlay(html_text=text, rel_path=rel_path, published=published, bumped=bumped)

    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def _parse_json_body(handler: BaseHTTPRequestHandler) -> dict[str, object]:
    raw_len = handler.headers.get("Content-Length", "0")
    try:
        length = int(raw_len)
    except ValueError:
        raise ApiError(400, "Invalid Content-Length")

    if length <= 0:
        return {}

    body = handler.rfile.read(length)
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:
        raise ApiError(400, "Invalid JSON body") from exc

    if not isinstance(payload, dict):
        raise ApiError(400, "JSON body must be an object")

    return payload


def make_handler(app: DocflowApp):
    class DocflowHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # type: ignore[override]
            parsed = urlparse(self.path)
            path = parsed.path

            if path.startswith("/api/"):
                _send_json(self, 405, {"ok": False, "error": "Use POST for API endpoints"})
                return

            raw_target = resolve_raw_path(app.base_dir, path)
            if raw_target is not None:
                if raw_target.is_file():
                    if raw_target.suffix.lower() in (".html", ".htm"):
                        rel_path = rel_path_from_abs(app.base_dir, raw_target)
                        _send_overlay_html(self, app, raw_target, rel_path)
                    else:
                        _send_file(self, raw_target)
                    return
                _send_json(self, 404, {"ok": False, "error": "Raw file not found"})
                return

            if path in ("/browse", "/read"):
                self.send_response(302)
                self.send_header("Location", path + "/")
                self.end_headers()
                return

            site_file = app.resolve_site_file(path)
            if site_file and site_file.is_file():
                _send_file(self, site_file)
                return

            _send_json(self, 404, {"ok": False, "error": "Not found"})

        def do_POST(self) -> None:  # type: ignore[override]
            parsed = urlparse(self.path)
            if not parsed.path.startswith("/api/"):
                _send_json(self, 404, {"ok": False, "error": "Unknown endpoint"})
                return

            action = parsed.path[len("/api/") :]
            try:
                payload = _parse_json_body(self)
                data = app.handle_api(action, payload)
                _send_json(self, 200, {"ok": True, "data": data})
            except ApiError as exc:
                _send_json(self, exc.status, {"ok": False, "error": exc.message})
            except Exception as exc:
                _send_json(self, 500, {"ok": False, "error": str(exc)})

        def log_message(self, format: str, *args: object) -> None:  # type: ignore[override]
            return

    return DocflowHandler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local docflow intranet server.")
    parser.add_argument("--base-dir", help="BASE_DIR with Incoming/Posts/Tweets/... and _site/")
    parser.add_argument("--host", default=os.getenv("DOCFLOW_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("DOCFLOW_PORT", "8088")))
    parser.add_argument("--bump-years", type=int, default=int(os.getenv("DOCFLOW_BUMP_YEARS", "100")))
    parser.add_argument("--no-rebuild-on-start", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_dir = resolve_base_dir(args.base_dir)

    app = DocflowApp(base_dir, bump_years=args.bump_years)
    if not args.no_rebuild_on_start:
        app.rebuild()

    handler_cls = make_handler(app)

    with ThreadingHTTPServer((args.host, args.port), handler_cls) as server:
        print(f"Serving docflow intranet from {base_dir}")
        print(f"URL: http://{args.host}:{args.port}")
        server.serve_forever()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
