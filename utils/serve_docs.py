#!/usr/bin/env python3
"""
Local HTML/PDF server with "bump" from the viewed page.

- Index ordered by mtime desc and highlighting bumped files (🔥 + background).
- Overlay on .html pages to Bump/Unbump the open file.
- No buttons in the index.
- Overlay CSS/JS served as external files (avoids CSP blocks).
- "Bump" mirrors the AppleScript:
    baseEpoch = /bin/date -v+{BUMP_YEARS}y +%s
    mtime := baseEpoch + i (i starts at 1 and increases per session bump)
- "Smart" button: only Bump or Unbump depending on mtime > now.
- Shortcuts: b / u / l and ⌘B / ⌘U (or Ctrl+B / Ctrl+U).
  · 'l' navigates to the listing (parent folder) of the current file.
- Bump and publish are independent states; you can (un)bump even if published.

Environment variables:
  PORT        (default 8000)
  SERVE_DIR   (default "/Users/domingo/⭐️ Documentación")
  BUMP_YEARS  (default 100)
"""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
import re
import time
import html
import urllib.parse
from datetime import datetime
import subprocess
import calendar as _cal
import stat
from typing import Optional

# Paths relative to the repo (for publishing).
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
_DEFAULT_PUBLISH_SCRIPT = os.path.join(REPO_ROOT, "bin", "publish_web.sh")
_DEFAULT_DEPLOY_SCRIPT = os.path.join(REPO_ROOT, "web", "deploy.sh")
DEPLOY_SCRIPT = os.getenv("DEPLOY_SCRIPT")
if not DEPLOY_SCRIPT:
    if os.path.isfile(_DEFAULT_PUBLISH_SCRIPT) and os.access(_DEFAULT_PUBLISH_SCRIPT, os.X_OK):
        DEPLOY_SCRIPT = _DEFAULT_PUBLISH_SCRIPT
    else:
        DEPLOY_SCRIPT = _DEFAULT_DEPLOY_SCRIPT
PUBLIC_READS_DIR = os.getenv(
    "PUBLIC_READS_DIR",
    os.path.join(REPO_ROOT, "web", "public", "read"),
)
STATIC_DIR = os.path.join(SCRIPT_DIR, "static")

# --------- CONFIG ---------
PORT = int(os.getenv("PORT", "8000"))
SERVE_DIR = os.getenv("SERVE_DIR", "/Users/domingo/⭐️ Documentación")
BUMP_YEARS = int(os.getenv("BUMP_YEARS", "100"))
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
YEAR_PATTERN = re.compile(r"(\d{4})$")
 

# Session counter (equivalent to the AppleScript "counter" in a run).
_BUMP_COUNTER = 0
_LAST_BASE_EPOCH: Optional[int] = None  # remembers the last base to reset the counter


# --------- STATIC ASSETS (external) ---------

def _load_static_bytes(filename: str) -> bytes:
    path = os.path.join(STATIC_DIR, filename)
    with open(path, "rb") as fh:
        return fh.read()


OVERLAY_CSS = _load_static_bytes("overlay.css")
OVERLAY_JS = _load_static_bytes("overlay.js")
INDEX_JS = _load_static_bytes("index.js")
HIGHLIGHTS_JS = _load_static_bytes("highlights.js")


# --------- HELPERS ---------
def safe_join(rel_path: str) -> str | None:
    """Ensure the target path stays within SERVE_DIR (avoid path traversal)."""
    rel_path = rel_path.lstrip("/")
    base = os.path.normpath(SERVE_DIR)
    target = os.path.normpath(os.path.join(base, rel_path))
    if target == base or target.startswith(base + os.sep):
        return target
    return None


def _extract_year_from_path(abs_path: str) -> int | None:
    parts = abs_path.split(os.sep)
    for part in reversed(parts):
        match = YEAR_PATTERN.search(part)
        if not match:
            continue
        try:
            return int(match.group(1))
        except ValueError:
            continue
    return None


