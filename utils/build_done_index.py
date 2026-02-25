"""Build intranet Done index pages under BASE_DIR/_site/done."""

from __future__ import annotations

import argparse
import html
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

# Support direct execution: `python utils/build_done_index.py ...`
if __package__ in (None, ""):
    _REPO_ROOT = Path(__file__).resolve().parents[1]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from utils.highlight_store import has_highlights_for_path
from utils.site_paths import raw_url_for_rel_path, resolve_base_dir, resolve_library_path, site_root
from utils.site_state import load_done_state

DONE_VIEWPORT = "width=device-width, initial-scale=1"
DONE_BASE_STYLE = (
    "body{margin:14px 18px;font:14px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;color:#222;"
    "-webkit-text-size-adjust:100%;text-size-adjust:100%}"
    "h1{margin:6px 0 10px;font-weight:600}"
    "hr{border:0;border-top:1px solid #e6e6e6;margin:8px 0}"
    "ul{margin-top:0}"
    ".dg-done-list{list-style:none;padding-left:0}"
    ".dg-done-list li{padding:2px 6px;border-radius:6px;margin:2px 0;display:flex;justify-content:space-between;gap:10px;align-items:center}"
    ".dg-done-list li.dg-hl{background:#fff9e8}"
    ".dg-year{margin:14px 0 6px;font-size:1rem;font-weight:600;color:#555}"
    ".dg-nav{color:#666;font:13px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;margin-bottom:8px}"
    ".dg-nav a{text-decoration:none;color:#0a7}"
    ".dg-legendbar{display:flex;align-items:center;justify-content:flex-start;gap:6px;flex-wrap:wrap;margin-bottom:8px}"
    ".dg-legend{color:#666;font:13px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial}"
    ".dg-sort-toggle{padding:2px 8px;border:1px solid #ccc;border-radius:6px;background:#f7f7f7;color:#333;font:12px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;cursor:pointer}"
    ".dg-sort-toggle.is-active{border-color:#c8a400;background:#fff6e5}"
    ".dg-actions{display:inline-flex;gap:6px}"
    ".dg-actions button{padding:2px 6px;border:1px solid #ccc;border-radius:6px;background:#f7f7f7;color:#333;font:12px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;cursor:pointer}"
    ".file-icon{font-size:0.85em;vertical-align:baseline;display:inline-block;transform:translateY(-0.05em)}"
)

YEAR_RE = re.compile(r"(?:19|20)\d{2}")


class SiteDoneItem(NamedTuple):
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


def _actions_html(item: SiteDoneItem) -> str:
    if not item.name.lower().endswith(".pdf"):
        return ""
    path_attr = html.escape(item.rel_path, quote=True)
    return (
        "<span class='dg-actions'>"
        f"<button data-api-action=\"reopen\" data-docflow-path=\"{path_attr}\">Reopen to Reading</button>"
        f"<button data-api-action=\"to-browse\" data-docflow-path=\"{path_attr}\">Back to Browse</button>"
        "</span>"
    )


def _done_at_to_epoch(value: object) -> float | None:
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


def _year_for_item(rel_path: str) -> str:
    for segment in Path(rel_path).parts[:-1]:
        match = YEAR_RE.search(segment)
        if match:
            return match.group(0)
    return "Unknown"


def _group_items_by_year(items: list[SiteDoneItem]) -> list[tuple[str, list[SiteDoneItem]]]:
    grouped: dict[str, list[SiteDoneItem]] = {}
    for item in items:
        year = _year_for_item(item.rel_path)
        grouped.setdefault(year, []).append(item)

    def _sort_key(year: str) -> tuple[int, int | str]:
        if year.isdigit():
            return (0, -int(year))
        return (1, year.lower())

    ordered_years = sorted(grouped.keys(), key=_sort_key)
    return [(year, grouped[year]) for year in ordered_years]


