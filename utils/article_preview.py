"""Shared summary metadata and assets for library list previews."""
from pathlib import Path
import html

from utils.markdown_utils import split_front_matter
from utils.site_paths import static_asset_url


def summary_for_path(path: Path) -> str:
    """Read an existing summary without generating or modifying content."""
    md_path = path if path.suffix.lower() == ".md" else path.with_suffix(".md")
    try:
        meta, _ = split_front_matter(md_path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return ""
    return str(meta.get("docflow_summary") or "").strip()


def preview_attributes(summary: str) -> str:
    return f' data-dg-summary="{html.escape(summary, quote=True)}"' if summary else ""


def preview_head() -> str:
    return (
        f'<link rel="stylesheet" href="{static_asset_url("article-preview.css")}">'
        f'<script src="{static_asset_url("article-preview.js")}" defer></script>'
    )
