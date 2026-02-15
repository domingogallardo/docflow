"""Generate static browse pages under BASE_DIR/_site/browse.

The generated browse UI intentionally mirrors the look of `utils/serve_docs.py`
directory listings while keeping pages static.
"""

from __future__ import annotations

import argparse
import html
import os
import time
from dataclasses import dataclass
from pathlib import Path
import sys
from urllib.parse import quote

# Support direct execution: `python utils/build_browse_index.py ...`
if __package__ in (None, ""):
    _REPO_ROOT = Path(__file__).resolve().parents[1]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from utils.site_paths import library_roots, raw_url_for_rel_path, rel_path_from_abs, resolve_base_dir, site_root
from utils.site_state import load_bump_state, list_published

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

CATEGORY_KEYS = ("incoming", "posts", "tweets", "pdfs", "images")
CATEGORY_LABELS = {
    "incoming": "Incoming",
    "posts": "Posts",
    "tweets": "Tweets",
    "pdfs": "Pdfs",
    "images": "Images",
}

SKIP_DIR_NAMES = {"highlights", "__pycache__"}


@dataclass(frozen=True)
class BrowseItem:
    rel_path: str
    name: str
    mtime: float
    published: bool
    bumped: bool
    highlighted: bool


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


def fmt_date(ts: float) -> str:
    t = time.localtime(ts)
    return f"{t.tm_year}-{MONTHS[t.tm_mon-1]}-{t.tm_mday:02d} {t.tm_hour:02d}:{t.tm_min:02d}"


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


def _is_highlighted(base_dir: Path, rel_path: str) -> bool:
    rel_parts = Path(rel_path).parts
    if len(rel_parts) < 3 or rel_parts[0] != "Posts":
        return False

    low_name = rel_parts[-1].lower()
    if not low_name.endswith((".html", ".htm")):
        return False

    parent = base_dir / Path(*rel_parts[:-1])
    highlights_dir = parent / "highlights"
    if not highlights_dir.is_dir():
        return False

    filename = rel_parts[-1]
    for encoded in _highlight_name_candidates(filename):
        if (highlights_dir / f"{encoded}.json").is_file():
            return True
    return False


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
    date_html = f"<span class='dg-date'> — {fmt_date(entry.mtime)}</span>"

    prefix = (
        ("🔥 " if entry.bumped else "")
        + ("🟢 " if entry.published else "")
        + ("🟡 " if entry.highlighted else "")
        + entry.icon
    )
    cls_attr = _entry_classes(entry)
    actions = _actions_html(entry)
    return (
        f"<li{cls_attr}><span>{prefix}<a href=\"{entry.href}\">{esc_name}</a>{date_html}</span>{actions}</li>"
    )


def _base_head(title: str) -> str:
    return (
        f"<html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
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
        ".dg-date{color:#666;margin-left:10px;white-space:nowrap}"
        "</style>"
        "<script src='/assets/actions.js' defer></script>"
        "</head><body>"
    )


def _render_directory_page(*, title: str, display_path: str, entries: list[BrowseEntry], parent_href: str | None) -> str:
    rows: list[str] = [_base_head(title)]
    rows.append("<div class='dg-nav'><a href='/'>Home</a> · <a href='/browse/'>Browse</a> · <a href='/read/'>Read</a></div>")
    rows.append(f"<h2>Index of {html.escape(display_path)}</h2>")
    rows.append("<div class='dg-legend'>🔥 bumped · 🟢 published · 🟡 highlight</div><hr><ul class='dg-index'>")

    if parent_href:
        rows.append(f'<li><a href="{parent_href}">../</a></li>')

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


