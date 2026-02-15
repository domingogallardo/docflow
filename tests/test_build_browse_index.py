from pathlib import Path

from utils import build_browse_index
from utils import site_state


def test_build_browse_site_generates_indexes_and_actions(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    html = posts / "doc.html"
    html.write_text("<html><title>Sample Title</title><body>Doc</body></html>", encoding="utf-8")
    md = posts / "doc.md"
    md.write_text("# Markdown sibling\\n", encoding="utf-8")

    pdfs = base / "Pdfs" / "Pdfs 2026"
    pdfs.mkdir(parents=True)
    pdf = pdfs / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    site_state.publish_path(base, "Posts/Posts 2026/doc.html")
    site_state.set_bumped_path(base, "Posts/Posts 2026/doc.html", original_mtime=10.0, bumped_mtime=20.0)

    counts = build_browse_index.build_browse_site(base)

    assert counts["posts"] == 1
    assert counts["pdfs"] == 1

    browse_home = base / "_site" / "browse" / "index.html"
    posts_root_page = base / "_site" / "browse" / "posts" / "index.html"
    posts_year_page = base / "_site" / "browse" / "posts" / "Posts 2026" / "index.html"
    pdfs_year_page = base / "_site" / "browse" / "pdfs" / "Pdfs 2026" / "index.html"
    assets_js = base / "_site" / "assets" / "actions.js"

    assert browse_home.exists()
    assert posts_root_page.exists()
    assert posts_year_page.exists()
    assert pdfs_year_page.exists()
    assert assets_js.exists()

    root_content = posts_root_page.read_text(encoding="utf-8")
    assert "Posts 2026/" in root_content

    content = posts_year_page.read_text(encoding="utf-8")
    assert "Sample Title" in content
    assert "doc.md" not in content
    assert 'data-api-action="unpublish"' not in content
    assert 'data-api-action="unbump"' not in content
    assert '/posts/raw/Posts%202026/doc.html' in content

    pdf_content = pdfs_year_page.read_text(encoding="utf-8")
    assert 'data-api-action="publish"' in pdf_content or 'data-api-action="unpublish"' in pdf_content
    assert 'data-api-action="bump"' in pdf_content or 'data-api-action="unbump"' in pdf_content


def test_collect_category_items_handles_missing_dirs(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()

    items = build_browse_index.collect_category_items(base, "images")
    assert items == []
