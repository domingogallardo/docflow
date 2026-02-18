"""Generate static browse pages under BASE_DIR/_site/browse.

The generated browse UI mirrors the intranet local reading workflow while
keeping pages static.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import time
from datetime import datetime, timezone
from dataclasses import dataclass, replace
from pathlib import Path
import sys
from urllib.parse import quote

# Support direct execution: `python utils/build_browse_index.py ...`
if __package__ in (None, ""):
    _REPO_ROOT = Path(__file__).resolve().parents[1]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from utils.site_paths import (
    library_roots,
    normalize_rel_path,
    raw_url_for_rel_path,
    rel_path_from_abs,
    resolve_base_dir,
    site_root,
)
from utils.highlight_store import has_highlights_for_path
from utils.site_state import load_bump_state, load_published_state

CATEGORY_KEYS = ("posts", "tweets", "pdfs", "images", "podcasts")
CATEGORY_LABELS = {
    "posts": "Posts",
    "tweets": "Tweets",
    "pdfs": "Pdfs",
    "images": "Images",
    "podcasts": "Podcasts",
}

SKIP_DIR_NAMES = {"highlights", "__pycache__"}
YEAR_SUFFIX_RE = re.compile(r"(\d{4})$")
YEAR_COUNT_CATEGORIES = {"posts", "tweets", "pdfs", "images"}
YEAR_SORT_CATEGORIES = {"posts", "tweets", "pdfs", "images"}


@dataclass(frozen=True)
class BrowseItem:
    rel_path: str
    name: str
    mtime: float
    published: bool
    bumped: bool
    highlighted: bool
    sort_mtime: float | None = None


@dataclass(frozen=True)
class BrowseEntry:
    name: str
    href: str
    mtime: float
    is_dir: bool
    icon: str
    rel_path: str | None = None
    published: bool = False
    bumped: bool = False
    highlighted: bool = False
    sort_mtime: float | None = None
    item_count: int | None = None


def _safe_quote_component(value: str) -> str:
    return quote(value, safe="~!*()'")


def _is_hidden_name(name: str) -> bool:
    return name.startswith(".")


def _skip_directory(name: str) -> bool:
    return _is_hidden_name(name) or name in SKIP_DIR_NAMES


def _is_visible_file_name(name: str) -> bool:
    if _is_hidden_name(name):
        return False
    lower = name.lower()
    return lower.endswith((".html", ".htm", ".pdf"))


def _icon_for_filename(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".pdf"):
        return "📕 "
    if lower.endswith((".html", ".htm")):
        return "📄 "
    return ""


def _is_highlighted(base_dir: Path, rel_path: str) -> bool:
    low_name = Path(rel_path).name.lower()
    if not low_name.endswith((".html", ".htm")):
        return False
    return has_highlights_for_path(base_dir, rel_path)


def _entry_classes(entry: BrowseEntry) -> str:
    classes: list[str] = []
    if entry.bumped:
        classes.append("dg-bump")
    if entry.published:
        classes.append("dg-pub")
    if entry.highlighted:
        classes.append("dg-hl")
    return f' class="{" ".join(classes)}"' if classes else ""


def _actions_html(entry: BrowseEntry) -> str:
    if entry.is_dir or not entry.rel_path:
        return ""
    if not entry.name.lower().endswith(".pdf"):
        return ""

    pub_action = "unpublish" if entry.published else "publish"
    pub_label = "Unpublish" if entry.published else "Publish"
    bump_action = "unbump" if entry.bumped else "bump"
    bump_label = "Unbump" if entry.bumped else "Bump"

    path_attr = html.escape(entry.rel_path, quote=True)
    return (
        "<span class='dg-actions'>"
        f"<button class='dg-act' data-api-action=\"{pub_action}\" data-docflow-path=\"{path_attr}\">{pub_label}</button>"
        f"<button class='dg-act' data-api-action=\"{bump_action}\" data-docflow-path=\"{path_attr}\">{bump_label}</button>"
        "</span>"
    )


def _render_entry(entry: BrowseEntry) -> str:
    display_name = entry.name + ("/" if entry.is_dir else "")
    esc_name = html.escape(display_name)
    count_html = f" <span class='dg-count'>({entry.item_count})</span>" if entry.item_count is not None else ""

    prefix = (
        ("🔥 " if entry.bumped else "")
        + ("🟢 " if entry.published else "")
        + ("🟡 " if entry.highlighted else "")
        + entry.icon
    )
    cls_attr = _entry_classes(entry)
    attr_bits = [
        "data-dg-sortable='1'",
        f"data-dg-bumped='{'1' if entry.bumped else '0'}'",
        f"data-dg-published='{'1' if entry.published else '0'}'",
        f"data-dg-highlighted='{'1' if entry.highlighted else '0'}'",
        f"data-dg-sort-mtime='{_sort_mtime(entry):.6f}'",
        f"data-dg-name='{html.escape(entry.name.lower(), quote=True)}'",
    ]
    attrs = f"{cls_attr} " + " ".join(attr_bits) if cls_attr else " " + " ".join(attr_bits)
    actions = _actions_html(entry)
    return (
        f"<li{attrs}><span>{prefix}<a href=\"{entry.href}\">{esc_name}</a>{count_html}</span>{actions}</li>"
    )


def _sort_mtime(entry: BrowseEntry) -> float:
    if entry.sort_mtime is not None:
        return entry.sort_mtime
    return entry.mtime


def _published_at_to_epoch(value: object) -> float | None:
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


def _natural_priority(entry: BrowseEntry) -> int:
    if entry.bumped:
        return 0
    if entry.published:
        return 1
    return 2


def _entry_sort_key(entry: BrowseEntry) -> tuple[int, float, str]:
    return (_natural_priority(entry), -_sort_mtime(entry), entry.name.lower())


def _base_head(title: str) -> str:
    return (
        f"<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>{html.escape(title)}</title>"
        "<style>"
        "body{margin:14px 18px;font:14px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;color:#222}"
        "h2{margin:6px 0 10px;font-weight:600}"
        "hr{border:0;border-top:1px solid #e6e6e6;margin:8px 0}"
        "ul.dg-index{list-style:none;padding-left:0}"
        ".dg-index li{padding:2px 6px;border-radius:6px;margin:2px 0;display:flex;justify-content:space-between;align-items:center;gap:10px}"
        ".dg-bump{background:#fff6e5}"
        ".dg-pub a{color:#0a7;font-weight:600}"
        ".dg-legend{color:#666;font:13px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;margin-bottom:6px}"
        ".dg-nav{color:#666;font:13px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;margin-bottom:8px}"
        ".dg-nav a{text-decoration:none;color:#0a7}"
        ".dg-actions{display:inline-flex;gap:6px}"
        ".dg-actions button, .dg-actions a, .dg-rebuild{padding:2px 6px;border:1px solid #ccc;border-radius:6px;background:#f7f7f7;text-decoration:none;color:#333;font:12px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;cursor:pointer}"
        ".dg-actions button[disabled], .dg-actions a[disabled], .dg-rebuild[disabled]{opacity:.6;pointer-events:none}"
        ".dg-count{color:#666;margin-left:8px;white-space:nowrap}"
        ".dg-sortbar{margin:6px 0 8px}"
        ".dg-sort-toggle{padding:2px 8px;border:1px solid #ccc;border-radius:6px;background:#f7f7f7;color:#333;font:12px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;cursor:pointer}"
        ".dg-sort-toggle.is-active{border-color:#c8a400;background:#fff6e5}"
        "</style>"
        "<script src='/assets/actions.js' defer></script>"
        "<script src='/assets/browse-sort.js' defer></script>"
        "</head><body>"
    )


def _render_directory_page(
    *,
    title: str,
    display_path: str,
    entries: list[BrowseEntry],
    parent_href: str | None,
) -> str:
    rows: list[str] = [_base_head(title)]
    rows.append("<div class='dg-nav'><a href='/'>Home</a> · <a href='/browse/'>Browse</a> · <a href='/read/'>Read</a></div>")
    rows.append(f"<h2>Index of {html.escape(display_path)}</h2>")
    rows.append(
        "<div class='dg-sortbar'><button type='button' class='dg-sort-toggle' data-dg-sort-toggle "
        "aria-pressed='false'>Highlights first: off</button></div>"
    )
    rows.append("<div class='dg-legend'>🔥 bumped · 🟢 published · 🟡 highlight</div><hr><ul class='dg-index'>")

    if parent_href:
        rows.append(f'<li data-dg-parent="1"><a href="{parent_href}">../</a></li>')

    for entry in entries:
        rows.append(_render_entry(entry))

    rows.append("</ul><hr></body></html>")
    return "\n".join(rows)


def _dir_has_visible_entries(path: Path, cache: dict[str, bool]) -> bool:
    key = str(path.resolve())
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        with os.scandir(path) as it:
            for entry in it:
                name = entry.name
                if _skip_directory(name) and entry.is_dir(follow_symlinks=False):
                    continue
                if _is_hidden_name(name):
                    continue

                try:
                    if entry.is_dir(follow_symlinks=False):
                        if _dir_has_visible_entries(Path(entry.path), cache):
                            cache[key] = True
                            return True
                    else:
                        if _is_visible_file_name(name):
                            cache[key] = True
                            return True
                except OSError:
                    continue
    except OSError:
        cache[key] = False
        return False

    cache[key] = False
    return False


def _count_visible_files(path: Path, cache: dict[str, int]) -> int:
    key = str(path.resolve())
    cached = cache.get(key)
    if cached is not None:
        return cached

    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                name = entry.name
                if _is_hidden_name(name):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if _skip_directory(name):
                            continue
                        total += _count_visible_files(Path(entry.path), cache)
                    else:
                        if _is_visible_file_name(name):
                            total += 1
                except OSError:
                    continue
    except OSError:
        total = 0

    cache[key] = total
    return total


def _annotate_root_year_counts(*, category: str, rel_dir: Path, abs_dir: Path, entries: list[BrowseEntry]) -> list[BrowseEntry]:
    if rel_dir != Path(".") or category not in YEAR_COUNT_CATEGORIES:
        return entries

    count_cache: dict[str, int] = {}
    annotated: list[BrowseEntry] = []
    for entry in entries:
        if entry.is_dir and _extract_entry_year(entry) is not None:
            child_abs = abs_dir / entry.name
            item_count = _count_visible_files(child_abs, count_cache)
            annotated.append(replace(entry, item_count=item_count))
            continue
        annotated.append(entry)
    return annotated


def _category_for_root_segment(segment: str) -> str | None:
    mapping = {
        "Posts": "posts",
        "Tweets": "tweets",
        "Pdfs": "pdfs",
        "PDFs": "pdfs",
        "Images": "images",
        "Podcasts": "podcasts",
    }
    return mapping.get(segment)


def _category_and_rel_dir(rel_path: str) -> tuple[str | None, Path | None]:
    normalized = normalize_rel_path(rel_path)
    parts = Path(normalized).parts
    if not parts:
        return None, None

    category = _category_for_root_segment(parts[0])
    if category is None:
        return None, None

    tail_parts = parts[1:]
    if not tail_parts:
        return category, Path(".")
    return category, Path(*tail_parts).parent


def _display_path_for_category_dir(category: str, rel_dir: Path) -> str:
    if rel_dir == Path("."):
        return f"/browse/{category}/"
    return f"/browse/{category}/{rel_dir.as_posix()}/"


def _cleanup_obsolete_incoming_dir(base_dir: Path) -> None:
    browse_dir = site_root(base_dir) / "browse"
    incoming_dir = browse_dir / "incoming"
    if incoming_dir.exists():
        shutil.rmtree(incoming_dir)


def _scan_directory(
    *,
    base_dir: Path,
    abs_dir: Path,
    published_items: dict[str, dict],
    bump_items: dict[str, dict],
    visibility_cache: dict[str, bool],
) -> tuple[list[BrowseEntry], list[str], int]:
    entries: list[BrowseEntry] = []
    child_dirs: list[str] = []
    file_count = 0

    try:
        with os.scandir(abs_dir) as it:
            for fs_entry in it:
                name = fs_entry.name
                if _is_hidden_name(name):
                    continue

                try:
                    st = fs_entry.stat()
                except OSError:
                    continue

                try:
                    if fs_entry.is_dir(follow_symlinks=False):
                        if _skip_directory(name):
                            continue
                        child_abs = Path(fs_entry.path)
                        if not _dir_has_visible_entries(child_abs, visibility_cache):
                            continue

                        child_dirs.append(name)
                        entries.append(
                            BrowseEntry(
                                name=name,
                                href=f"{_safe_quote_component(name)}/",
                                mtime=st.st_mtime,
                                sort_mtime=st.st_mtime,
                                is_dir=True,
                                icon="📁 ",
                            )
                        )
                        continue
                except OSError:
                    continue

                if not _is_visible_file_name(name):
                    continue

                file_count += 1
                abs_path = Path(fs_entry.path)
                rel = rel_path_from_abs(base_dir, abs_path)
                published_entry = published_items.get(rel)
                published_at_mtime = None
                if isinstance(published_entry, dict):
                    published_at_mtime = _published_at_to_epoch(published_entry.get("published_at"))
                is_published = rel in published_items

                bump_entry = bump_items.get(rel)
                bumped_mtime = None
                if isinstance(bump_entry, dict):
                    try:
                        bumped_mtime = float(bump_entry.get("bumped_mtime"))
                    except Exception:
                        bumped_mtime = None
                display_mtime = st.st_mtime
                effective_mtime = bumped_mtime
                if effective_mtime is None:
                    if is_published and published_at_mtime is not None:
                        effective_mtime = published_at_mtime
                    else:
                        effective_mtime = display_mtime
                bumped = bumped_mtime is not None
                entries.append(
                    BrowseEntry(
                        name=name,
                        href=raw_url_for_rel_path(rel),
                        mtime=display_mtime,
                        sort_mtime=effective_mtime,
                        is_dir=False,
                        icon=_icon_for_filename(name),
                        rel_path=rel,
                        published=is_published,
                        bumped=bumped,
                        highlighted=_is_highlighted(base_dir, rel),
                    )
                )
    except OSError:
        return [], [], 0

    entries.sort(key=_entry_sort_key)
    child_dirs.sort()
    return entries, child_dirs, file_count


def _write_category_directory_page(
    *,
    base_dir: Path,
    category: str,
    category_root: Path,
    rel_dir: Path,
    published_items: dict[str, dict],
    bump_items: dict[str, dict],
    visibility_cache: dict[str, bool],
) -> tuple[list[str], int]:
    out_root = site_root(base_dir) / "browse" / category
    out_root.mkdir(parents=True, exist_ok=True)

    abs_dir = category_root / rel_dir
    out_dir = out_root / rel_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    entries, child_dirs, direct_files = _scan_directory(
        base_dir=base_dir,
        abs_dir=abs_dir,
        published_items=published_items,
        bump_items=bump_items,
        visibility_cache=visibility_cache,
    )
    if category in YEAR_SORT_CATEGORIES and rel_dir == Path("."):
        entries = _sort_root_year_entries(entries)
    entries = _annotate_root_year_counts(
        category=category,
        rel_dir=rel_dir,
        abs_dir=abs_dir,
        entries=entries,
    )
    display_path = _display_path_for_category_dir(category, rel_dir)
    html_doc = _render_directory_page(
        title=f"Index of {display_path}",
        display_path=display_path,
        entries=entries,
        parent_href="../",
    )
    (out_dir / "index.html").write_text(html_doc, encoding="utf-8")
    return child_dirs, direct_files


def _extract_entry_year(entry: BrowseEntry) -> int | None:
    if not entry.is_dir:
        return None
    match = YEAR_SUFFIX_RE.search(entry.name)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _sort_root_year_entries(entries: list[BrowseEntry]) -> list[BrowseEntry]:
    year_dirs: list[tuple[int, BrowseEntry]] = []
    others: list[BrowseEntry] = []
    for entry in entries:
        year = _extract_entry_year(entry)
        if year is None:
            others.append(entry)
        else:
            year_dirs.append((year, entry))

    year_dirs.sort(key=lambda item: item[0], reverse=True)
    others.sort(key=_entry_sort_key)
    return [entry for _, entry in year_dirs] + others


def _write_category_tree(
    *,
    base_dir: Path,
    category: str,
    category_root: Path,
    published_items: dict[str, dict],
    bump_items: dict[str, dict],
) -> int:
    visibility_cache: dict[str, bool] = {}

    def walk(rel_dir: Path) -> int:
        child_dirs, direct_files = _write_category_directory_page(
            base_dir=base_dir,
            category=category,
            category_root=category_root,
            rel_dir=rel_dir,
            published_items=published_items,
            bump_items=bump_items,
            visibility_cache=visibility_cache,
        )

        total_files = direct_files
        for child in child_dirs:
            total_files += walk(rel_dir / child)
        return total_files

    return walk(Path("."))


def _write_browse_home(base_dir: Path, category_roots: dict[str, Path], counts: dict[str, int]) -> None:
    out_dir = site_root(base_dir) / "browse"
    out_dir.mkdir(parents=True, exist_ok=True)

    now = time.time()
    entries: list[BrowseEntry] = []
    for category in CATEGORY_KEYS:
        root = category_roots[category]
        label = CATEGORY_LABELS[category]
        count = counts.get(category, 0)
        if root.exists():
            try:
                mtime = root.stat().st_mtime
            except OSError:
                mtime = now
        else:
            mtime = now

        entries.append(
            BrowseEntry(
                name=label,
                href=f"{category}/",
                mtime=mtime,
                sort_mtime=mtime,
                is_dir=True,
                icon="📁 ",
                item_count=count,
            )
        )

    html_doc = _render_directory_page(
        title="Index of /browse/",
        display_path="/browse/",
        entries=entries,
        parent_href="/",
    )
    html_doc = html_doc.replace(
        "</ul><hr></body></html>",
        "</ul><p><button class='dg-rebuild' data-api-action='rebuild'>Rebuild browse + read</button></p><hr></body></html>",
    )
    (out_dir / "index.html").write_text(html_doc, encoding="utf-8")


def write_site_home(base_dir: Path) -> None:
    out_dir = site_root(base_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    html_doc = (
        "<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>Docflow</title>"
        "<style>body{margin:14px 18px;font:14px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;color:#222}"
        "h1{margin:6px 0 10px;font-weight:600}a{color:#0a7;text-decoration:none}"
        ".dg-actions button{padding:2px 6px;border:1px solid #ccc;border-radius:6px;background:#f7f7f7;color:#333;font:12px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;cursor:pointer}"
        "</style><script src='/assets/actions.js' defer></script></head><body>"
        "<h1>Docflow Intranet</h1>"
        "<p><a href='/browse/'>Browse</a> · <a href='/read/'>Read</a></p>"
        "<p><button data-api-action='rebuild'>Rebuild browse + read</button></p>"
        "</body></html>"
    )

    output = out_dir / "index.html"
    output.write_text(html_doc, encoding="utf-8")


def ensure_assets(base_dir: Path) -> None:
    assets_dir = site_root(base_dir) / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    js = """