def _find_highlight_json(abs_html_path: str) -> str | None:
    name = os.path.basename(abs_html_path)
    if not name:
        return None
    posts_root = os.path.join(SERVE_DIR, "Posts")
    year = _extract_year_from_path(abs_html_path)
    if year:
        for encoded in _highlight_name_candidates(name):
            candidate = os.path.join(posts_root, f"Posts {year}", "highlights", f"{encoded}.json")
            if os.path.isfile(candidate):
                return candidate
    if not os.path.isdir(posts_root):
        return None
    years: list[int] = []
    try:
        for entry in os.listdir(posts_root):
            match = YEAR_PATTERN.search(entry)
            if not match:
                continue
            try:
                years.append(int(match.group(1)))
            except ValueError:
                continue
    except Exception:
        return None
    for year in sorted(set(years), reverse=True):
        for encoded in _highlight_name_candidates(name):
            candidate = os.path.join(posts_root, f"Posts {year}", "highlights", f"{encoded}.json")
            if os.path.isfile(candidate):
                return candidate
    return None


def is_bumped(ts: float) -> bool:
    return ts > time.time()


def fmt_ts(ts: float) -> str:
    """Format like /read/: YYYY-Mon-DD HH:MM (English month abbreviation)."""
    t = time.localtime(ts)
    return f"{t.tm_year}-{MONTHS[t.tm_mon-1]}-{t.tm_mday:02d} {t.tm_hour:02d}:{t.tm_min:02d}"


def _is_visible_filename(name: str) -> bool:
    lowered = name.lower()
    return lowered.endswith((".html", ".htm", ".pdf"))


def _highlight_name_candidates(name: str) -> list[str]:
    candidates = [
        urllib.parse.quote(name),
        urllib.parse.quote(name, safe="~!*()'"),
    ]
    deduped: list[str] = []
    seen = set()
    for item in candidates:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _dir_has_visible_entries(path: str, cache: dict[str, bool]) -> bool:
    cached = cache.get(path)
    if cached is not None:
        return cached
    try:
        with os.scandir(path) as it:
            for entry in it:
                name = entry.name
                if name.startswith("."):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if _dir_has_visible_entries(entry.path, cache):
                            cache[path] = True
                            return True
                    else:
                        if _is_visible_filename(name):
                            cache[path] = True
                            return True
                except OSError:
                    continue
    except OSError:
        cache[path] = True
        return True
    cache[path] = False
    return False


def _entry_classes(bumped: bool, published: bool, highlighted: bool) -> str:
    classes: list[str] = []
    if bumped:
        classes.append("dg-bump")
    if published:
        classes.append("dg-pub")
    if highlighted:
        classes.append("dg-hl")
    return f" class=\"{' '.join(classes)}\"" if classes else ""


def _is_published_filename(name: str) -> bool:
    try:
        if name.lower().endswith((".html", ".htm", ".pdf")):
            return os.path.exists(os.path.join(PUBLIC_READS_DIR, name))
    except Exception:
        return False
    return False


def _pdf_actions_html(rel_from_root: str, bumped: bool, published: bool) -> str:
    actions: list[str] = []
    if bumped:
        actions.append(
            f"<a href='#' class='dg-act' data-dg-act='unbump_now' data-dg-path='{html.escape(rel_from_root)}'>Unbump</a>"
        )
    else:
        actions.append(
            f"<a href='#' class='dg-act' data-dg-act='bump' data-dg-path='{html.escape(rel_from_root)}'>Bump</a>"
        )
    if published:
        actions.append(
            f"<a href='#' class='dg-act' data-dg-act='unpublish' data-dg-path='{html.escape(rel_from_root)}'>Unpublish</a>"
        )
    else:
        actions.append(
            f"<a href='#' class='dg-act' data-dg-act='publish' data-dg-path='{html.escape(rel_from_root)}'>Publish</a>"
        )
    if not actions:
        return ""
    return f"<span class='dg-actions'>{' '.join(actions)}</span>"