def collect_site_done_items(base_dir: Path) -> list[SiteDoneItem]:
    done_state = load_done_state(base_dir)
    state_items = done_state.get("items", {})
    done_items = state_items if isinstance(state_items, dict) else {}

    items: list[SiteDoneItem] = []
    for rel in sorted(done_items):
        try:
            abs_path = resolve_library_path(base_dir, rel)
        except Exception:
            continue
        if not abs_path.is_file():
            continue

        st = abs_path.stat()
        done_entry = done_items.get(rel)
        done_mtime: float | None = None
        if isinstance(done_entry, dict):
            done_mtime = _done_at_to_epoch(done_entry.get("done_at"))
        display_mtime = st.st_mtime
        effective_mtime = done_mtime if done_mtime is not None else display_mtime
        items.append(
            SiteDoneItem(
                rel_path=rel,
                name=abs_path.name,
                mtime=display_mtime,
                sort_mtime=effective_mtime,
                highlighted=_is_site_highlighted(base_dir, rel),
            )
        )

    items.sort(key=lambda item: item.sort_mtime, reverse=True)
    return items


def build_site_done_html(items: list[SiteDoneItem]) -> str:
    if not items:
        list_html = '<ul class="dg-done-list"></ul>'
    else:
        sections: list[str] = []
        for year, year_items in _group_items_by_year(items):
            lines: list[str] = [f'<h2 class="dg-year">{html.escape(year)}</h2>', '<ul class="dg-done-list">']
            for item in year_items:
                href = raw_url_for_rel_path(item.rel_path)
                icon = _icon_for(item.name)
                hl_icon = '<span class="file-icon hl-icon" aria-hidden="true">🟡</span> ' if item.highlighted else ""
                esc_name = html.escape(item.name)
                row_class = ' class="dg-hl"' if item.highlighted else ""
                row_attrs = (
                    "data-dg-sortable='1' "
                    f"data-dg-highlighted='{'1' if item.highlighted else '0'}' "
                    f"data-dg-sort-mtime='{item.sort_mtime:.6f}' "
                    f"data-dg-name='{html.escape(item.name.lower(), quote=True)}'"
                )
                actions = _actions_html(item)
                lines.append(
                    f'<li{row_class} {row_attrs}><span>{hl_icon}{icon}<a href="{href}" title="{esc_name}">{esc_name}</a></span>{actions}</li>'
                )
            lines.append("</ul>")
            sections.append("\n".join(lines))
        list_html = "\n".join(sections)

    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f'<meta name="viewport" content="{DONE_VIEWPORT}">'
        f"<style>{DONE_BASE_STYLE}</style>"
        '<script src="/assets/actions.js" defer></script>'
        '<script src="/assets/browse-sort.js" defer></script>'
        "<title>Done</title></head><body>"
        '<div class="dg-nav"><a href="/">Home</a> · <a href="/browse/">Browse</a> · <a href="/reading/">Reading</a> · <a href="/working/">Working</a> · <a href="/done/">Done</a></div>'
        '<h1>Done</h1>'
        '<div class="dg-legendbar"><div class="dg-legend">🟡 highlight</div><button type="button" class="dg-sort-toggle" data-dg-sort-toggle aria-pressed="false">Highlight: off</button></div><hr>'
        + list_html
        + "</body></html>"
    )


def write_site_done_index(base_dir: Path, output_dir: Path | None = None) -> Path:
    out_dir = output_dir or (site_root(base_dir) / "done")
    out_dir.mkdir(parents=True, exist_ok=True)

    items = collect_site_done_items(base_dir)
    html_doc = build_site_done_html(items)
    out_path = out_dir / "index.html"
    out_path.write_text(html_doc, encoding="utf-8")
    return out_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build intranet Done index pages.")
    parser.add_argument("--base-dir", help="BASE_DIR with Incoming/Posts/Tweets/... and _site/")
    parser.add_argument("--output-dir", help="Output dir (default BASE_DIR/_site/done)")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv[1:])
    base_dir = resolve_base_dir(args.base_dir)
    out_dir = Path(args.output_dir).expanduser() if args.output_dir else None
    out_path = write_site_done_index(base_dir, out_dir)
    print(f"✓ Generated {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