(function() {
  async function callApi(action, path) {
    const body = path ? { path } : {};
    const response = await fetch(`/api/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    return response.ok;
  }

  document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-api-action]');
    if (!button) return;
    event.preventDefault();

    const action = button.getAttribute('data-api-action');
    const path = button.getAttribute('data-docflow-path') || '';
    button.setAttribute('disabled', '');

    try {
      const ok = await callApi(action, path);
      if (!ok) {
        alert(`Action failed: ${action}`);
        button.removeAttribute('disabled');
        return;
      }
      window.location.reload();
    } catch (error) {
      alert(`Action error: ${action}`);
      button.removeAttribute('disabled');
    }
  });
})();
""".strip()

    browse_sort_js = """
(function() {
  function asNumber(value) {
    const num = Number(value);
    return Number.isFinite(num) ? num : 0;
  }

  function naturalRank(node) {
    if (node.dataset.dgBumped === '1') return 0;
    if (node.dataset.dgPublished === '1') return 1;
    return 2;
  }

  function compareEntries(a, b, highlightsFirst) {
    if (highlightsFirst) {
      const aHl = a.dataset.dgHighlighted === '1' ? 0 : 1;
      const bHl = b.dataset.dgHighlighted === '1' ? 0 : 1;
      if (aHl !== bHl) return aHl - bHl;
    }

    const aNatural = naturalRank(a);
    const bNatural = naturalRank(b);
    if (aNatural !== bNatural) return aNatural - bNatural;

    const aSort = asNumber(a.dataset.dgSortMtime);
    const bSort = asNumber(b.dataset.dgSortMtime);
    if (aSort !== bSort) return bSort - aSort;

    const aName = a.dataset.dgName || '';
    const bName = b.dataset.dgName || '';
    return aName.localeCompare(bName);
  }

  document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.querySelector('[data-dg-sort-toggle]');
    const list = document.querySelector('ul.dg-index');
    if (!toggle || !list) return;

    const sortable = Array.from(list.querySelectorAll('li[data-dg-sortable=\"1\"]'));
    if (sortable.length === 0) {
      toggle.setAttribute('disabled', '');
      return;
    }

    let highlightsFirst = false;

    function renderOrder() {
      const sorted = [...sortable].sort((a, b) => compareEntries(a, b, highlightsFirst));
      for (const node of sorted) {
        list.appendChild(node);
      }
      toggle.textContent = highlightsFirst ? 'Highlights first: on' : 'Highlights first: off';
      toggle.classList.toggle('is-active', highlightsFirst);
      toggle.setAttribute('aria-pressed', highlightsFirst ? 'true' : 'false');
    }

    toggle.addEventListener('click', () => {
      highlightsFirst = !highlightsFirst;
      renderOrder();
    });

    renderOrder();
  });
})();
""".strip()

    css = """
/* Base styles for read pages and shared elements */
body { margin:14px 18px; font:14px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial; color:#222; }
header h1 { margin:6px 0 10px; font-weight:600; }
header nav a { color:#0a7; text-decoration:none; }
main { max-width: 1100px; }
.dg-list { list-style:none; padding-left:0; }
.dg-list li { padding:6px 0; border-bottom:1px solid #ececec; display:flex; justify-content:space-between; gap:10px; align-items:center; }
.dg-sub { color:#666; font-size:13px; }
.dg-actions { display:inline-flex; gap:6px; }
.dg-actions button, button[data-api-action] { padding:2px 6px; border:1px solid #ccc; border-radius:6px; background:#f7f7f7; color:#333; font:12px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial; cursor:pointer; }
.dg-actions button[disabled], button[data-api-action][disabled] { opacity:.6; pointer-events:none; }
""".strip()

    (assets_dir / "actions.js").write_text(js + "\n", encoding="utf-8")
    (assets_dir / "browse-sort.js").write_text(browse_sort_js + "\n", encoding="utf-8")
    (assets_dir / "site.css").write_text(css + "\n", encoding="utf-8")


def collect_category_items(base_dir: Path, category: str) -> list[BrowseItem]:
    """Compatibility helper used by tests (recursive file summary)."""
    roots = _category_roots(base_dir)
    root = roots[category]
    if not root.is_dir():
        return []

    published_state = load_published_state(base_dir)
    published_state_items = published_state.get("items", {})
    published_items = published_state_items if isinstance(published_state_items, dict) else {}
    bump_state = load_bump_state(base_dir)
    bump_items = bump_state.get("items", {}) if isinstance(bump_state.get("items", {}), dict) else {}

    items: list[BrowseItem] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel_to_root = path.relative_to(root)
        if any(_skip_directory(part) for part in rel_to_root.parts[:-1]):
            continue
        if not _is_visible_file_name(path.name):
            continue

        rel = rel_path_from_abs(base_dir, path)
        st = path.stat()
        published_entry = published_items.get(rel)
        published_at_mtime = None
        if isinstance(published_entry, dict):
            published_at_mtime = _published_at_to_epoch(published_entry.get("published_at"))
        is_published = rel in published_items

        bump_entry = bump_items.get(rel)
        bumped_mtime = None
        if isinstance(bump_entry, dict):
            try:
                bumped_mtime = float(bump_entry.get("bumped_mtime"))
            except Exception:
                bumped_mtime = None
        display_mtime = st.st_mtime
        effective_mtime = bumped_mtime
        if effective_mtime is None:
            if is_published and published_at_mtime is not None:
                effective_mtime = published_at_mtime
            else:
                effective_mtime = display_mtime
        items.append(
            BrowseItem(
                rel_path=rel,
                name=path.name,
                mtime=display_mtime,
                sort_mtime=effective_mtime,
                published=is_published,
                bumped=bumped_mtime is not None,
                highlighted=_is_highlighted(base_dir, rel),
            )
        )

    items.sort(
        key=lambda item: (
            0 if item.bumped else 1 if item.published else 2,
            -(item.sort_mtime if item.sort_mtime is not None else item.mtime),
            item.name.lower(),
        )
    )
    return items


def _category_roots(base_dir: Path) -> dict[str, Path]:
    roots = library_roots(base_dir)
    return {
        "posts": roots["posts"],
        "tweets": roots["tweets"],
        "pdfs": roots["pdfs"],
        "images": roots["images"],
        "podcasts": roots["podcasts"],
    }


def rebuild_browse_for_path(base_dir: Path, rel_path: str) -> dict[str, object]:
    """Incremental browse rebuild for one affected library file path.

    Rebuilds only the containing directory and its ancestors in the matching category.
    Falls back to full rebuild for unsupported paths.
    """
    ensure_assets(base_dir)
    _cleanup_obsolete_incoming_dir(base_dir)

    try:
        normalized = normalize_rel_path(rel_path)
    except Exception:
        counts = build_browse_site(base_dir)
        return {"mode": "full", "reason": "invalid_path", "counts": counts}

    category, rel_dir = _category_and_rel_dir(normalized)
    if category is None or rel_dir is None:
        counts = build_browse_site(base_dir)
        return {"mode": "full", "reason": "unsupported_root", "counts": counts}

    published_state = load_published_state(base_dir)
    published_state_items = published_state.get("items", {})
    published_items = published_state_items if isinstance(published_state_items, dict) else {}
    bump_state = load_bump_state(base_dir)
    bump_items = bump_state.get("items", {}) if isinstance(bump_state.get("items", {}), dict) else {}
    roots = _category_roots(base_dir)
    category_root = roots[category]
    visibility_cache: dict[str, bool] = {}

    dirs_to_update: list[Path] = []
    cursor = rel_dir
    while True:
        dirs_to_update.append(cursor)
        if cursor == Path("."):
            break
        cursor = cursor.parent

    updated_paths: list[str] = []
    for target_rel_dir in dirs_to_update:
        _write_category_directory_page(
            base_dir=base_dir,
            category=category,
            category_root=category_root,
            rel_dir=target_rel_dir,
            published_items=published_items,
            bump_items=bump_items,
            visibility_cache=visibility_cache,
        )
        updated_paths.append(_display_path_for_category_dir(category, target_rel_dir))

    return {
        "mode": "partial",
        "category": category,
        "updated": updated_paths,
    }


def build_browse_site(base_dir: Path) -> dict[str, int]:
    ensure_assets(base_dir)
    _cleanup_obsolete_incoming_dir(base_dir)

    published_state = load_published_state(base_dir)
    published_state_items = published_state.get("items", {})
    published_items = published_state_items if isinstance(published_state_items, dict) else {}
    bump_state = load_bump_state(base_dir)
    bump_items = bump_state.get("items", {}) if isinstance(bump_state.get("items", {}), dict) else {}
    roots = _category_roots(base_dir)

    counts: dict[str, int] = {}
    for category in CATEGORY_KEYS:
        counts[category] = _write_category_tree(
            base_dir=base_dir,
            category=category,
            category_root=roots[category],
            published_items=published_items,
            bump_items=bump_items,
        )

    _write_browse_home(base_dir, roots, counts)
    write_site_home(base_dir)
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate static browse pages for the local intranet site.")
    parser.add_argument("--base-dir", help="BASE_DIR containing Incoming/ Posts/ Tweets/ ...")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_dir = resolve_base_dir(args.base_dir)
    counts = build_browse_site(base_dir)
    print(f"✓ Generated browse pages in {site_root(base_dir) / 'browse'} ({counts})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
