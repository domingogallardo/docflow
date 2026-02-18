"""Build intranet Working index pages under BASE_DIR/_site/working."""

from __future__ import annotations

import argparse
import html
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

# Support direct execution: `python utils/build_working_index.py ...`
if __package__ in (None, ""):
    _REPO_ROOT = Path(__file__).resolve().parents[1]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from utils.highlight_store import has_highlights_for_path
from utils.site_paths import raw_url_for_rel_path, resolve_base_dir, resolve_library_path, site_root
from utils.site_state import load_working_state

WORKING_VIEWPORT = "width=device-width, initial-scale=1"
WORKING_BASE_STYLE = (
    "body{margin:14px 18px;font:14px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;color:#222;"
    "-webkit-text-size-adjust:100%;text-size-adjust:100%}"
    "h1{margin:6px 0 10px;font-weight:600}"
    "h2{margin:16px 0 10px;font-weight:600}"
    "ul{margin-top:0}"
    ".dg-working-list{list-style:none;padding-left:0}"
    ".dg-working-list li{padding:2px 6px;border-radius:6px;margin:2px 0}"
    ".dg-nav{color:#666;font:13px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;margin-bottom:8px}"
    ".dg-nav a{text-decoration:none;color:#0a7}"
    ".dg-legend{color:#666;font:13px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;margin-bottom:8px}"
    ".file-icon{font-size:0.85em;vertical-align:baseline;display:inline-block;transform:translateY(-0.05em)}"
)


class SiteWorkingItem(NamedTuple):
    rel_path: str
    name: str
    mtime: float
    sort_mtime: float
    highlighted: bool

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



def _iso_to_epoch(value: object) -> float | None:
    if not isinstance(value, str):
        return None

    iso_value = value.strip()
    if not iso_value:
        return None

    if iso_value.endswith("Z"):
        iso_value = iso_value[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(iso_value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def collect_site_working_items(base_dir: Path) -> list[SiteWorkingItem]:
    working_state = load_working_state(base_dir)
    state_items = working_state.get("items", {})
    working_items = state_items if isinstance(state_items, dict) else {}

    items: list[SiteWorkingItem] = []
    for rel in sorted(working_items):
        try:
            abs_path = resolve_library_path(base_dir, rel)
        except Exception:
            continue
        if not abs_path.is_file():
            continue

        st = abs_path.stat()
        working_entry = working_items.get(rel)
        working_mtime: float | None = None
        if isinstance(working_entry, dict):
            working_mtime = _iso_to_epoch(working_entry.get("working_at"))
        display_mtime = st.st_mtime
        effective_mtime = working_mtime if working_mtime is not None else display_mtime
        items.append(
            SiteWorkingItem(
                rel_path=rel,
                name=abs_path.name,
                mtime=display_mtime,
                sort_mtime=effective_mtime,
                highlighted=_is_site_highlighted(base_dir, rel),
            )
        )

    items.sort(key=lambda item: item.sort_mtime, reverse=True)
    return items



def build_site_working_html(items: list[SiteWorkingItem]) -> str:
    if not items:
        list_html = '<ul class="dg-working-list"></ul>'
    else:
        lines: list[str] = ['<ul class="dg-working-list">']
        for item in items:
            href = raw_url_for_rel_path(item.rel_path)
            icon = _icon_for(item.name)
            hl_icon = '<span class="file-icon hl-icon" aria-hidden="true">🟡</span> ' if item.highlighted else ""
            esc_name = html.escape(item.name)
            lines.append(
                f'<li>{hl_icon}{icon}<a href="{href}" title="{esc_name}">{esc_name}</a></li>'
            )
        lines.append("</ul>")
        list_html = "\n".join(lines)

    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f'<meta name="viewport" content="{WORKING_VIEWPORT}">'
        f"<style>{WORKING_BASE_STYLE}</style>"
        '<script src="/working/article.js" defer></script>'
        '<title>Working</title></head><body>'
        '<div class="dg-nav"><a href="/">Home</a> · <a href="/browse/">Browse</a> · <a href="/working/">Working</a> · <a href="/done/">Done</a></div>'
        '<h1>Working</h1>'
        '<div class="dg-legend">🟡 highlight</div>'
        + list_html
        + "</body></html>"
    )



def _copy_site_working_assets(out_dir: Path) -> None:
    source = Path(__file__).resolve().parent / "static" / "article.js"
    if not source.is_file():
        raise FileNotFoundError(f"Missing working asset: {source}")

    target = out_dir / "article.js"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")



def write_site_working_index(base_dir: Path, output_dir: Path | None = None) -> Path:
    out_dir = output_dir or (site_root(base_dir) / "working")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Cleanup obsolete tweet pages from older working index layouts.
    tweets_pages_dir = out_dir / "tweets"
    if tweets_pages_dir.exists():
        shutil.rmtree(tweets_pages_dir)

    # Cleanup obsolete legacy read pages.
    if output_dir is None:
        legacy_read_dir = site_root(base_dir) / "read"
        if legacy_read_dir.exists():
            shutil.rmtree(legacy_read_dir)

    items = collect_site_working_items(base_dir)
    html_doc = build_site_working_html(items)
    out_path = out_dir / "index.html"
    out_path.write_text(html_doc, encoding="utf-8")
    _copy_site_working_assets(out_dir)
    return out_path



def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build intranet Working index pages.")
    parser.add_argument("--base-dir", help="BASE_DIR with Incoming/Posts/Tweets/... and _site/")
    parser.add_argument("--output-dir", help="Output dir (default BASE_DIR/_site/working)")
    return parser.parse_args(argv)



def main(argv: list[str]) -> int:
    args = parse_args(argv[1:])
    base_dir = resolve_base_dir(args.base_dir)
    out_dir = Path(args.output_dir).expanduser() if args.output_dir else None
    out_path = write_site_working_index(base_dir, out_dir)
    print(f"✓ Generated {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
