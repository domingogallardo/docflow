#!/usr/bin/env python3
"""Single local server for docflow intranet.

Features:
- Serves generated site files from BASE_DIR/_site
- Serves raw files from BASE_DIR via dedicated routes (/posts/raw/..., /pdfs/raw/...)
- Exposes API actions under /api/* (to-working, to-done, to-browse, reopen, bump, unbump, delete, rebuild, rebuild-file)
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

from utils import add_margins_to_html_files, build_browse_index, build_done_index, build_working_index, markdown_to_html
from utils.site_paths import (
    PathValidationError,
    normalize_rel_path,
    rel_path_from_abs,
    resolve_base_dir,
    resolve_library_path,
    resolve_raw_path,
    site_root,
)
from utils.site_state import (
    get_bumped_entry,
    is_done,
    is_working,
    pop_bumped_path,
    pop_working_path,
    set_done_path,
    set_bumped_path,
    set_working_path,
    clear_done_path,
)
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


def _browse_index_url_for_raw_library_path(request_path: str) -> str:
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
    _PATH_ACTION_METHODS = {
        "to-working": "api_to_working",
        "to-done": "api_to_done",
        "to-browse": "api_to_browse",
        "reopen": "api_reopen",
        "bump": "api_bump",
        "unbump": "api_unbump",
        "delete": "api_delete",
        "rebuild-file": "api_rebuild_file",
    }

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
        build_working_index.write_site_working_index(self.base_dir)
        build_done_index.write_site_done_index(self.base_dir)

    def rebuild_for_path(
        self,
        rel_path: str,
        *,
        rebuild_browse: bool = True,
        rebuild_working: bool = True,
        rebuild_done: bool = True,
    ) -> None:
        if rebuild_browse:
            build_browse_index.rebuild_browse_for_path(self.base_dir, rel_path)
        if rebuild_working:
            build_working_index.write_site_working_index(self.base_dir)
        if rebuild_done:
            build_done_index.write_site_done_index(self.base_dir)

    def rebuild_for_stage_transition(self, rel_path: str, before_stage: str, after_stage: str) -> None:
        impacted_stages = {before_stage, after_stage}
        self.rebuild_for_path(
            rel_path,
            rebuild_browse="browse" in impacted_stages,
            rebuild_working="working" in impacted_stages,
            rebuild_done="done" in impacted_stages,
        )

    def _next_bump_mtime(self) -> float:
        with self._bump_lock:
            self._bump_counter += 1
            counter = self._bump_counter
        base = _add_years(datetime.now().replace(microsecond=0), self.bump_years)
        return float(int(base.timestamp()) + counter)

    def _normalize_rel_path_or_400(self, rel_path: str) -> str:
        try:
            return normalize_rel_path(rel_path)
        except PathValidationError as exc:
            raise ApiError(400, str(exc)) from exc

    def _require_existing_library_file(self, normalized_rel_path: str) -> Path:
        try:
            abs_path = resolve_library_path(self.base_dir, normalized_rel_path)
        except PathValidationError as exc:
            raise ApiError(400, str(exc)) from exc

        if not abs_path.exists():
            raise ApiError(404, f"File not found: {normalized_rel_path}")
        if not abs_path.is_file():
            raise ApiError(400, "Path must be a file")

        return abs_path

    def path_stage(self, rel_path: str) -> str:
        normalized = normalize_rel_path(rel_path)
        if is_done(self.base_dir, normalized):
            return "done"
        if is_working(self.base_dir, normalized):
            return "working"
        return "browse"

    def api_to_working(self, rel_path: str) -> dict[str, object]:
        normalized = self._normalize_rel_path_or_400(rel_path)
        self._require_existing_library_file(normalized)
        before_stage = self.path_stage(normalized)
        changed = set_working_path(self.base_dir, normalized)
        changed = clear_done_path(self.base_dir, normalized) or changed
        changed = (pop_bumped_path(self.base_dir, normalized) is not None) or changed
        if changed:
            self.rebuild_for_stage_transition(normalized, before_stage, "working")
        return {"changed": changed, "path": normalized, "stage": "working"}

    def api_to_done(self, rel_path: str) -> dict[str, object]:
        normalized = self._normalize_rel_path_or_400(rel_path)
        self._require_existing_library_file(normalized)
        before_stage = self.path_stage(normalized)
        changed = set_done_path(self.base_dir, normalized)
        changed = (pop_working_path(self.base_dir, normalized) is not None) or changed
        changed = (pop_bumped_path(self.base_dir, normalized) is not None) or changed
        if changed:
            self.rebuild_for_stage_transition(normalized, before_stage, "done")
        return {"changed": changed, "path": normalized, "stage": "done"}

    def api_to_browse(self, rel_path: str) -> dict[str, object]:
        normalized = self._normalize_rel_path_or_400(rel_path)
        self._require_existing_library_file(normalized)
        before_stage = self.path_stage(normalized)
        changed = (pop_working_path(self.base_dir, normalized) is not None)
        changed = clear_done_path(self.base_dir, normalized) or changed
        changed = (pop_bumped_path(self.base_dir, normalized) is not None) or changed
        if changed:
            self.rebuild_for_stage_transition(normalized, before_stage, "browse")
        return {"changed": changed, "path": normalized, "stage": "browse"}

    def api_reopen(self, rel_path: str) -> dict[str, object]:
        result = self.api_to_working(rel_path)
        result["transition"] = "reopen"
        return result

    def api_bump(self, rel_path: str) -> dict[str, object]:
        normalized = self._normalize_rel_path_or_400(rel_path)
        abs_path = self._require_existing_library_file(normalized)
        if self.path_stage(normalized) != "browse":
            raise ApiError(409, f"Bump is only allowed in browse stage: {normalized}")
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
        self.rebuild_for_path(normalized, rebuild_working=False, rebuild_done=False)
        return {"path": normalized, "bumped_mtime": bumped_mtime}

    def api_unbump(self, rel_path: str) -> dict[str, object]:
        normalized = self._normalize_rel_path_or_400(rel_path)
        self._require_existing_library_file(normalized)
        entry = pop_bumped_path(self.base_dir, normalized)
        if entry is None:
            raise ApiError(409, f"Path is not bumped: {normalized}")

        original_mtime = float(entry.get("original_mtime", time.time()))
        self.rebuild_for_path(normalized, rebuild_working=False, rebuild_done=False)
        return {"path": normalized, "restored_mtime": original_mtime}

    def api_delete(self, rel_path: str) -> dict[str, object]:
        normalized = self._normalize_rel_path_or_400(rel_path)
        abs_path = self._require_existing_library_file(normalized)
        before_stage = self.path_stage(normalized)
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

        removed_done = clear_done_path(self.base_dir, normalized)
        removed_working = pop_working_path(self.base_dir, normalized) is not None
        pop_bumped_path(self.base_dir, normalized)

        if sibling_md_rel:
            clear_done_path(self.base_dir, sibling_md_rel)
            pop_working_path(self.base_dir, sibling_md_rel)
            pop_bumped_path(self.base_dir, sibling_md_rel)

        self.rebuild_for_path(
            normalized,
            rebuild_browse=True,
            rebuild_working=(before_stage == "working") or removed_working,
            rebuild_done=(before_stage == "done") or removed_done,
        )
        return {
            "path": normalized,
            "deleted_md": deleted_md,
            "removed_done": removed_done,
            "removed_working": removed_working,
            "redirect": _browse_parent_url_for_rel_path(normalized),
        }

    def _resolve_rebuild_targets(self, rel_path: str) -> tuple[str, Path, str, Path]:
        normalized = self._normalize_rel_path_or_400(rel_path)
        abs_path = self._require_existing_library_file(normalized)
        suffix = abs_path.suffix.lower()

        if suffix in {".html", ".htm"}:
            html_rel = normalized
            html_abs = abs_path
            md_abs = abs_path.with_suffix(".md")
            md_rel = normalize_rel_path(str(Path(normalized).with_suffix(".md")))
        elif suffix == ".md":
            md_rel = normalized
            md_abs = abs_path
            html_abs = abs_path.with_suffix(".html")
            html_rel = normalize_rel_path(str(Path(normalized).with_suffix(".html")))
        else:
            raise ApiError(400, "Rebuild is only supported for .md/.html files")

        if not md_abs.is_file():
            raise ApiError(404, f"Associated Markdown file not found: {md_rel}")

        return md_rel, md_abs, html_rel, html_abs

    def api_rebuild_file(self, rel_path: str) -> dict[str, object]:
        md_rel, md_abs, html_rel, html_abs = self._resolve_rebuild_targets(rel_path)
        stage = self.path_stage(html_rel)

        try:
            md_text = md_abs.read_text(encoding="utf-8", errors="replace")
            full_html = markdown_to_html(md_text, title=md_abs.stem)
            html_abs.write_text(full_html, encoding="utf-8")

            html_abs_resolved = html_abs.resolve()
            add_margins_to_html_files(
                html_abs.parent,
                file_filter=lambda candidate: candidate.resolve() == html_abs_resolved,
            )
        except Exception as exc:
            raise ApiError(500, f"Could not rebuild HTML from Markdown: {exc}") from exc

        self.rebuild_for_path(
            html_rel,
            rebuild_browse=(stage == "browse"),
            rebuild_working=(stage == "working"),
            rebuild_done=(stage == "done"),
        )
        return {"rebuilt": True, "path": html_rel, "markdown": md_rel}

    def api_rebuild(self) -> dict[str, object]:
        self.rebuild()
        return {"rebuilt": True}

    def api_get_highlights(self, rel_path: str) -> dict[str, object]:
        normalized = self._normalize_rel_path_or_400(rel_path)
        self._require_existing_library_file(normalized)
        return load_highlights_for_path(self.base_dir, normalized)

    def api_put_highlights(self, rel_path: str, payload: dict[str, object]) -> dict[str, object]:
        normalized = self._normalize_rel_path_or_400(rel_path)
        self._require_existing_library_file(normalized)
        stage = self.path_stage(normalized)
        saved = save_highlights_for_path(self.base_dir, normalized, payload)
        self.rebuild_for_path(
            normalized,
            rebuild_browse=(stage == "browse"),
            rebuild_working=(stage == "working"),
            rebuild_done=(stage == "done"),
        )
        return saved

    def handle_api(self, action: str, payload: dict[str, object]) -> dict[str, object]:
        action_name = action.strip("/")
        if action_name == "rebuild":
            return self.api_rebuild()

        raw_path = payload.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ApiError(400, "Field 'path' is required")

        method_name = self._PATH_ACTION_METHODS.get(action_name)
        if method_name is None:
            raise ApiError(404, f"Unknown API action: {action_name}")
        method = getattr(self, method_name)
        return method(raw_path)

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
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  padding: 8px;
  border: 1px solid #cfcfcf;
  border-radius: 10px;
  background: #ffffff;
  box-shadow: 0 4px 16px rgba(0,0,0,0.15);
  font: 12px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;
}
#dg-overlay .dg-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
#dg-overlay .dg-row-status {
  justify-content: flex-start;
}
#dg-overlay .dg-row-highlights {
  justify-content: flex-start;
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
#dg-overlay .dg-link {
  display: inline-flex;
  align-items: center;
  padding: 4px 8px;
  border: 1px solid #bfbfbf;
  border-radius: 6px;
  background: #fafafa;
  color: #333;
  text-decoration: none;
}
#dg-overlay .dg-row-status .dg-link,
#dg-overlay .dg-row-highlights button {
  border: 0;
  background: #f3f3f3;
  box-shadow: 0 1px 4px rgba(0,0,0,0.12);
}
#dg-overlay .dg-hl-nav {
  display: none;
  align-items: center;
  gap: 6px;
}
#dg-overlay .dg-hl-nav.is-visible {
  display: inline-flex;
}
#dg-overlay .dg-hl-label {
  color: #333;
  white-space: nowrap;
}
#dg-overlay .dg-hl-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 56px;
  padding: 4px 8px;
  border-radius: 6px;
  background: #f0f0f0;
  color: #444;
  font-variant-numeric: tabular-nums;
}
#dg-overlay .dg-hl-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  min-width: 30px;
  padding: 4px 0;
  line-height: 1;
}
#dg-overlay .dg-hl-icon {
  width: 14px;
  height: 14px;
  display: block;
  stroke: #333;
  fill: none;
  stroke-width: 2.1;
  stroke-linecap: round;
  stroke-linejoin: round;
  pointer-events: none;
}
""".strip()


