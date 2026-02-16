#!/usr/bin/env python3
"""Single local server for docflow intranet.

Features:
- Serves generated site files from BASE_DIR/_site
- Serves raw files from BASE_DIR via dedicated routes (/posts/raw/..., /pdfs/raw/...)
- Exposes API actions under /api/* (publish, unpublish, bump, unbump, delete, rebuild)
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
from urllib.parse import parse_qs, quote, urlparse, unquote

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
from utils.highlight_store import load_highlights_for_path, save_highlights_for_path


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


def _browse_parent_url_for_rel_path(rel_path: str) -> str:
    normalized = normalize_rel_path(rel_path)
    parts = Path(normalized).parts
    if len(parts) < 2:
        return "/browse/"

    category_map = {
        "Posts": "posts",
        "Tweets": "tweets",
        "Pdfs": "pdfs",
        "PDFs": "pdfs",
        "Images": "images",
        "Podcasts": "podcasts",
    }
    category = category_map.get(parts[0])
    if category is None:
        return "/browse/"

    parent_parts = parts[1:-1]
    if not parent_parts:
        return f"/browse/{category}/"

    encoded = "/".join(quote(part, safe="~!*()'") for part in parent_parts)
    return f"/browse/{category}/{encoded}/"


def _browse_url_from_raw_path(request_path: str) -> str:
    prefixes = (
        ("/posts/raw", "posts"),
        ("/tweets/raw", "tweets"),
        ("/pdfs/raw", "pdfs"),
        ("/images/raw", "images"),
        ("/podcasts/raw", "podcasts"),
    )

    for prefix, category in prefixes:
        if request_path == prefix or request_path == f"{prefix}/":
            return f"/browse/{category}/"
        if request_path.startswith(prefix + "/"):
            rel = request_path[len(prefix) + 1 :].strip("/")
            if not rel:
                return f"/browse/{category}/"
            decoded = unquote(rel)
            encoded = quote(decoded, safe="~!*()'/-")
            return f"/browse/{category}/{encoded}/"

    return "/browse/"


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

    def rebuild_for_path(self, rel_path: str) -> None:
        build_browse_index.rebuild_browse_for_path(self.base_dir, rel_path)
        build_read_index.write_site_read_index(self.base_dir)

    def _next_bump_mtime(self) -> float:
        with self._bump_lock:
            self._bump_counter += 1
            counter = self._bump_counter
        base = _add_years(datetime.now().replace(microsecond=0), self.bump_years)
        return float(int(base.timestamp()) + counter)

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
        self.rebuild_for_path(normalized)
        return {"changed": changed, "path": normalized}

    def api_unpublish(self, rel_path: str) -> dict[str, object]:
        normalized = normalize_rel_path(rel_path)
        changed = unpublish_path(self.base_dir, normalized)
        self.rebuild_for_path(normalized)
        return {"changed": changed, "path": normalized}

    def api_bump(self, rel_path: str) -> dict[str, object]:
        normalized, abs_path = self._resolve_existing_file(rel_path)
        entry = get_bumped_entry(self.base_dir, normalized)

        st = abs_path.stat()
        original_mtime = float(entry.get("original_mtime", st.st_mtime)) if entry else float(st.st_mtime)
        bumped_mtime = self._next_bump_mtime()

        set_bumped_path(
            self.base_dir,
            normalized,
            original_mtime=original_mtime,
            bumped_mtime=bumped_mtime,
        )
        self.rebuild_for_path(normalized)
        return {"path": normalized, "bumped_mtime": bumped_mtime}

    def api_unbump(self, rel_path: str) -> dict[str, object]:
        normalized, _ = self._resolve_existing_file(rel_path)
        entry = pop_bumped_path(self.base_dir, normalized)
        if entry is None:
            raise ApiError(409, f"Path is not bumped: {normalized}")

        original_mtime = float(entry.get("original_mtime", time.time()))
        self.rebuild_for_path(normalized)
        return {"path": normalized, "restored_mtime": original_mtime}

    def api_delete(self, rel_path: str) -> dict[str, object]:
        normalized, abs_path = self._resolve_existing_file(rel_path)
        sibling_md = abs_path.with_suffix(".md")
        sibling_md_rel: str | None = None
        if sibling_md != abs_path:
            try:
                sibling_md_rel = rel_path_from_abs(self.base_dir, sibling_md)
            except Exception:
                sibling_md_rel = None

        try:
            abs_path.unlink()
        except FileNotFoundError as exc:
            raise ApiError(404, f"File not found: {normalized}") from exc
        except OSError as exc:
            raise ApiError(500, f"Could not delete file: {exc}") from exc

        deleted_md = False
        if sibling_md != abs_path and sibling_md.is_file():
            try:
                sibling_md.unlink()
                deleted_md = True
            except OSError as exc:
                raise ApiError(500, f"Could not delete associated Markdown: {exc}") from exc

        unpublished = unpublish_path(self.base_dir, normalized)
        pop_bumped_path(self.base_dir, normalized)

        if sibling_md_rel:
            unpublish_path(self.base_dir, sibling_md_rel)
            pop_bumped_path(self.base_dir, sibling_md_rel)

        self.rebuild_for_path(normalized)
        return {
            "path": normalized,
            "deleted_md": deleted_md,
            "unpublished": unpublished,
            "redirect": _browse_parent_url_for_rel_path(normalized),
        }

    def api_rebuild(self) -> dict[str, object]:
        self.rebuild()
        return {"rebuilt": True}

    def api_get_highlights(self, rel_path: str) -> dict[str, object]:
        normalized, _ = self._resolve_existing_file(rel_path)
        return load_highlights_for_path(self.base_dir, normalized)

    def api_put_highlights(self, rel_path: str, payload: dict[str, object]) -> dict[str, object]:
        normalized, _ = self._resolve_existing_file(rel_path)
        saved = save_highlights_for_path(self.base_dir, normalized, payload)
        self.rebuild_for_path(normalized)
        return saved

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
        if action == "delete":
            return self.api_delete(raw_path)

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
  right: 12px;
  top: 12px;
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
      if (action === 'delete') {
        const name = relPath.split('/').pop() || relPath || 'this file';
        if (!window.confirm(`Are you sure you want to delete "${name}"?`)) {
          return;
        }
      }
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
        if (action === 'delete') {
          let redirectTo = '/browse/';
          try {
            const payload = await res.json();
            const maybe = payload && payload.data && payload.data.redirect;
            if (typeof maybe === 'string' && maybe) redirectTo = maybe;
          } catch (error) {}
          window.location.assign(redirectTo);
          return;
        }
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
    bar.appendChild(makeButton('Delete', 'delete'));
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


def _ensure_viewport_meta(html_text: str) -> str:
    lower = html_text.lower()
    if 'name="viewport"' in lower or "name='viewport'" in lower:
        return html_text

    viewport = '<meta name="viewport" content="width=device-width, initial-scale=1">'
    head_start = lower.find("<head")
    if head_start != -1:
        head_end = lower.find(">", head_start)
        if head_end != -1:
            return html_text[: head_end + 1] + viewport + html_text[head_end + 1 :]

    html_start = lower.find("<html")
    if html_start != -1:
        html_end = lower.find(">", html_start)
        if html_end != -1:
            return html_text[: html_end + 1] + f"<head>{viewport}</head>" + html_text[html_end + 1 :]

    body_start = lower.find("<body")
    if body_start != -1:
        return html_text[:body_start] + f"<head>{viewport}</head>" + html_text[body_start:]

    return f"<head>{viewport}</head>{html_text}"


def _inject_html_overlay(*, html_text: str, rel_path: str, published: bool, bumped: bool) -> bytes:
    html_text = _ensure_viewport_meta(html_text)
    path_attr = html.escape(rel_path, quote=True)
    article_js = ""
    if "/read/article.js" not in html_text:
        article_js = f"<script defer src=\"/read/article.js\" data-docflow-path=\"{path_attr}\"></script>"
    tags = (
        article_js
        + f"<style>{OVERLAY_CSS}</style>"
        + f"<script defer data-path=\"{path_attr}\" data-published=\"{'1' if published else '0'}\" "
        + f"data-bumped=\"{'1' if bumped else '0'}\">{OVERLAY_JS}</script>"
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


def _get_query_path(parsed) -> str:
    query = parse_qs(parsed.query)
    value = query.get("path", [""])[0]
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, "Query parameter 'path' is required")
    return value


def make_handler(app: DocflowApp):
    class DocflowHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # type: ignore[override]
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/api/highlights":
                try:
                    rel_path = _get_query_path(parsed)
                    payload = app.api_get_highlights(rel_path)
                    _send_json(self, 200, payload)
                except ApiError as exc:
                    _send_json(self, exc.status, {"ok": False, "error": exc.message})
                except Exception as exc:
                    _send_json(self, 500, {"ok": False, "error": str(exc)})
                return

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
                if raw_target.is_dir():
                    self.send_response(302)
                    self.send_header("Location", _browse_url_from_raw_path(path))
                    self.end_headers()
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
            if action == "highlights":
                _send_json(self, 405, {"ok": False, "error": "Use GET/PUT for /api/highlights"})
                return
            try:
                payload = _parse_json_body(self)
                data = app.handle_api(action, payload)
                _send_json(self, 200, {"ok": True, "data": data})
            except ApiError as exc:
                _send_json(self, exc.status, {"ok": False, "error": exc.message})
            except Exception as exc:
                _send_json(self, 500, {"ok": False, "error": str(exc)})

        def do_PUT(self) -> None:  # type: ignore[override]
            parsed = urlparse(self.path)
            if parsed.path != "/api/highlights":
                _send_json(self, 404, {"ok": False, "error": "Unknown endpoint"})
                return

            try:
                rel_path = _get_query_path(parsed)
                payload = _parse_json_body(self)
                data = app.api_put_highlights(rel_path, payload)
                _send_json(self, 200, data)
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
    parser.set_defaults(rebuild_on_start=False)
    parser.add_argument(
        "--rebuild-on-start",
        dest="rebuild_on_start",
        action="store_true",
        help="Rebuild browse/read static pages before serving.",
    )
    # Backward compatibility: previously this was the explicit opt-out flag.
    parser.add_argument("--no-rebuild-on-start", dest="rebuild_on_start", action="store_false", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_dir = resolve_base_dir(args.base_dir)

    app = DocflowApp(base_dir, bump_years=args.bump_years)
    if args.rebuild_on_start:
        app.rebuild()

    handler_cls = make_handler(app)

    with ThreadingHTTPServer((args.host, args.port), handler_cls) as server:
        print(f"Serving docflow intranet from {base_dir}")
        print(f"URL: http://{args.host}:{args.port}")
        server.serve_forever()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