def _render_list_entry(entry: os.DirEntry[str], now: float, st: os.stat_result) -> str | None:
    mtime = st.st_mtime
    bumped = mtime > now
    published = _is_published_filename(entry.name)
    is_dir = stat.S_ISDIR(st.st_mode)
    display_name = entry.name + ("/" if is_dir else "")
    link = urllib.parse.quote(display_name)
    rel_from_root = os.path.relpath(entry.path, SERVE_DIR)
    type_icon = ""
    highlighted = False
    if not is_dir:
        lowered = entry.name.lower()
        if lowered.endswith((".html", ".htm")):
            type_icon = "📄 "
            highlighted = _find_highlight_json(entry.path) is not None
        elif lowered.endswith(".pdf"):
            type_icon = "📕 "
        else:
            return None  # ignore files that are not HTML/PDF

    prefix = ("🔥 " if bumped else "") + ("🟢 " if published else "") + ("🟡 " if highlighted else "") + type_icon
    date_html = f"<span class='dg-date'> — {fmt_ts(mtime)}</span>"
    actions_html = ""
    if entry.name.lower().endswith(".pdf"):
        actions_html = _pdf_actions_html(rel_from_root, bumped, published)
    cls_attr = _entry_classes(bumped, published, highlighted)
    return f"<li{cls_attr}><span>{prefix}<a href=\"{link}\">{html.escape(display_name)}</a>{date_html}</span>{actions_html}</li>"


def _apple_like_base_epoch() -> int:
    """Epoch for (now + BUMP_YEARS years), mirroring `/bin/date -v+{BUMP_YEARS}y +%s`."""
    try:
        cmd = ["/bin/date", f"-v+{BUMP_YEARS}y", "+%s"]
        out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()
        return int(out)
    except Exception:
        # Fallback: add years respecting the calendar.
        now = datetime.now()
        tgt_year = now.year + BUMP_YEARS
        y, m, d = tgt_year, now.month, now.day
        last_day = _cal.monthrange(y, m)[1]
        if d > last_day:
            d = last_day
        dt2 = datetime(y, m, d, now.hour, now.minute, now.second, now.microsecond)
        return int(time.mktime(dt2.timetuple()))


def base_epoch_cached() -> int:
    """Get the future base (now + BUMP_YEARS years).

    Previously cached for the whole session, but now recomputed on each access
    so bumps always start from the current moment.
    """
    return _apple_like_base_epoch()


def get_creation_epoch(abs_path: str) -> int | None:
    """Try to get creation time (APFS/Spotlight)."""
    try:
        st = os.stat(abs_path)
        birth = getattr(st, "st_birthtime", None)
        if birth and birth > 0:
            return int(birth)
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["/usr/bin/mdls", "-raw", "-name", "kMDItemFSCreationDate", abs_path],
            check=True, capture_output=True, text=True
        ).stdout.strip()
        if out and out.lower() != "(null)":
            try:
                dt = datetime.strptime(out, "%Y-%m-%d %H:%M:%S %z")
                return int(dt.timestamp())
            except Exception:
                for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
                    try:
                        dt = datetime.strptime(out, fmt)
                        if dt.tzinfo is None:
                            return int(time.mktime(dt.timetuple()))
                        return int(dt.timestamp())
                    except Exception:
                        continue
    except Exception:
        pass
    return None


def compute_bump_mtime() -> int:
    """Compute the future mtime by adding years relative to the bump moment."""
    global _BUMP_COUNTER, _LAST_BASE_EPOCH
    base_epoch = base_epoch_cached()
    if base_epoch != _LAST_BASE_EPOCH:
        _LAST_BASE_EPOCH = base_epoch
        _BUMP_COUNTER = 0
    _BUMP_COUNTER += 1
    return base_epoch + _BUMP_COUNTER


 


def inject_overlay(html_text: str, rel_fs: str, bumped: bool, published: bool) -> bytes:
    tags = (
        '<link rel="stylesheet" href="/__overlay.css">'
        f'<script src="/__highlights.js" defer data-path="{html.escape(rel_fs)}"></script>'
        f'<script src="/__overlay.js" defer data-path="{html.escape(rel_fs)}" '
        f'data-bumped="{"1" if bumped else "0"}" '
        f' data-published="{"1" if published else "0"}"></script>'
    )
    low = html_text.lower()
    idx = low.rfind("</body>")
    injected = (html_text + tags) if idx == -1 else (html_text[:idx] + tags + html_text[idx:])
    return injected.encode("utf-8", "surrogateescape")


