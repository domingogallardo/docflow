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
from typing import Iterable, List, Tuple
from urllib.parse import quote


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


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


def _render_list_item(name: str, mtime: float) -> str:
    href = quote(name)
    esc = html.escape(name)
    icon = _icon_for(name)
    d = fmt_date(mtime)
    return f'<li>{icon}<a href="{href}" title="{esc}">{esc}</a> — {d}</li>'


def build_html(dir_path: str, entries: List[Tuple[float, str]]) -> str:
    if not entries:
        list_html = "<ul></ul>"
    else:
        list_parts: List[str] = []
        current_year: int | None = None
        for mtime, name in entries:
            year = time.localtime(mtime).tm_year
            if year != current_year:
                if current_year is not None:
                    list_parts.append("</ul>")
                list_parts.append(f"<h2>{year}</h2><ul>")
                current_year = year
            list_parts.append(_render_list_item(name, mtime))
        list_parts.append("</ul>")
        list_html = "\n".join(list_parts)

    ascii_open = r'''<style>
  .ascii-head { margin-top: 28px; color: #666; font-size: 14px; }
  pre.ascii-logo {
    margin: 10px 0 0;
    color: #666;
    line-height: 1.05;
    font-size: 12px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    white-space: pre;
  }
  .file-icon {
    font-size: 0.85em;
    vertical-align: baseline;
    display: inline-block;
    transform: translateY(-0.05em);
  }
</style>
<div class="ascii-head"><a href="https://github.com/domingogallardo/docflow" target="_blank" rel="noopener">Docflow</a></div>
<pre class="ascii-logo" aria-hidden="true">         _
        /^\
        |-|
        |D|
        |O|
        |C|
        |F|
        |L|
        |O|
        |W|
       /| |\
      /_| |_\
        /_\
       /___\
      /_/ \_\
</pre>'''

    html_doc = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width">'
        '<script src="/read/article.js" defer></script>'
        '<title>Read</title></head><body>'
        '<h1>Read</h1>'
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
    html_doc = build_html(dir_path, entries)
    out_path = os.path.join(dir_path, "read.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)
    print(f"✓ Generated {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
