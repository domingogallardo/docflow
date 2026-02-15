"""Generate static browse pages under BASE_DIR/_site/browse."""

from __future__ import annotations

import argparse
import html
import re
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

from utils.site_paths import raw_url_for_rel_path, rel_path_from_abs, resolve_base_dir, site_root
from utils.site_state import list_bumped, list_published

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

CATEGORY_DIRS = {
    "incoming": "Incoming",
    "posts": "Posts",
    "tweets": "Tweets",
    "pdfs": "Pdfs",
    "images": "Images",
}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".heic"}
HTML_EXTS = {".html", ".htm"}

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def fmt_date(ts: float) -> str:
    t = time.localtime(ts)
    return f"{t.tm_year}-{MONTHS[t.tm_mon-1]}-{t.tm_mday:02d} {t.tm_hour:02d}:{t.tm_min:02d}"


@dataclass(frozen=True)
class BrowseItem:
    rel_path: str
    name: str
    title: str | None
    mtime: float
    published: bool
    bumped: bool
    highlighted: bool


def _is_hidden(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def _guess_title(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in HTML_EXTS:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None
        match = _TITLE_RE.search(text)
        if not match:
            return None
        title = re.sub(r"\s+", " ", match.group(1)).strip()
        return title or None

    if suffix == ".md":
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        return stripped.lstrip("# ").strip() or None
        except Exception:
            return None

    return None


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
    if len(rel_parts) < 3:
        return False
    if rel_parts[0] != "Posts":
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


def _iter_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []

    files: list[Path] = []
    for path in root.rglob("*"):
        if _is_hidden(path.relative_to(root)):
            continue
        if path.is_file():
            files.append(path)
    return files


def collect_category_items(base_dir: Path, category: str) -> list[BrowseItem]:
    dirname = CATEGORY_DIRS[category]
    root = base_dir / dirname

    published = list_published(base_dir)
    bumped = list_bumped(base_dir)

    items: list[BrowseItem] = []
    for file_path in _iter_files(root):
        rel = rel_path_from_abs(base_dir, file_path)
        st = file_path.stat()
        items.append(
            BrowseItem(
                rel_path=rel,
                name=file_path.name,
                title=_guess_title(file_path),
                mtime=st.st_mtime,
                published=rel in published,
                bumped=rel in bumped,
                highlighted=_is_highlighted(base_dir, rel),
            )
        )

    items.sort(key=lambda item: item.mtime, reverse=True)
    return items


def _icon_for(item: BrowseItem) -> str:
    lower = item.name.lower()
    if lower.endswith(".pdf"):
        return "📕"
    if lower.endswith((".html", ".htm")):
        return "📄"
    if Path(lower).suffix in IMAGE_EXTS:
        return "🖼️"
    if lower.endswith(".md"):
        return "📝"
    return "📦"


def _status_text(item: BrowseItem) -> str:
    parts: list[str] = []
    if item.published:
        parts.append("published")
    if item.bumped:
        parts.append("bumped")
    if item.highlighted:
        parts.append("highlighted")
    return ", ".join(parts) if parts else "-"


def _actions_html(item: BrowseItem) -> str:
    pub_action = "unpublish" if item.published else "publish"
    pub_label = "Unpublish" if item.published else "Publish"
    bump_action = "unbump" if item.bumped else "bump"
    bump_label = "Unbump" if item.bumped else "Bump"

    path_attr = html.escape(item.rel_path, quote=True)
    return (
        f"<button data-api-action=\"{pub_action}\" data-docflow-path=\"{path_attr}\">{pub_label}</button>"
        f"<button data-api-action=\"{bump_action}\" data-docflow-path=\"{path_attr}\">{bump_label}</button>"
    )


def _render_items(items: list[BrowseItem]) -> str:
    if not items:
        return "<p>No files found.</p>"

    lines = ["<ul class=\"dg-list\">"]
    for item in items:
        link = raw_url_for_rel_path(item.rel_path)
        title = f"<div class=\"dg-sub\">{html.escape(item.title)}</div>" if item.title else ""
        status = html.escape(_status_text(item))
        lines.append(
            "<li>"
            f"<div class=\"dg-main\"><span class=\"dg-ico\">{_icon_for(item)}</span>"
            f"<a href=\"{link}\" target=\"_blank\" rel=\"noopener\">{html.escape(item.name)}</a>"
            f"<div class=\"dg-sub\">{html.escape(item.rel_path)}</div>"
            f"{title}"
            f"<div class=\"dg-sub\">mtime: {fmt_date(item.mtime)} · state: {status}</div>"
            "</div>"
            f"<div class=\"dg-actions\">{_actions_html(item)}</div>"
            "</li>"
        )
    lines.append("</ul>")
    return "\n".join(lines)


def _page_shell(*, title: str, heading: str, body: str, back_href: str = "/") -> str:
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<link rel=\"stylesheet\" href=\"/assets/site.css\">"
        "<script src=\"/assets/actions.js\" defer></script>"
        f"<title>{html.escape(title)}</title></head><body>"
        "<header><h1>{}</h1><nav><a href=\"{}\">Home</a> · <a href=\"/browse/\">Browse</a> · "
        "<a href=\"/read/\">Read</a></nav></header>"
        "<main>{}</main>"
        "</body></html>"
    ).format(html.escape(heading), html.escape(back_href, quote=True), body)


def ensure_assets(base_dir: Path) -> None:
    assets_dir = site_root(base_dir) / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    css = """
:root {
  color-scheme: light;
  --bg: #f8f7f3;
  --card: #ffffff;
  --ink: #222222;
  --muted: #666666;
  --line: #d8d5cc;
  --accent: #0a6e4f;
}
body { margin: 0; background: radial-gradient(circle at top right, #efe9d9, var(--bg)); color: var(--ink); font: 15px/1.45 'Avenir Next', 'Segoe UI', sans-serif; }
header { padding: 18px 22px; border-bottom: 1px solid var(--line); position: sticky; top: 0; backdrop-filter: blur(8px); background: color-mix(in srgb, var(--bg) 84%, white); }
header h1 { margin: 0 0 6px; font-size: 22px; }
header nav a { color: var(--accent); text-decoration: none; }
main { padding: 18px 22px 40px; max-width: 1080px; }
.dg-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; }
.dg-card { border: 1px solid var(--line); border-radius: 10px; background: var(--card); padding: 12px; }
.dg-list { list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }
.dg-list li { border: 1px solid var(--line); border-radius: 10px; background: var(--card); padding: 10px; display: grid; gap: 8px; }
.dg-main a { color: var(--accent); text-decoration: none; font-weight: 600; }
.dg-sub { color: var(--muted); font-size: 13px; }
.dg-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.dg-actions button, .dg-rebuild { border: 1px solid var(--line); background: #f7f7f7; border-radius: 7px; padding: 6px 10px; cursor: pointer; }
.dg-actions button[disabled], .dg-rebuild[disabled] { opacity: 0.6; cursor: progress; }
.dg-ico { margin-right: 6px; }
""".strip()

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

    (assets_dir / "site.css").write_text(css + "\n", encoding="utf-8")
    (assets_dir / "actions.js").write_text(js + "\n", encoding="utf-8")


def write_category_page(base_dir: Path, category: str, items: list[BrowseItem]) -> Path:
    out_dir = site_root(base_dir) / "browse" / category
    out_dir.mkdir(parents=True, exist_ok=True)
    body = _render_items(items)
    page = _page_shell(title=f"Browse {category}", heading=f"Browse / {category}", body=body, back_href="/browse/")
    output = out_dir / "index.html"
    output.write_text(page, encoding="utf-8")
    return output


def write_browse_home(base_dir: Path, counts: dict[str, int]) -> Path:
    out_dir = site_root(base_dir) / "browse"
    out_dir.mkdir(parents=True, exist_ok=True)

    cards: list[str] = ["<div class=\"dg-grid\">"]
    for category in CATEGORY_DIRS:
        cards.append(
            "<article class=\"dg-card\">"
            f"<h2><a href=\"/browse/{category}/\">{category.title()}</a></h2>"
            f"<p>{counts.get(category, 0)} files</p>"
            "</article>"
        )
    cards.append("</div>")

    cards.append('<p><button class="dg-rebuild" data-api-action="rebuild">Rebuild all indexes</button></p>')

    page = _page_shell(title="Browse", heading="Browse", body="\n".join(cards), back_href="/")
    output = out_dir / "index.html"
    output.write_text(page, encoding="utf-8")
    return output


def write_site_home(base_dir: Path) -> Path:
    out_dir = site_root(base_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    body = (
        '<div class="dg-grid">'
        '<article class="dg-card"><h2><a href="/browse/">Browse</a></h2><p>Complete library navigation.</p></article>'
        '<article class="dg-card"><h2><a href="/read/">Read</a></h2><p>Curated published view.</p></article>'
        "</div>"
        '<p><button class="dg-rebuild" data-api-action="rebuild">Rebuild browse + read</button></p>'
    )

    page = _page_shell(title="Docflow", heading="Docflow Intranet", body=body)
    output = out_dir / "index.html"
    output.write_text(page, encoding="utf-8")
    return output


def build_browse_site(base_dir: Path) -> dict[str, int]:
    ensure_assets(base_dir)

    counts: dict[str, int] = {}
    for category in CATEGORY_DIRS:
        items = collect_category_items(base_dir, category)
        write_category_page(base_dir, category, items)
        counts[category] = len(items)

    write_browse_home(base_dir, counts)
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
