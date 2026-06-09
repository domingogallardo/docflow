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
    saved_highlights = highlight_store.save_highlights_for_path(
        base,
        "Posts/Posts 2026/doc.html",
        {
            "updated_at": "2026-02-03T10:06:00Z",
            "highlights": [{"id": "h1", "text": "Doc", "created_at": "2026-02-03T10:05:00Z"}],
        },
    )

    out = build_reading_index.write_site_reading_index(base)

    assert out == base / "_site" / "reading" / "index.html"
    assert out.exists()

    content = out.read_text(encoding="utf-8")
    assert "/posts/raw/Posts%202026/doc.html" in content
    assert '<a href="/browse/">Browse</a>' in content
    assert '<a href="/reading/">Reading</a>' in content
    assert '<a href="/done/">Done</a>' in content
    assert "<title>Reading (1)</title>" in content
    assert "<h1>Reading (1)</h1>" in content
    assert "🟡 highlight" in content
    assert "data-dg-sort-toggle" in content
    assert 'data-dg-sort-direction="desc"' in content
    assert "Highlight: off" in content
    assert "data-dg-sortable='1'" in content
    assert "data-dg-highlighted='1'" in content
    assert f"data-dg-highlight-last='{highlight_store.latest_highlight_epoch(saved_highlights):.6f}'" in content
    assert "data-dg-sort-mtime=" in content
    assert '<script src="/assets/browse-sort.js?v=20260609-scroll-restore" defer></script>' in content
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

    assert content.find("newer.html") < content.find("older.html")


def test_site_reading_orders_by_last_read_activity(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    added_older = posts / "added-older.html"
    added_newer = posts / "added-newer.html"
    added_older.write_text("<html><body>Added older</body></html>", encoding="utf-8")
    added_newer.write_text("<html><body>Added newer</body></html>", encoding="utf-8")
    added_older.with_suffix(".md").write_text(
        "---\ndocflow_last_read: 2026-02-02T10:00:00Z\n---\n\n# Added older\n",
        encoding="utf-8",
    )
    added_newer.with_suffix(".md").write_text(
        "---\ndocflow_last_read: 2026-02-01T10:00:00Z\n---\n\n# Added newer\n",
        encoding="utf-8",
    )

    reading_times = iter(["2026-02-01T10:00:00Z", "2026-02-01T10:00:05Z"])
    monkeypatch.setattr(site_state, "_utc_now_iso", lambda: next(reading_times))

    site_state.set_reading_path(base, "Posts/Posts 2026/added-older.html")
    site_state.set_reading_path(base, "Posts/Posts 2026/added-newer.html")

    out = build_reading_index.write_site_reading_index(base)
    content = out.read_text(encoding="utf-8")

    assert content.find("added-older.html") < content.find("added-newer.html")


def test_build_reading_index_cli_generates_site_index(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    (posts / "doc.html").write_text("<html><body>Doc</body></html>", encoding="utf-8")
    site_state.set_reading_path(base, "Posts/Posts 2026/doc.html")

    exit_code = build_reading_index.main(["build_reading_index.py", "--base-dir", str(base)])

    assert exit_code == 0
    assert (base / "_site" / "reading" / "index.html").exists()


def test_reading_index_links_pdfs_without_list_actions(tmp_path: Path):
    base = tmp_path / "base"
    pdfs = base / "Pdfs" / "Pdfs 2026"
    pdfs.mkdir(parents=True)
    pdf = pdfs / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    site_state.set_reading_path(base, "Pdfs/Pdfs 2026/paper.pdf")

    out = build_reading_index.write_site_reading_index(base)
    content = out.read_text(encoding="utf-8")

    assert "/pdfs/view/Pdfs%202026/paper.pdf" in content
    assert 'data-api-action="to-done"' not in content
    assert 'data-api-action="to-browse"' not in content
    assert 'data-docflow-path="Pdfs/Pdfs 2026/paper.pdf"' not in content
