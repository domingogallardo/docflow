"""Generate the static web/public/read/read.html index with year headings.

- List files (HTML/PDF) ordered by mtime desc.
- Entries are grouped by year with <h2> headings.

Usage:
    python utils/build_read_index.py [DIRECTORY]

If DIRECTORY is not specified, "web/public/read" is assumed relative to CWD.
"""

from __future__ import annotations

import html
import os
import sys
import time
from pathlib import Path
import importlib.util
from typing import Iterable, List, Tuple
from urllib.parse import quote


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
BASE_DIR_ENV = "DOCFLOW_BASE_DIR"
OWNER_URL_ENV = "DOCFLOW_OWNER_URL"
DEFAULT_OWNER_URL = "https://domingogallardo.com/"
DEFAULT_OWNER_NAME = "Domingo Gallardo"


def fmt_date(ts: float) -> str:
    t = time.localtime(ts)
    return f"{t.tm_year}-{MONTHS[t.tm_mon-1]}-{t.tm_mday:02d} {t.tm_hour:02d}:{t.tm_min:02d}"


def load_entries(dir_path: str, allowed_exts: Iterable[str]) -> List[Tuple[float, str]]:
    entries: List[Tuple[float, str]] = []
    for name in os.listdir(dir_path):
        if name.startswith('.'):
            continue
        path = os.path.join(dir_path, name)
        if not os.path.isfile(path):
            continue
        low = name.lower()
        if low in ("read.html", "index.html", "index.htm"):
            continue
        if allowed_exts and not low.endswith(tuple(allowed_exts)):
            continue
        st = os.stat(path)
        entries.append((st.st_mtime, name))
    entries.sort(key=lambda x: x[0], reverse=True)
    return entries


def _icon_for(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".pdf"):
        return '<span class="file-icon pdf-icon" aria-hidden="true">📕</span> '
    if lower.endswith((".html", ".htm")):
        return '<span class="file-icon html-icon" aria-hidden="true">📄</span> '
    return ""


def _get_base_dir() -> Path | None:
    env_value = os.getenv(BASE_DIR_ENV)
    if env_value:
        return Path(env_value).expanduser()
    try:
        from config import BASE_DIR  # local import to avoid hard dependency in tests
    except Exception:
        BASE_DIR = None
    if BASE_DIR is not None:
        return BASE_DIR
    try:
        repo_root = Path(__file__).resolve().parents[1]
        config_path = repo_root / "config.py"
        if not config_path.is_file():
            return None
        spec = importlib.util.spec_from_file_location("docflow_config", config_path)
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        assert spec and spec.loader
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        base_dir = getattr(module, "BASE_DIR", None)
        return Path(base_dir) if base_dir else None
    except Exception:
        return None


def _load_highlight_index(base_dir: Path | None) -> set[str]:
    if base_dir is None:
        return set()
    posts_root = base_dir / "Posts"
    if not posts_root.is_dir():
        return set()
    highlight_files: set[str] = set()
    try:
        for entry in posts_root.iterdir():
            if not entry.is_dir():
                continue
            name = entry.name
            if not name.startswith("Posts "):
                continue
            suffix = name[6:]
            if len(suffix) != 4 or not suffix.isdigit():
                continue
            highlights_dir = entry / "highlights"
            if not highlights_dir.is_dir():
                continue
            for item in highlights_dir.iterdir():
                if item.is_file() and item.suffix.lower() == ".json":
                    highlight_files.add(item.name)
    except Exception:
        return set()
    return highlight_files


def _highlight_name_candidates(name: str) -> list[str]:
    candidates = [
        quote(name),
        quote(name, safe="~!*()'"),
    ]
    deduped: list[str] = []
    seen = set()
    for item in candidates:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _highlight_icon(name: str, highlight_files: set[str]) -> str:
    if not highlight_files:
        return ""
    for encoded in _highlight_name_candidates(name):
        if f"{encoded}.json" in highlight_files:
            return '<span class="file-icon hl-icon" aria-hidden="true">🟡</span> '
    return ""


def _render_list_item(name: str, mtime: float, highlight_files: set[str]) -> str:
    href = quote(name, safe="~!*()'")
    esc = html.escape(name)
    icon = _icon_for(name)
    highlight_icon = _highlight_icon(name, highlight_files)
    d = fmt_date(mtime)
    return f'<li>{icon}{highlight_icon}<a href="{href}" title="{esc}">{esc}</a> — {d}</li>'


