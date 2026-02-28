import os
from pathlib import Path

from utils import build_reading_index
from utils import highlight_store
from utils import site_state


def test_write_site_reading_index_uses_reading_state(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    html = posts / "doc.html"
    html.write_text("<html><body>Doc</body></html>", encoding="utf-8")

    site_state.set_reading_path(base, "Posts/Posts 2026/doc.html")
    highlight_store.save_highlights_for_path(
        base,
        "Posts/Posts 2026/doc.html",
        {"highlights": [{"id": "h1", "text": "Doc"}]},
    )

    out = build_reading_index.write_site_reading_index(base)

    assert out == base / "_site" / "reading" / "index.html"
    assert out.exists()

    content = out.read_text(encoding="utf-8")
    assert "/posts/raw/Posts%202026/doc.html" in content
    assert '<a href="/browse/">Browse</a>' in content
    assert '<a href="/reading/">Reading</a>' in content
    assert '<a href="/working/">Working</a>' in content
    assert '<a href="/done/">Done</a>' in content
    assert "<title>Reading (1)</title>" in content
    assert "<h1>Reading (1)</h1>" in content
    assert "🟡 highlight" in content
    assert "data-dg-sort-toggle" in content
    assert 'data-dg-sort-direction="asc"' in content
    assert "Highlight: off" in content
    assert "data-dg-sortable='1'" in content
    assert "data-dg-highlighted='1'" in content
    assert "data-dg-sort-mtime=" in content
    assert "<script src=\"/assets/browse-sort.js\" defer></script>" in content
    assert "🟡" in content
    assert "Posts/Posts 2026/doc.html" not in content


def test_site_reading_orders_by_reading_time(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    older = posts / "older.html"
    newer = posts / "newer.html"
    older.write_text("<html><body>Older</body></html>", encoding="utf-8")
    newer.write_text("<html><body>Newer</body></html>", encoding="utf-8")

    # Keep file mtime inverse to reading order to assert reading time wins.
    os.utime(older, (1_700_000_500, 1_700_000_500))
    os.utime(newer, (1_700_000_100, 1_700_000_100))

    reading_times = iter(["2026-02-01T10:00:00Z", "2026-02-01T10:00:05Z"])
    monkeypatch.setattr(site_state, "_utc_now_iso", lambda: next(reading_times))

    site_state.set_reading_path(base, "Posts/Posts 2026/older.html")
    site_state.set_reading_path(base, "Posts/Posts 2026/newer.html")

    out = build_reading_index.write_site_reading_index(base)
    content = out.read_text(encoding="utf-8")

    assert content.find("older.html") < content.find("newer.html")


def test_build_reading_index_cli_generates_site_index(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    (posts / "doc.html").write_text("<html><body>Doc</body></html>", encoding="utf-8")
    site_state.set_reading_path(base, "Posts/Posts 2026/doc.html")

    exit_code = build_reading_index.main(["build_reading_index.py", "--base-dir", str(base)])

    assert exit_code == 0
    assert (base / "_site" / "reading" / "index.html").exists()


def test_reading_index_shows_state_actions_for_pdfs(tmp_path: Path):
    base = tmp_path / "base"
    pdfs = base / "Pdfs" / "Pdfs 2026"
    pdfs.mkdir(parents=True)
    pdf = pdfs / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    site_state.set_reading_path(base, "Pdfs/Pdfs 2026/paper.pdf")

    out = build_reading_index.write_site_reading_index(base)
    content = out.read_text(encoding="utf-8")

    assert "/pdfs/raw/Pdfs%202026/paper.pdf" in content
    assert 'data-api-action="to-working"' in content
    assert 'data-api-action="to-done"' in content
    assert 'data-api-action="to-browse"' in content
    assert 'data-docflow-path="Pdfs/Pdfs 2026/paper.pdf"' in content
