from pathlib import Path

from utils import build_read_index
from utils import site_state


def test_write_site_read_index_uses_published_state(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    html = posts / "doc.html"
    html.write_text("<html><body>Doc</body></html>", encoding="utf-8")

    site_state.publish_path(base, "Posts/Posts 2026/doc.html")
    site_state.set_bumped_path(base, "Posts/Posts 2026/doc.html", original_mtime=1.0, bumped_mtime=2.0)

    out = build_read_index.write_site_read_index(base)

    assert out == base / "_site" / "read" / "index.html"
    assert out.exists()

    content = out.read_text(encoding="utf-8")
    assert "/posts/raw/Posts%202026/doc.html" in content
    assert 'data-api-action="unpublish"' in content
    assert 'data-api-action="unbump"' in content
    assert "Posts/Posts 2026/doc.html" in content


def test_build_read_index_legacy_mode_still_generates_read_html(tmp_path: Path):
    (tmp_path / "a.html").write_text("<p>A</p>", encoding="utf-8")

    exit_code = build_read_index.main(["build_read_index.py", str(tmp_path)])

    assert exit_code == 0
    assert (tmp_path / "read.html").exists()