def _owner_url() -> str:
    value = os.getenv(OWNER_URL_ENV, "").strip()
    if value:
        return value
    return DEFAULT_OWNER_URL


def _tweet_year_items(dir_path: str) -> list[tuple[int, int]]:
    tweets_root = Path(dir_path) / "tweets"
    if not tweets_root.is_dir():
        return []

    items: list[tuple[int, int]] = []
    for child in tweets_root.iterdir():
        if not child.is_dir():
            continue
        name = child.name
        if len(name) != 4 or not name.isdigit():
            continue
        count = 0
        for entry in child.iterdir():
            if not entry.is_file():
                continue
            low = entry.name.lower()
            if not entry.name.startswith("Consolidado Tweets "):
                continue
            if low.endswith((".html", ".htm")):
                count += 1
        if count > 0:
            items.append((int(name), count))

    items.sort(key=lambda x: x[0], reverse=True)
    return items


def _render_tweets_section(dir_path: str) -> str:
    years = _tweet_year_items(dir_path)
    if not years:
        return "<h2>Tweets</h2><ul></ul>"

    lines = ["<h2>Tweets</h2><ul>"]
    for year, count in years:
        lines.append(f'<li><a href="/read/tweets/{year}.html">{year}</a> ({count})</li>')
    lines.append("</ul>")
    return "\n".join(lines)


def build_html(dir_path: str, entries: List[Tuple[float, str]], highlight_files: set[str] | None = None) -> str:
    if not entries:
        list_html = "<ul></ul>"
    else:
        list_parts: List[str] = []
        current_year: int | None = None
        highlight_files = highlight_files or set()
        for mtime, name in entries:
            year = time.localtime(mtime).tm_year
            if year != current_year:
                if current_year is not None:
                    list_parts.append("</ul>")
                list_parts.append(f"<h2>{year}</h2><ul>")
                current_year = year
            list_parts.append(_render_list_item(name, mtime, highlight_files))
        list_parts.append("</ul>")
        list_html = "\n".join(list_parts)

    owner_url = html.escape(_owner_url(), quote=True)
    owner_name = html.escape(DEFAULT_OWNER_NAME)
    tweets_html = _render_tweets_section(dir_path)

    ascii_open = f'''<style>
  .ascii-head {{ margin-top: 28px; color: #666; font-size: 14px; }}
  .owner-copy {{
    margin: 10px 0 0;
    color: #666;
    font-size: 14px;
  }}
  pre.ascii-logo {{
    margin: 10px 0 0;
    color: #666;
    line-height: 1.05;
    font-size: 12px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    white-space: pre;
  }}
  .file-icon {{
    font-size: 0.85em;
    vertical-align: baseline;
    display: inline-block;
    transform: translateY(-0.05em);
  }}
</style>
<div class="ascii-head"><a href="https://github.com/domingogallardo/docflow" target="_blank" rel="noopener">Docflow</a></div>
<p class="owner-copy">© <a href="{owner_url}" target="_blank" rel="noopener">{owner_name}</a></p>
<pre class="ascii-logo" aria-hidden="true">         _
        /^\\
        |-|
        |D|
        |O|
        |C|
        |F|
        |L|
        |O|
        |W|
       /| |\\
      /_| |_\\
        /_\\
       /___\\
      /_/ \\_\\
</pre>'''

    html_doc = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width">'
        '<script src="/read/article.js" defer></script>'
        '<title>Read</title></head><body>'
        '<h1>Read</h1>'
        + tweets_html
        + list_html
        + ascii_open
        + '</body></html>'
    )
    return html_doc


def main(argv: list[str]) -> int:
    if len(argv) > 2:
        print("Usage: python utils/build_read_index.py [DIRECTORY]", file=sys.stderr)
        return 2
    dir_path = argv[1] if len(argv) == 2 else os.path.join("web", "public", "read")
    if not os.path.isdir(dir_path):
        print(f"❌ Directory not found: {dir_path}", file=sys.stderr)
        return 1

    print("🧾 Generating web/public/read/read.html…")
    entries = load_entries(dir_path, allowed_exts=(".html", ".htm", ".pdf"))
    highlight_files = _load_highlight_index(_get_base_dir())
    html_doc = build_html(dir_path, entries, highlight_files)
    out_path = os.path.join(dir_path, "read.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)
    print(f"✓ Generated {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
