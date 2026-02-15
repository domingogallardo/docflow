"""Read index generators.

Two supported modes:
- Legacy mode: `python utils/build_read_index.py [DIRECTORY]`
  Generates `read.html` from files inside DIRECTORY (web/public/read compatible).
- Site mode (new): `python utils/build_read_index.py --base-dir <BASE_DIR>`
  Generates `_site/read/index.html` from `state/published.json`.
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterable, List, NamedTuple, Tuple
from urllib.parse import quote

# Support direct execution: `python utils/build_read_index.py ...`
if __package__ in (None, ""):
    _REPO_ROOT = Path(__file__).resolve().parents[1]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from utils.site_paths import raw_url_for_rel_path, resolve_base_dir, resolve_library_path, site_root
from utils.site_state import list_published

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
        if name.startswith("."):
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
            if not (entry.name.startswith("Consolidado Tweets ") or entry.name.startswith("Tweets ")):
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


# -------- New site mode --------

class SiteReadItem(NamedTuple):
    rel_path: str
    name: str
    mtime: float
    highlighted: bool


def _is_site_highlighted(base_dir: Path, rel_path: str) -> bool:
    rel_parts = Path(rel_path).parts
    if len(rel_parts) < 3:
        return False
    if rel_parts[0] != "Posts":
        return False
    if not rel_parts[-1].lower().endswith((".html", ".htm")):
        return False

    post_dir = base_dir / Path(*rel_parts[:-1])
    highlights_dir = post_dir / "highlights"
    if not highlights_dir.is_dir():
        return False

    filename = rel_parts[-1]
    for encoded in _highlight_name_candidates(filename):
        if (highlights_dir / f"{encoded}.json").is_file():
            return True
    return False


def collect_site_read_items(base_dir: Path) -> list[SiteReadItem]:
    published = list_published(base_dir)

    items: list[SiteReadItem] = []
    for rel in sorted(published):
        try:
            abs_path = resolve_library_path(base_dir, rel)
        except Exception:
            continue
        if not abs_path.is_file():
            continue
        items.append(
            SiteReadItem(
                rel_path=rel,
                name=abs_path.name,
                mtime=abs_path.stat().st_mtime,
                highlighted=_is_site_highlighted(base_dir, rel),
            )
        )

    items.sort(key=lambda item: item.mtime, reverse=True)
    return items


def _site_ascii_footer() -> str:
    owner_url = html.escape(_owner_url(), quote=True)
    owner_name = html.escape(DEFAULT_OWNER_NAME)
    return f'''<style>
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


def _collect_site_tweet_years(base_dir: Path, items: list[SiteReadItem]) -> dict[int, list[SiteReadItem]]:
    by_year: dict[int, list[SiteReadItem]] = defaultdict(list)
    for item in items:
        rel = Path(item.rel_path)
        parts = rel.parts
        if len(parts) < 3:
            continue
        if parts[0] != "Tweets":
            continue
        year_part = parts[1]
        if not year_part.startswith("Tweets "):
            continue
        year_text = year_part[7:]
        if len(year_text) != 4 or not year_text.isdigit():
            continue
        if not item.name.lower().endswith((".html", ".htm")):
            continue
        if not (item.name.startswith("Consolidado Tweets ") or item.name.startswith("Tweets ")):
            continue
        by_year[int(year_text)].append(item)

    for year in by_year:
        by_year[year].sort(key=lambda it: it.mtime, reverse=True)

    return dict(sorted(by_year.items(), key=lambda kv: kv[0], reverse=True))


def _render_site_tweets_section(tweets_by_year: dict[int, list[SiteReadItem]]) -> str:
    if not tweets_by_year:
        return "<h2>Tweets</h2><ul></ul>"
    lines = ["<h2>Tweets</h2><ul>"]
    for year, items in tweets_by_year.items():
        lines.append(f'<li><a href="/read/tweets/{year}.html">{year}</a> ({len(items)})</li>')
    lines.append("</ul>")
    return "\n".join(lines)


def _write_site_tweets_year_pages(out_dir: Path, tweets_by_year: dict[int, list[SiteReadItem]]) -> None:
    tweets_dir = out_dir / "tweets"
    tweets_dir.mkdir(parents=True, exist_ok=True)

    for year, items in tweets_by_year.items():
        if not items:
            list_html = "<ul></ul>"
        else:
            lines = ["<ul>"]
            for item in items:
                href = raw_url_for_rel_path(item.rel_path)
                esc = html.escape(item.name)
                lines.append(f'<li><a href="{href}" title="{esc}">{esc}</a> — {fmt_date(item.mtime)}</li>')
            lines.append("</ul>")
            list_html = "\n".join(lines)

        html_doc = (
            '<!DOCTYPE html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width">'
            '<script src="/read/article.js" defer></script>'
            f'<title>Tweets {year}</title></head><body>'
            f'<h1>Tweets {year}</h1>'
            f"{list_html}"
            '<p><a href="/read/">← Back to Read</a></p>'
            "</body></html>"
        )
        (tweets_dir / f"{year}.html").write_text(html_doc, encoding="utf-8")


def _copy_site_read_assets(out_dir: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source = repo_root / "web" / "public" / "read" / "article.js"
    if not source.is_file():
        return
    target = out_dir / "article.js"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def build_site_read_html(items: list[SiteReadItem], tweets_by_year: dict[int, list[SiteReadItem]]) -> str:
    if not items:
        list_html = "<ul></ul>"
    else:
        lines: list[str] = []
        current_year: int | None = None
        for item in items:
            year = time.localtime(item.mtime).tm_year
            if year != current_year:
                if current_year is not None:
                    lines.append("</ul>")
                lines.append(f"<h2>{year}</h2><ul>")
                current_year = year

            href = raw_url_for_rel_path(item.rel_path)
            icon = _icon_for(item.name)
            hl_icon = '<span class="file-icon hl-icon" aria-hidden="true">🟡</span> ' if item.highlighted else ""
            esc_name = html.escape(item.name)
            lines.append(
                f'<li>{icon}{hl_icon}<a href="{href}" title="{esc_name}">{esc_name}</a> — {fmt_date(item.mtime)}</li>'
            )

        if current_year is not None:
            lines.append("</ul>")
        list_html = "\n".join(lines)

    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width">'
        '<script src="/read/article.js" defer></script>'
        '<title>Read</title></head><body>'
        '<h1>Read</h1>'
        + _render_site_tweets_section(tweets_by_year)
        + list_html
        + _site_ascii_footer()
        + "</body></html>"
    )


def write_site_read_index(base_dir: Path, output_dir: Path | None = None) -> Path:
    out_dir = output_dir or (site_root(base_dir) / "read")
    out_dir.mkdir(parents=True, exist_ok=True)

    items = collect_site_read_items(base_dir)
    tweets_by_year = _collect_site_tweet_years(base_dir, items)
    html_doc = build_site_read_html(items, tweets_by_year)
    out_path = out_dir / "index.html"
    out_path.write_text(html_doc, encoding="utf-8")
    _write_site_tweets_year_pages(out_dir, tweets_by_year)
    _copy_site_read_assets(out_dir)
    return out_path


# -------- CLI --------

def _legacy_main(dir_path: str) -> int:
    if not os.path.isdir(dir_path):
        print(f"❌ Directory not found: {dir_path}", file=sys.stderr)
        return 1

    print(f"🧾 Generating {dir_path}/read.html…")
    entries = load_entries(dir_path, allowed_exts=(".html", ".htm", ".pdf"))
    highlight_files = _load_highlight_index(_get_base_dir())
    html_doc = build_html(dir_path, entries, highlight_files)
    out_path = os.path.join(dir_path, "read.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)
    print(f"✓ Generated {out_path}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Read index pages.")
    parser.add_argument("legacy_dir", nargs="?", help="Legacy target directory to generate read.html")
    parser.add_argument("--base-dir", help="BASE_DIR for new _site/read generation")
    parser.add_argument("--output-dir", help="Output dir for new mode (default BASE_DIR/_site/read)")
    parser.add_argument("--mode", choices=("auto", "legacy", "site"), default="auto")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv[1:])

    mode = args.mode
    if mode == "auto":
        mode = "legacy" if args.legacy_dir else "site"

    if mode == "legacy":
        dir_path = args.legacy_dir if args.legacy_dir else os.path.join("web", "public", "read")
        return _legacy_main(dir_path)

    base_dir = resolve_base_dir(args.base_dir)
    out_dir = Path(args.output_dir).expanduser() if args.output_dir else None
    out_path = write_site_read_index(base_dir, out_dir)
    print(f"✓ Generated {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
