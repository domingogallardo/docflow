import os
from pathlib import Path

from utils import build_read_index
from utils import highlight_store
from utils import site_state


def test_write_site_read_index_uses_published_state(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    html = posts / "doc.html"
    html.write_text("<html><body>Doc</body></html>", encoding="utf-8")

    site_state.publish_path(base, "Posts/Posts 2026/doc.html")
    site_state.set_bumped_path(base, "Posts/Posts 2026/doc.html", original_mtime=1.0, bumped_mtime=2.0)
    highlight_store.save_highlights_for_path(
        base,
        "Posts/Posts 2026/doc.html",
        {"highlights": [{"id": "h1", "text": "Doc"}]},
    )

    out = build_read_index.write_site_read_index(base)

    assert out == base / "_site" / "read" / "index.html"
    assert out.exists()

    content = out.read_text(encoding="utf-8")
    assert "/posts/raw/Posts%202026/doc.html" in content
    assert '<a href="/browse/">Browse</a>' in content
    assert "<h1>Read</h1>" in content
    assert "<h2>Tweets</h2>" not in content
    assert "github.com/domingogallardo/docflow" not in content
    assert "domingogallardo.com" not in content
    assert "🟡" in content
    assert "Posts/Posts 2026/doc.html" not in content
    assert "data-api-action" not in content
    assert (base / "_site" / "read" / "article.js").exists()


def test_write_site_read_index_keeps_tweets_in_main_list_and_removes_old_tweet_pages(tmp_path: Path):
    base = tmp_path / "base"
    tweets_dir = base / "Tweets" / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    tweet_html = tweets_dir / "Tweets 2026-01-02.html"
    tweet_html.write_text("<html><body>tweets</body></html>", encoding="utf-8")
    site_state.publish_path(base, "Tweets/Tweets 2026/Tweets 2026-01-02.html")

    stale_pages_dir = base / "_site" / "read" / "tweets"
    stale_pages_dir.mkdir(parents=True)
    (stale_pages_dir / "2026.html").write_text("<p>stale</p>", encoding="utf-8")

    out = build_read_index.write_site_read_index(base)
    content = out.read_text(encoding="utf-8")

    assert "/tweets/raw/Tweets%202026/Tweets%202026-01-02.html" in content
    assert "<h2>Tweets</h2>" not in content
    assert not stale_pages_dir.exists()


def test_site_read_uses_bump_state_for_order_without_touching_mtime(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    first = posts / "a.html"
    second = posts / "b.html"
    first.write_text("<html><body>A</body></html>", encoding="utf-8")
    second.write_text("<html><body>B</body></html>", encoding="utf-8")
    os.utime(first, (1_700_000_100, 1_700_000_100))
    os.utime(second, (1_700_000_000, 1_700_000_000))

    site_state.publish_path(base, "Posts/Posts 2026/a.html")
    site_state.publish_path(base, "Posts/Posts 2026/b.html")

    mtime_b_before = second.stat().st_mtime
    site_state.set_bumped_path(base, "Posts/Posts 2026/b.html", original_mtime=mtime_b_before, bumped_mtime=9_999_999_999.0)

    out = build_read_index.write_site_read_index(base)
    content = out.read_text(encoding="utf-8")

    assert content.find("b.html") < content.find("a.html")
    assert abs(second.stat().st_mtime - mtime_b_before) < 0.001
    assert " — " not in content


def test_build_read_index_cli_generates_site_index(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    (posts / "doc.html").write_text("<html><body>Doc</body></html>", encoding="utf-8")
    site_state.publish_path(base, "Posts/Posts 2026/doc.html")

    exit_code = build_read_index.main(["build_read_index.py", "--base-dir", str(base)])

    assert exit_code == 0
    assert (base / "_site" / "read" / "index.html").exists()