def _scan_directory(
    *,
    base_dir: Path,
    abs_dir: Path,
    published_set: set[str],
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
                bump_entry = bump_items.get(rel)
                bumped_mtime = None
                if isinstance(bump_entry, dict):
                    try:
                        bumped_mtime = float(bump_entry.get("bumped_mtime"))
                    except Exception:
                        bumped_mtime = None
                effective_mtime = bumped_mtime if bumped_mtime is not None else st.st_mtime
                bumped = bumped_mtime is not None
                entries.append(
                    BrowseEntry(
                        name=name,
                        href=raw_url_for_rel_path(rel),
                        mtime=effective_mtime,
                        is_dir=False,
                        icon=_icon_for_filename(name),
                        rel_path=rel,
                        published=rel in published_set,
                        bumped=bumped,
                        highlighted=_is_highlighted(base_dir, rel),
                    )
                )
    except OSError:
        return [], [], 0

    entries.sort(key=lambda item: item.mtime, reverse=True)
    child_dirs.sort()
    return entries, child_dirs, file_count


def _write_category_tree(
    *,
    base_dir: Path,
    category: str,
    category_root: Path,
    published_set: set[str],
    bump_items: dict[str, dict],
) -> int:
    out_root = site_root(base_dir) / "browse" / category
    out_root.mkdir(parents=True, exist_ok=True)

    visibility_cache: dict[str, bool] = {}

    if not category_root.is_dir():
        html_doc = _render_directory_page(
            title=f"Index of /browse/{category}/",
            display_path=f"/browse/{category}/",
            entries=[],
            parent_href="../",
        )
        (out_root / "index.html").write_text(html_doc, encoding="utf-8")
        return 0

    def walk(rel_dir: Path) -> int:
        abs_dir = category_root / rel_dir
        out_dir = out_root / rel_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        entries, child_dirs, direct_files = _scan_directory(
            base_dir=base_dir,
            abs_dir=abs_dir,
            published_set=published_set,
            bump_items=bump_items,
            visibility_cache=visibility_cache,
        )

        if rel_dir == Path("."):
            display_path = f"/browse/{category}/"
        else:
            display_path = f"/browse/{category}/{rel_dir.as_posix()}/"

        html_doc = _render_directory_page(
            title=f"Index of {display_path}",
            display_path=display_path,
            entries=entries,
            parent_href="../",
        )
        (out_dir / "index.html").write_text(html_doc, encoding="utf-8")

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
                name=f"{label} ({count})",
                href=f"{category}/",
                mtime=mtime,
                is_dir=True,
                icon="📁 ",
            )
        )

    entries.sort(key=lambda item: item.mtime, reverse=True)
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


def write_site_home(base_dir: Path) -> Path:
    out_dir = site_root(base_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    html_doc = (
        "<html><head><meta charset='utf-8'><title>Docflow</title>"
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
    return output


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
    (assets_dir / "site.css").write_text(css + "\n", encoding="utf-8")


def collect_category_items(base_dir: Path, category: str) -> list[BrowseItem]:
    """Compatibility helper used by tests (recursive file summary)."""
    roots = _category_roots(base_dir)
    root = roots[category]
    if not root.is_dir():
        return []

    published_set = list_published(base_dir)
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
        bump_entry = bump_items.get(rel)
        bumped_mtime = None
        if isinstance(bump_entry, dict):
            try:
                bumped_mtime = float(bump_entry.get("bumped_mtime"))
            except Exception:
                bumped_mtime = None
        effective_mtime = bumped_mtime if bumped_mtime is not None else st.st_mtime
        items.append(
            BrowseItem(
                rel_path=rel,
                name=path.name,
                mtime=effective_mtime,
                published=rel in published_set,
                bumped=bumped_mtime is not None,
                highlighted=_is_highlighted(base_dir, rel),
            )
        )

    items.sort(key=lambda item: item.mtime, reverse=True)
    return items


def _category_roots(base_dir: Path) -> dict[str, Path]:
    roots = library_roots(base_dir)
    return {
        "incoming": roots["incoming"],
        "posts": roots["posts"],
        "tweets": roots["tweets"],
        "pdfs": roots["pdfs"],
        "images": roots["images"],
    }


def build_browse_site(base_dir: Path) -> dict[str, int]:
    ensure_assets(base_dir)

    published_set = list_published(base_dir)
    bump_state = load_bump_state(base_dir)
    bump_items = bump_state.get("items", {}) if isinstance(bump_state.get("items", {}), dict) else {}
    roots = _category_roots(base_dir)

    counts: dict[str, int] = {}
    for category in CATEGORY_KEYS:
        counts[category] = _write_category_tree(
            base_dir=base_dir,
            category=category,
            category_root=roots[category],
            published_set=published_set,
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
