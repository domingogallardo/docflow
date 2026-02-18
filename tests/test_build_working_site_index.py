import os
from pathlib import Path

from utils import build_working_index
from utils import highlight_store
from utils import site_state


def test_write_site_working_index_uses_working_state(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    html = posts / "doc.html"
    html.write_text("<html><body>Doc</body></html>", encoding="utf-8")

    site_state.set_working_path(base, "Posts/Posts 2026/doc.html")
    highlight_store.save_highlights_for_path(
        base,
        "Posts/Posts 2026/doc.html",
        {"highlights": [{"id": "h1", "text": "Doc"}]},
    )

    out = build_working_index.write_site_working_index(base)

    assert out == base / "_site" / "working" / "index.html"
    assert out.exists()

    content = out.read_text(encoding="utf-8")
    assert "/posts/raw/Posts%202026/doc.html" in content
    assert '<a href="/browse/">Browse</a>' in content
    assert '<a href="/done/">Done</a>' in content
    assert "<h1>Working</h1>" in content
    assert "🟡 highlight" in content
    assert "data-dg-sort-toggle" not in content
    assert "<h2>Tweets</h2>" not in content
    assert "github.com/domingogallardo/docflow" not in content
    assert "domingogallardo.com" not in content
    assert "🟡" in content
    assert "🔥" not in content
    assert 'class="dg-bump"' not in content
    assert "Posts/Posts 2026/doc.html" not in content
    assert "data-api-action" not in content
    assert (base / "_site" / "working" / "article.js").exists()


def test_write_site_working_index_keeps_tweets_in_main_list_and_removes_old_tweet_pages(tmp_path: Path):
    base = tmp_path / "base"
    tweets_dir = base / "Tweets" / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    tweet_html = tweets_dir / "Tweets 2026-01-02.html"
    tweet_html.write_text("<html><body>tweets</body></html>", encoding="utf-8")
    site_state.set_working_path(base, "Tweets/Tweets 2026/Tweets 2026-01-02.html")

    stale_pages_dir = base / "_site" / "working" / "tweets"
    stale_pages_dir.mkdir(parents=True)
    (stale_pages_dir / "2026.html").write_text("<p>stale</p>", encoding="utf-8")

    out = build_working_index.write_site_working_index(base)
    content = out.read_text(encoding="utf-8")

    assert "/tweets/raw/Tweets%202026/Tweets%202026-01-02.html" in content
    assert "<h2>Tweets</h2>" not in content
    assert not stale_pages_dir.exists()


def test_site_working_orders_by_working_time(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    older = posts / "older.html"
    newer = posts / "newer.html"
    older.write_text("<html><body>Older</body></html>", encoding="utf-8")
    newer.write_text("<html><body>Newer</body></html>", encoding="utf-8")

    # Keep file mtime inverse to working order to assert working time wins.
    os.utime(older, (1_700_000_500, 1_700_000_500))
    os.utime(newer, (1_700_000_100, 1_700_000_100))

    working_times = iter(["2026-02-01T10:00:00Z", "2026-02-01T10:00:05Z"])
    monkeypatch.setattr(site_state, "_utc_now_iso", lambda: next(working_times))

    site_state.set_working_path(base, "Posts/Posts 2026/older.html")
    site_state.set_working_path(base, "Posts/Posts 2026/newer.html")

    out = build_working_index.write_site_working_index(base)
    content = out.read_text(encoding="utf-8")

    assert content.find("newer.html") < content.find("older.html")
    assert "🔥" not in content


def test_build_working_index_cli_generates_site_index(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    (posts / "doc.html").write_text("<html><body>Doc</body></html>", encoding="utf-8")
    site_state.set_working_path(base, "Posts/Posts 2026/doc.html")

    exit_code = build_working_index.main(["build_working_index.py", "--base-dir", str(base)])

    assert exit_code == 0
    assert (base / "_site" / "working" / "index.html").exists()


def test_working_index_shows_state_actions_for_pdfs(tmp_path: Path):
    base = tmp_path / "base"
    pdfs = base / "Pdfs" / "Pdfs 2026"
    pdfs.mkdir(parents=True)
    pdf = pdfs / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    site_state.set_working_path(base, "Pdfs/Pdfs 2026/paper.pdf")

    out = build_working_index.write_site_working_index(base)
    content = out.read_text(encoding="utf-8")

    assert "/pdfs/raw/Pdfs%202026/paper.pdf" in content
    assert 'data-api-action="to-done"' in content
    assert 'data-api-action="to-browse"' in content
    assert 'data-docflow-path="Pdfs/Pdfs 2026/paper.pdf"' in content
