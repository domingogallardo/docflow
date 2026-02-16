"""Build intranet Read index pages under BASE_DIR/_site/read."""

from __future__ import annotations

import argparse
import html
import shutil
import sys
import time
from pathlib import Path
from typing import NamedTuple

# Support direct execution: `python utils/build_read_index.py ...`
if __package__ in (None, ""):
    _REPO_ROOT = Path(__file__).resolve().parents[1]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from utils.highlight_store import has_highlights_for_path
from utils.site_paths import raw_url_for_rel_path, resolve_base_dir, resolve_library_path, site_root
from utils.site_state import list_published, load_bump_state

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
READ_VIEWPORT = "width=device-width, initial-scale=1"
READ_BASE_STYLE = (
    "body{margin:14px 18px;font:14px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;color:#222;"
    "-webkit-text-size-adjust:100%;text-size-adjust:100%}"
    "h1{margin:6px 0 10px;font-weight:600}"
    "h2{margin:16px 0 10px;font-weight:600}"
    "ul{margin-top:0}"
    ".dg-nav{color:#666;font:13px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;margin-bottom:8px}"
    ".dg-nav a{text-decoration:none;color:#0a7}"
    ".file-icon{font-size:0.85em;vertical-align:baseline;display:inline-block;transform:translateY(-0.05em)}"
)


class SiteReadItem(NamedTuple):
    rel_path: str
    name: str
    mtime: float
    sort_mtime: float
    highlighted: bool



def fmt_date(ts: float) -> str:
    t = time.localtime(ts)
    return f"{t.tm_year}-{MONTHS[t.tm_mon-1]}-{t.tm_mday:02d} {t.tm_hour:02d}:{t.tm_min:02d}"



def _icon_for(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".pdf"):
        return '<span class="file-icon pdf-icon" aria-hidden="true">📕</span> '
    if lower.endswith((".html", ".htm")):
        return '<span class="file-icon html-icon" aria-hidden="true">📄</span> '
    return ""



def _is_site_highlighted(base_dir: Path, rel_path: str) -> bool:
    if not Path(rel_path).name.lower().endswith((".html", ".htm")):
        return False
    return has_highlights_for_path(base_dir, rel_path)



def collect_site_read_items(base_dir: Path) -> list[SiteReadItem]:
    published = list_published(base_dir)
    bump_state = load_bump_state(base_dir)
    items_state = bump_state.get("items", {})
    bump_items = items_state if isinstance(items_state, dict) else {}

    items: list[SiteReadItem] = []
    for rel in sorted(published):
        try:
            abs_path = resolve_library_path(base_dir, rel)
        except Exception:
            continue
        if not abs_path.is_file():
            continue

        st = abs_path.stat()
        bump_entry = bump_items.get(rel)
        bumped_mtime: float | None = None
        if isinstance(bump_entry, dict):
            try:
                bumped_mtime = float(bump_entry.get("bumped_mtime"))
            except Exception:
                bumped_mtime = None

        display_mtime = st.st_mtime
        effective_mtime = bumped_mtime if bumped_mtime is not None else display_mtime
        items.append(
            SiteReadItem(
                rel_path=rel,
                name=abs_path.name,
                mtime=display_mtime,
                sort_mtime=effective_mtime,
                highlighted=_is_site_highlighted(base_dir, rel),
            )
        )

    items.sort(key=lambda item: item.sort_mtime, reverse=True)
    return items



def build_site_read_html(items: list[SiteReadItem]) -> str:
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
        f'<meta name="viewport" content="{READ_VIEWPORT}">'
        f"<style>{READ_BASE_STYLE}</style>"
        '<script src="/read/article.js" defer></script>'
        '<title>Read</title></head><body>'
        '<div class="dg-nav"><a href="/">Home</a> · <a href="/browse/">Browse</a> · <a href="/read/">Read</a></div>'
        '<h1>Read</h1>'
        + list_html
        + "</body></html>"
    )



def _copy_site_read_assets(out_dir: Path) -> None:
    source = Path(__file__).resolve().parent / "static" / "article.js"
    if not source.is_file():
        raise FileNotFoundError(f"Missing read asset: {source}")

    target = out_dir / "article.js"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")



def write_site_read_index(base_dir: Path, output_dir: Path | None = None) -> Path:
    out_dir = output_dir or (site_root(base_dir) / "read")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Cleanup obsolete tweet pages from older read index layouts.
    tweets_pages_dir = out_dir / "tweets"
    if tweets_pages_dir.exists():
        shutil.rmtree(tweets_pages_dir)

    items = collect_site_read_items(base_dir)
    html_doc = build_site_read_html(items)
    out_path = out_dir / "index.html"
    out_path.write_text(html_doc, encoding="utf-8")
    _copy_site_read_assets(out_dir)
    return out_path



def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build intranet Read index pages.")
    parser.add_argument("--base-dir", help="BASE_DIR with Incoming/Posts/Tweets/... and _site/")
    parser.add_argument("--output-dir", help="Output dir (default BASE_DIR/_site/read)")
    return parser.parse_args(argv)



def main(argv: list[str]) -> int:
    args = parse_args(argv[1:])
    base_dir = resolve_base_dir(args.base_dir)
    out_dir = Path(args.output_dir).expanduser() if args.output_dir else None
    out_path = write_site_read_index(base_dir, out_dir)
    print(f"✓ Generated {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
