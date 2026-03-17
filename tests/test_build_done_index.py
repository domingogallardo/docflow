from pathlib import Path

from utils import build_done_index
from utils import highlight_store
from utils import site_state

def test_write_site_done_index_uses_done_state(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    html = posts / "doc.html"
    html.write_text("<html><body>Doc</body></html>", encoding="utf-8")

    site_state.set_done_path(base, "Posts/Posts 2026/doc.html")
    saved_highlights = highlight_store.save_highlights_for_path(
        base,
        "Posts/Posts 2026/doc.html",
        {
            "updated_at": "2026-02-03T10:06:00Z",
            "highlights": [{"id": "h1", "text": "Doc", "created_at": "2026-02-03T10:05:00Z"}],
        },
    )

    out = build_done_index.write_site_done_index(base)
    content = out.read_text(encoding="utf-8")

    assert out == base / "_site" / "done" / "index.html"
    assert "/posts/raw/Posts%202026/doc.html" in content
    assert '<a href="/reading/">Reading</a>' in content
    assert '<a href="/working/">Working</a>' in content
    assert "<h1>Done</h1>" in content
    assert "🟡 highlight" in content
    assert "data-dg-sort-toggle" in content
    assert "Highlight: off" in content
    assert "data-dg-highlighted='1'" in content
    assert f"data-dg-highlight-last='{highlight_store.latest_highlight_epoch(saved_highlights):.6f}'" in content
    assert "data-dg-group-year='2026'" in content
    assert 'data-dg-highlight-view="default"' in content
    assert 'data-dg-highlight-view="highlight"' in content
    assert "data-dg-sort-mtime=" in content
    assert "data-dg-working" not in content
    assert "data-dg-done" not in content
    assert "🟡" in content


def test_done_items_order_by_done_time(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    (posts / "a.html").write_text("<html><body>A</body></html>", encoding="utf-8")
    (posts / "b.html").write_text("<html><body>B</body></html>", encoding="utf-8")

    done_times = iter(["2026-02-01T10:00:00Z", "2026-02-01T10:00:05Z"])
    monkeypatch.setattr(site_state, "_utc_now_iso", lambda: next(done_times))
    site_state.set_done_path(base, "Posts/Posts 2026/a.html")
    site_state.set_done_path(base, "Posts/Posts 2026/b.html")

    out = build_done_index.write_site_done_index(base)
    content = out.read_text(encoding="utf-8")

    assert '<h2 class="dg-year">2026</h2>' in content
    assert content.find("b.html") < content.find("a.html")


def test_build_done_index_cli_generates_site_index(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    (posts / "doc.html").write_text("<html><body>Doc</body></html>", encoding="utf-8")
    site_state.set_done_path(base, "Posts/Posts 2026/doc.html")

    exit_code = build_done_index.main(["build_done_index.py", "--base-dir", str(base)])

    assert exit_code == 0
    assert (base / "_site" / "done" / "index.html").exists()


def test_done_index_shows_state_actions_for_pdfs(tmp_path: Path):
    base = tmp_path / "base"
    pdfs = base / "Pdfs" / "Pdfs 2026"
    pdfs.mkdir(parents=True)
    pdf = pdfs / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    site_state.set_done_path(base, "Pdfs/Pdfs 2026/paper.pdf")

    out = build_done_index.write_site_done_index(base)
    content = out.read_text(encoding="utf-8")

    assert "/pdfs/raw/Pdfs%202026/paper.pdf" in content
    assert 'data-api-action="reopen"' in content
    assert 'data-api-action="to-browse"' in content
    assert 'data-docflow-path="Pdfs/Pdfs 2026/paper.pdf"' in content


def test_done_index_groups_items_by_done_year_headers(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts_2025 = base / "Posts" / "Posts 2025"
    posts_2026 = base / "Posts" / "Posts 2026"
    posts_2025.mkdir(parents=True)
    posts_2026.mkdir(parents=True)
    (posts_2025 / "old.html").write_text("<html><body>Old</body></html>", encoding="utf-8")
    (posts_2026 / "new.html").write_text("<html><body>New</body></html>", encoding="utf-8")

    done_times = iter(["2026-01-01T10:00:00Z", "2026-01-02T10:00:00Z"])
    monkeypatch.setattr(site_state, "_utc_now_iso", lambda: next(done_times))
    site_state.set_done_path(base, "Posts/Posts 2025/old.html")
    site_state.set_done_path(base, "Posts/Posts 2026/new.html")

    out = build_done_index.write_site_done_index(base)
    content = out.read_text(encoding="utf-8")

    assert '<h2 class="dg-year">2026</h2>' in content
    assert '<h2 class="dg-year">2025</h2>' not in content
    assert content.find("new.html") < content.find("old.html")


def test_done_index_falls_back_to_path_year_when_done_at_missing(tmp_path: Path):
    base = tmp_path / "base"
    posts_2025 = base / "Posts" / "Posts 2025"
    posts_2025.mkdir(parents=True)
    (posts_2025 / "legacy.html").write_text("<html><body>Legacy</body></html>", encoding="utf-8")

    site_state.save_done_state(
        base,
        {"version": site_state.STATE_VERSION, "items": {"Posts/Posts 2025/legacy.html": {}}},
    )

    out = build_done_index.write_site_done_index(base)
    content = out.read_text(encoding="utf-8")

    assert '<h2 class="dg-year">2025</h2>' in content
    assert "legacy.html" in content


def test_done_highlight_view_promotes_old_item_to_highlight_year(tmp_path: Path):
    base = tmp_path / "base"
    posts_2024 = base / "Posts" / "Posts 2024"
    posts_2024.mkdir(parents=True)
    (posts_2024 / "legacy.html").write_text("<html><body>Legacy</body></html>", encoding="utf-8")

    site_state.save_done_state(
        base,
        {"version": site_state.STATE_VERSION, "items": {"Posts/Posts 2024/legacy.html": {}}},
    )
    highlight_store.save_highlights_for_path(
        base,
        "Posts/Posts 2024/legacy.html",
        {
            "updated_at": "2026-03-17T10:05:00Z",
            "highlights": [{"id": "h1", "text": "Legacy", "created_at": "2026-03-17T10:05:00Z"}],
        },
    )

    out = build_done_index.write_site_done_index(base)
    content = out.read_text(encoding="utf-8")

    default_view = content.split('data-dg-highlight-view="default"', 1)[1].split('data-dg-highlight-view="highlight"', 1)[0]
    highlight_view = content.split('data-dg-highlight-view="highlight"', 1)[1]

    assert '<h2 class="dg-year">2024</h2>' in default_view
    assert "legacy.html" in default_view
    assert "data-dg-group-year='2024'" in highlight_view
    assert '<h2 class="dg-year">2026</h2>' in highlight_view
    assert highlight_view.find('<h2 class="dg-year">2026</h2>') < highlight_view.find("legacy.html")