OVERLAY_JS = """
(function() {
  const script = document.currentScript;
  const relPath = script.getAttribute('data-path') || '';
  if (!relPath) return;

  window.addEventListener('pageshow', (event) => {
    let navType = '';
    try {
      const entries = performance.getEntriesByType('navigation');
      if (entries && entries.length > 0) navType = entries[0].type || '';
    } catch (error) {}
    if (event.persisted || navType === 'back_forward') {
      window.location.reload();
    }
  });

  let stage = script.getAttribute('data-stage') || 'browse';
  let bumped = script.getAttribute('data-bumped') === '1';
  const browseIndexUrl = script.getAttribute('data-browse-url') || '/browse/';
  let busy = false;
  let highlightBusy = false;
  let highlightProgress = { current: 0, total: 0, label: '0 / 0' };
  let highlightProgressListenerAttached = false;
  let hashListenerAttached = false;
  let highlightRefreshTimer = 0;

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
        if (action === 'to-working' || action === 'reopen') stage = 'working';
        if (action === 'to-done') stage = 'done';
        if (action === 'to-browse') {
          stage = 'browse';
          bumped = false;
        }
        if (action === 'to-working' || action === 'to-done' || action === 'reopen') {
          bumped = false;
        }
        if (action === 'bump') bumped = true;
        if (action === 'unbump') bumped = false;
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

  function currentIndexUrl() {
    if (stage === 'working') return '/working/';
    if (stage === 'done') return '/done/';
    return browseIndexUrl;
  }

  function currentInsideLabel() {
    if (stage === 'working') return 'Inside Working';
    if (stage === 'done') return 'Inside Done';
    return 'Inside Browse';
  }

  function withRefreshParam(url) {
    try {
      const target = new URL(url, window.location.origin);
      target.searchParams.set('_r', String(Date.now()));
      return `${target.pathname}${target.search}${target.hash}`;
    } catch (error) {
      return url;
    }
  }

  function makeInsideLink() {
    const link = document.createElement('a');
    link.className = 'dg-link';
    link.textContent = currentInsideLabel();
    link.href = withRefreshParam(currentIndexUrl());
    return link;
  }

  function makeChevronIcon(direction) {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 16 16');
    svg.setAttribute('aria-hidden', 'true');
    svg.classList.add('dg-hl-icon');
    const path = document.createElementNS(ns, 'path');
    path.setAttribute('d', direction === 'up' ? 'M3.5 10.5L8 6l4.5 4.5' : 'M3.5 5.5L8 10l4.5-4.5');
    svg.appendChild(path);
    return svg;
  }

  function hasHighlightApi() {
    const api = window.ArticleJS;
    return !!(
      api
      && typeof api.getHighlightProgress === 'function'
      && typeof api.nextHighlight === 'function'
      && typeof api.previousHighlight === 'function'
    );
  }

  function normalizeHighlightProgress(progress) {
    let total = Number(progress && progress.total);
    let current = Number(progress && progress.current);
    if (!Number.isFinite(total) || total < 0) total = 0;
    if (!Number.isFinite(current) || current < 0) current = 0;
    if (total === 0) current = 0;
    if (current > total) current = total;
    return {
      current,
      total,
      label: `${current} / ${total}`
    };
  }

  async function refreshHighlightProgress() {
    if (!hasHighlightApi()) {
      highlightProgress = normalizeHighlightProgress(null);
      render();
      return;
    }
    try {
      highlightProgress = normalizeHighlightProgress(await window.ArticleJS.getHighlightProgress());
    } catch (error) {
      highlightProgress = normalizeHighlightProgress(null);
    }
    render();
  }

  function scheduleHighlightProgressRefresh(delayMs) {
    const delay = Number.isFinite(Number(delayMs)) ? Math.max(0, Number(delayMs)) : 0;
    if (highlightRefreshTimer) {
      window.clearTimeout(highlightRefreshTimer);
      highlightRefreshTimer = 0;
    }
    highlightRefreshTimer = window.setTimeout(() => {
      highlightRefreshTimer = 0;
      refreshHighlightProgress();
    }, delay);
  }

  async function moveHighlight(direction) {
    if (busy || highlightBusy || !hasHighlightApi()) return;
    highlightBusy = true;
    render();
    try {
      const api = window.ArticleJS;
      let result;
      if (direction < 0) {
        result = await api.previousHighlight();
      } else {
        result = await api.nextHighlight();
      }
      if (result && result.progress) {
        highlightProgress = normalizeHighlightProgress(result.progress);
      } else {
        highlightProgress = normalizeHighlightProgress(await api.getHighlightProgress());
      }
    } catch (error) {}
    highlightBusy = false;
    render();
  }

  function makeHighlightNav() {
    const nav = document.createElement('div');
    const visible = highlightProgress.total > 0;
    nav.className = `dg-hl-nav${visible ? ' is-visible' : ''}`;
    nav.setAttribute('aria-hidden', visible ? 'false' : 'true');

    const label = document.createElement('span');
    label.className = 'dg-hl-label';
    label.textContent = 'Jump to highlight:';
    nav.appendChild(label);

    const count = document.createElement('span');
    count.className = 'dg-hl-count';
    count.textContent = highlightProgress.label;
    nav.appendChild(count);

    const prevBtn = document.createElement('button');
    prevBtn.type = 'button';
    prevBtn.className = 'dg-hl-btn';
    prevBtn.appendChild(makeChevronIcon('up'));
    prevBtn.setAttribute('aria-label', 'Previous highlight');
    prevBtn.title = 'Previous highlight';
    prevBtn.addEventListener('click', () => { moveHighlight(-1); });
    nav.appendChild(prevBtn);

    const nextBtn = document.createElement('button');
    nextBtn.type = 'button';
    nextBtn.className = 'dg-hl-btn';
    nextBtn.appendChild(makeChevronIcon('down'));
    nextBtn.setAttribute('aria-label', 'Next highlight');
    nextBtn.title = 'Next highlight';
    nextBtn.addEventListener('click', () => { moveHighlight(1); });
    nav.appendChild(nextBtn);

    if (!visible || busy || highlightBusy || !hasHighlightApi()) {
      prevBtn.setAttribute('disabled', '');
      nextBtn.setAttribute('disabled', '');
    }

    return { node: nav, visible };
  }

  function stageActions() {
    if (stage === 'working') {
      return [
        ['Back to Browse', 'to-browse'],
        ['Move to Done', 'to-done']
      ];
    }
    if (stage === 'done') {
      return [
        ['Reopen to Working', 'reopen']
      ];
    }
    return [
      ['Move to Working', 'to-working'],
      [bumped ? 'Unbump' : 'Bump', bumped ? 'unbump' : 'bump']
    ];
  }

  function render() {
    bar.innerHTML = '';
    const statusRow = document.createElement('div');
    statusRow.className = 'dg-row dg-row-status';
    statusRow.appendChild(makeInsideLink());
    bar.appendChild(statusRow);

    const actionsRow = document.createElement('div');
    actionsRow.className = 'dg-row dg-row-actions';
    for (const [label, action] of stageActions()) {
      actionsRow.appendChild(makeButton(label, action));
    }
    if (stage === 'browse') {
      actionsRow.appendChild(makeButton('Rebuild', 'rebuild-file'));
      actionsRow.appendChild(makeButton('Delete', 'delete'));
    }
    bar.appendChild(actionsRow);

    const navControl = makeHighlightNav();
    const highlightsRow = document.createElement('div');
    highlightsRow.className = 'dg-row dg-row-highlights';
    if (navControl.visible) {
      highlightsRow.appendChild(navControl.node);
      bar.appendChild(highlightsRow);
    }

    if (busy) {
      for (const btn of bar.querySelectorAll('button')) btn.setAttribute('disabled', '');
    }
  }

  const bar = document.createElement('div');
  bar.id = 'dg-overlay';

  function onHighlightProgress(event) {
    highlightProgress = normalizeHighlightProgress(event && event.detail ? event.detail : null);
    render();
  }

  function onHashChange() {
    // Deep links can target a specific highlight id (#hl=...).
    // Refresh shortly after hash changes to reflect the focused index.
    scheduleHighlightProgressRefresh(60);
  }

  function mount() {
    if (!document.body) return;
    if (!bar.isConnected) document.body.appendChild(bar);
    if (!highlightProgressListenerAttached) {
      document.addEventListener('articlejs:highlight-progress', onHighlightProgress);
      highlightProgressListenerAttached = true;
    }
    if (!hashListenerAttached && window && window.addEventListener) {
      window.addEventListener('hashchange', onHashChange, { passive: true });
      hashListenerAttached = true;
    }
    render();
    refreshHighlightProgress();
    // Re-sync once highlights finish hydration/focus on load.
    scheduleHighlightProgressRefresh(180);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }
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


def _inject_html_overlay(*, html_text: str, rel_path: str, stage: str, bumped: bool) -> bytes:
    html_text = _ensure_viewport_meta(html_text)
    path_attr = html.escape(rel_path, quote=True)
    browse_url_attr = html.escape(_browse_parent_url_for_rel_path(rel_path), quote=True)
    article_js = ""
    if "/working/article.js" not in html_text:
        article_js = f"<script defer src=\"/working/article.js\" data-docflow-path=\"{path_attr}\"></script>"
    tags = (
        article_js
        + f"<style>{OVERLAY_CSS}</style>"
        + f"<script defer data-path=\"{path_attr}\" data-stage=\"{html.escape(stage, quote=True)}\" "
        + f"data-bumped=\"{'1' if bumped else '0'}\" data-browse-url=\"{browse_url_attr}\">{OVERLAY_JS}</script>"
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

    stage = app.path_stage(rel_path)
    bumped = get_bumped_entry(app.base_dir, rel_path) is not None
    payload = _inject_html_overlay(html_text=text, rel_path=rel_path, stage=stage, bumped=bumped)

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
                    self.send_header("Location", _browse_index_url_for_raw_library_path(path))
                    self.end_headers()
                    return
                _send_json(self, 404, {"ok": False, "error": "Raw file not found"})
                return

            if path in ("/browse", "/working", "/done"):
                self.send_response(302)
                self.send_header("Location", path + "/")
                self.end_headers()
                return

            if path == "/read" or path.startswith("/read/"):
                _send_json(self, 404, {"ok": False, "error": "Not found"})
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
    parser.add_argument("--port", type=int, default=int(os.getenv("DOCFLOW_PORT", "8080")))
    parser.add_argument("--bump-years", type=int, default=int(os.getenv("DOCFLOW_BUMP_YEARS", "100")))
    parser.set_defaults(rebuild_on_start=False)
    parser.add_argument(
        "--rebuild-on-start",
        dest="rebuild_on_start",
        action="store_true",
        help="Rebuild browse/working/done static pages before serving.",
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