# --------- REQUEST HANDLER ---------
class HTMLOnlyRequestHandler(SimpleHTTPRequestHandler):
    def _send_bytes(self, data: bytes, content_type: str, extra_headers: dict | None = None):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    # --------- ROUTES ----------
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/__bump":
            self.send_error(404, "Unknown POST")
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", "surrogateescape")
        data = urllib.parse.parse_qs(body)
        rel = urllib.parse.unquote(data.get("path", [""])[0])
        action = data.get("action", ["bump"])[0]
        abs_path = safe_join(rel)
        if not abs_path or not os.path.exists(abs_path):
            self.send_error(404, "File not found")
            return

        try:
            if action in ("bump", "unbump_now"):
                st = os.stat(abs_path)
                atime = st.st_atime  # preserve atime

                if action == "bump":
                    mtime = compute_bump_mtime()
                else:  # unbump_now
                    cre = get_creation_epoch(abs_path)
                    if cre is not None:
                        mtime = cre
                    else:
                        mtime = st.st_mtime if st.st_mtime <= time.time() else time.time() - 60

                os.utime(abs_path, (atime, mtime))
                md_path = os.path.splitext(abs_path)[0] + ".md"
                if os.path.isfile(md_path):
                    try:
                        md_stat = os.stat(md_path)
                        os.utime(md_path, (md_stat.st_atime, mtime))
                    except Exception:
                        pass
                self._send_bytes(b'{"ok":true}', "application/json; charset=utf-8")
                return

            if action == "delete":
                if os.path.isdir(abs_path):
                    self.send_error(400, "Directories cannot be deleted")
                    return
                try:
                    os.remove(abs_path)
                except FileNotFoundError:
                    self.send_error(404, "File not found")
                    return
                except Exception as e:
                    self.send_error(500, f"Could not delete: {e}")
                    return

                # Delete associated Markdown (same name).
                try:
                    stem, _ = os.path.splitext(abs_path)
                    md_path = f"{stem}.md"
                    if os.path.isfile(md_path):
                        os.remove(md_path)
                except Exception as e:
                    self.send_error(500, f"Could not delete associated Markdown: {e}")
                    return

                # Also remove the published copy if it exists.
                try:
                    pub_path = os.path.join(PUBLIC_READS_DIR, os.path.basename(abs_path))
                    if os.path.isfile(pub_path):
                        os.remove(pub_path)
                except Exception as e:
                    self.send_error(500, f"Could not delete public copy: {e}")
                    return

                self._send_bytes(b'{"ok":true}', "application/json; charset=utf-8")
                return

            if action == "publish":
                try:
                    st_src = os.stat(abs_path)
                except Exception as e:
                    self.send_error(500, f"Could not read file: {e}")
                    return
                # 1) Always copy to the public READS directory.
                if not os.path.isdir(PUBLIC_READS_DIR):
                    try:
                        os.makedirs(PUBLIC_READS_DIR, exist_ok=True)
                    except Exception as e:
                        self.send_error(500, f"Could not create destination: {e}")
                        return
                dst_dir = PUBLIC_READS_DIR
                try:
                    os.makedirs(dst_dir, exist_ok=True)
                except Exception as e:
                    self.send_error(500, f"Could not create destination: {e}")
                    return

                dst_path = os.path.join(dst_dir, os.path.basename(abs_path))
                try:
                    src_stat = st_src
                    name_low = os.path.basename(abs_path).lower()
                    if name_low.endswith((".html", ".htm")):
                        # Inject the base article script before </head> if missing.
                        with open(abs_path, 'r', encoding='utf-8', errors='ignore') as src:
                            text = src.read()
                        if "/read/article.js" not in text:
                            low = text.lower()
                            idx = low.rfind("</head>")
                            if idx != -1:
                                text = text[:idx] + "<script src='/read/article.js' defer></script>" + text[idx:]
                        with open(dst_path, 'w', encoding='utf-8') as dst:
                            dst.write(text)
                    else:
                        # Binary copy for other types (e.g., PDFs).
                        with open(abs_path, 'rb') as src, open(dst_path, 'wb') as dst:
                            while True:
                                chunk = src.read(1024 * 1024)
                                if not chunk:
                                    break
                                dst.write(chunk)
                    # Preserve atime and set public copy mtime to publish time.
                    try:
                        target_mtime = int(time.time())
                        os.utime(dst_path, (src_stat.st_atime, target_mtime))
                    except Exception:
                        pass
                except Exception as e:
                    self.send_error(500, f"Error copying: {e}")
                    return

                # 2) Trigger deploy.
                if not os.path.isfile(DEPLOY_SCRIPT) or not os.access(DEPLOY_SCRIPT, os.X_OK):
                    self.send_error(500, f"Deploy not available: {DEPLOY_SCRIPT}")
                    return

                try:
                    # inherit environment (requires REMOTE_USER/REMOTE_HOST configured)
                    subprocess.run([DEPLOY_SCRIPT], check=True)
                except subprocess.CalledProcessError as e:
                    self.send_error(500, f"Deploy failed ({e.returncode})")
                    return

                self._send_bytes(b'{"ok":true}', "application/json; charset=utf-8")
                return

            if action == "unpublish":
                # Remove the file from the public READS directory and deploy.
                removed = False
                try:
                    dst_path = os.path.join(PUBLIC_READS_DIR, os.path.basename(abs_path))
                    if os.path.exists(dst_path):
                        os.remove(dst_path)
                        removed = True
                except Exception as e:
                    self.send_error(500, f"Error unpublishing: {e}")
                    return

                # Trigger deploy.
                if not os.path.isfile(DEPLOY_SCRIPT) or not os.access(DEPLOY_SCRIPT, os.X_OK):
                    self.send_error(500, f"Deploy not available: {DEPLOY_SCRIPT}")
                    return
                try:
                    subprocess.run([DEPLOY_SCRIPT], check=True)
                except subprocess.CalledProcessError as e:
                    self.send_error(500, f"Deploy failed ({e.returncode})")
                    return

                self._send_bytes(b'{"ok":true}', "application/json; charset=utf-8")
                return

            self.send_error(400, "Unknown action")
        except OSError as e:
            self.send_error(500, str(e))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        # Overlay assets (external to avoid inline CSP).
        if parsed.path == "/__overlay.css":
            return self._send_bytes(OVERLAY_CSS, "text/css; charset=utf-8")

        if parsed.path == "/__overlay.js":
            return self._send_bytes(OVERLAY_JS, "application/javascript; charset=utf-8")
        if parsed.path == "/__index.js":
            return self._send_bytes(INDEX_JS, "application/javascript; charset=utf-8")
        if parsed.path == "/__highlights.js":
            return self._send_bytes(HIGHLIGHTS_JS, "application/javascript; charset=utf-8")
        if parsed.path == "/__highlights":
            qs = urllib.parse.parse_qs(parsed.query)
            rel = qs.get("path", [""])[0]
            if not rel:
                self.send_error(400, "Missing path")
                return
            rel = urllib.parse.unquote(rel)
            abs_path = safe_join(rel)
            if not abs_path or not os.path.isfile(abs_path):
                self.send_error(404, "File not found")
                return
            highlights_path = _find_highlight_json(abs_path)
            if not highlights_path or not os.path.isfile(highlights_path):
                self.send_error(404, "Highlights not found")
                return
            try:
                with open(highlights_path, "rb") as fh:
                    data = fh.read()
            except OSError:
                self.send_error(500, "Could not read highlights")
                return
            return self._send_bytes(data, "application/json; charset=utf-8", {"Cache-Control": "no-store"})

        # HTML pages: inject overlay.
        rel_path = parsed.path.lstrip("/")

        if rel_path and rel_path.lower().endswith(".html"):
            rel_fs = urllib.parse.unquote(rel_path)
            abs_path = safe_join(rel_fs)
            if abs_path and os.path.exists(abs_path):
                try:
                    with open(abs_path, "rb") as f:
                        original = f.read()
                    text = original.decode("utf-8", "surrogateescape")
                except Exception:
                    return super().do_GET()

                st = os.stat(abs_path)
                # Published if a file with the same name already exists in read/.
                published = False
                try:
                    published = os.path.exists(os.path.join(PUBLIC_READS_DIR, os.path.basename(abs_path)))
                except Exception:
                    published = False
                out = inject_overlay(text, rel_fs, is_bumped(st.st_mtime), published)
                return self._send_bytes(out, "text/html; charset=utf-8", {"X-Overlay": "1"})

        # Otherwise: normal behavior.
        return super().do_GET()

    # --------- DIRECTORY LISTING ----------
    def list_directory(self, path):
        try:
            entries: list[tuple[float, os.DirEntry[str], os.stat_result]] = []
            dir_cache: dict[str, bool] = {}
            with os.scandir(path) as it:
                for entry in it:
                    try:
                        st = entry.stat()
                    except FileNotFoundError:
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if not _dir_has_visible_entries(entry.path, dir_cache):
                                continue
                    except OSError:
                        continue
                    entries.append((st.st_mtime, entry, st))
        except OSError:
            self.send_error(404, "No permission to list directory")
            return None

        entries.sort(key=lambda item: item[0], reverse=True)

        displaypath = urllib.parse.unquote(self.path)
        head_html = (
            f"<html><head><meta charset='utf-8'><title>Index of {html.escape(displaypath)}</title>"
            "<style>"
            "body{margin:14px 18px;font:14px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;color:#222}"
            "h2{margin:6px 0 10px;font-weight:600}"
            "hr{border:0;border-top:1px solid #e6e6e6;margin:8px 0}"
            "ul.dg-index{list-style:none;padding-left:0}"
            ".dg-index li{padding:2px 6px;border-radius:6px;margin:2px 0;display:flex;justify-content:space-between;align-items:center}"
            ".dg-bump{background:#fff6e5}"
            ".dg-pub a{color:#0a7;font-weight:600}"
            ".dg-legend{color:#666;font:13px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;margin-bottom:6px}"
            ".dg-actions{display:inline-flex;gap:6px}"
            ".dg-actions button, .dg-actions a{padding:2px 6px;border:1px solid #ccc;border-radius:6px;background:#f7f7f7;text-decoration:none;color:#333;font:12px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial}"
            ".dg-actions button[disabled], .dg-actions a[disabled]{opacity:.6;pointer-events:none}"
            ".dg-date{color:#666;margin-left:10px;white-space:nowrap}"
            "</style>"
            "<script src='/__index.js' defer></script>"
            "</head><body>"
        )

        rows: list[str] = [head_html, f"<h2>Index of {html.escape(displaypath)}</h2>"]
        rows.append("<div class='dg-legend'>🔥 bumped · 🟢 published · 🟡 highlight</div><hr><ul class='dg-index'>")

        if displaypath != "/":
            parent = os.path.dirname(displaypath.rstrip("/"))
            rows.append(f'<li><a href="{parent or "/"}">../</a></li>')

        now = time.time()
        for _, entry, st in entries:
            rendered = _render_list_entry(entry, now, st)
            if rendered:
                rows.append(rendered)

        rows.append("</ul><hr></body></html>")
        encoded = "\n".join(rows).encode("utf-8", "surrogateescape")
        self._send_bytes(encoded, "text/html; charset=utf-8")
        return None

    # --------- PATH MAP ----------
    def translate_path(self, path):
        path = urllib.parse.unquote(urllib.parse.urlparse(path).path)
        if path == "/":
            return SERVE_DIR
        safe = safe_join(path)
        return safe if safe else SERVE_DIR


def main():
    os.chdir(SERVE_DIR)
    with ThreadingHTTPServer(("", PORT), HTMLOnlyRequestHandler) as httpd:
        print(f"Serving ONLY .html/.pdf (and folders) from: {SERVE_DIR}")
        print(f"Access at: http://localhost:{PORT}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
