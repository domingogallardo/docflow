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
    highlight_store.save_highlights_for_path(
        base,
        "Posts/Posts 2026/doc.html",
        {"highlights": [{"id": "h1", "text": "Doc"}]},
    )

    out = build_done_index.write_site_done_index(base)
    content = out.read_text(encoding="utf-8")

    assert out == base / "_site" / "done" / "index.html"
    assert "/posts/raw/Posts%202026/doc.html" in content
    assert '<a href="/working/">Working</a>' in content
    assert "<h1>Done</h1>" in content
    assert "🟡 highlight" in content
    assert "data-dg-sort-toggle" in content
    assert "Highlight: off" in content
    assert "data-dg-highlighted='1'" in content
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
