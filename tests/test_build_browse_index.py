import os
from pathlib import Path

from utils import build_browse_index
from utils import highlight_store
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
    podcasts = base / "Podcasts" / "Podcasts 2026"
    podcasts.mkdir(parents=True)
    podcast_html = podcasts / "episode.html"
    podcast_html.write_text("<html><body>Podcast episode</body></html>", encoding="utf-8")

    stale_incoming = base / "_site" / "browse" / "incoming"
    stale_incoming.mkdir(parents=True)
    (stale_incoming / "index.html").write_text("<p>stale incoming</p>", encoding="utf-8")

    site_state.publish_path(base, "Posts/Posts 2026/doc.html")
    site_state.set_bumped_path(base, "Posts/Posts 2026/doc.html", original_mtime=10.0, bumped_mtime=20.0)
    highlight_store.save_highlights_for_path(
        base,
        "Posts/Posts 2026/doc.html",
        {"highlights": [{"id": "h1", "text": "Doc"}]},
    )

    counts = build_browse_index.build_browse_site(base)

    assert counts["posts"] == 1
    assert counts["pdfs"] == 1
    assert counts["podcasts"] == 1
    assert "incoming" not in counts

    browse_home = base / "_site" / "browse" / "index.html"
    posts_root_page = base / "_site" / "browse" / "posts" / "index.html"
    posts_year_page = base / "_site" / "browse" / "posts" / "Posts 2026" / "index.html"
    pdfs_year_page = base / "_site" / "browse" / "pdfs" / "Pdfs 2026" / "index.html"
    podcasts_year_page = base / "_site" / "browse" / "podcasts" / "Podcasts 2026" / "index.html"
    assets_js = base / "_site" / "assets" / "actions.js"

    assert browse_home.exists()
    assert posts_root_page.exists()
    assert posts_year_page.exists()
    assert pdfs_year_page.exists()
    assert podcasts_year_page.exists()
    assert assets_js.exists()
    assert not stale_incoming.exists()

    root_content = posts_root_page.read_text(encoding="utf-8")
    assert "Posts 2026/" in root_content

    content = posts_year_page.read_text(encoding="utf-8")
    assert "Sample Title" not in content
    assert " · Sample Title" not in content
    assert "🟢" in content
    assert "🟡" in content
    assert "doc.md" not in content
    assert 'data-api-action="unpublish"' not in content
    assert 'data-api-action="unbump"' not in content
    assert '/posts/raw/Posts%202026/doc.html' in content

    pdf_content = pdfs_year_page.read_text(encoding="utf-8")
    assert 'data-api-action="publish"' in pdf_content or 'data-api-action="unpublish"' in pdf_content
    assert 'data-api-action="bump"' in pdf_content or 'data-api-action="unbump"' in pdf_content

    browse_home_content = browse_home.read_text(encoding="utf-8")
    assert "Incoming" not in browse_home_content
    assert "Podcasts (1)" in browse_home_content


def test_collect_category_items_handles_missing_dirs(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()

    items = build_browse_index.collect_category_items(base, "images")
    assert items == []


def test_browse_uses_bump_state_for_order_without_touching_mtime(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    first = posts / "a.html"
    second = posts / "b.html"
    first.write_text("<html><title>A</title><body>A</body></html>", encoding="utf-8")
    second.write_text("<html><title>B</title><body>B</body></html>", encoding="utf-8")
    os.utime(first, (1_700_000_100, 1_700_000_100))
    os.utime(second, (1_700_000_000, 1_700_000_000))

    site_state.publish_path(base, "Posts/Posts 2026/a.html")
    site_state.publish_path(base, "Posts/Posts 2026/b.html")

    mtime_b_before = second.stat().st_mtime
    site_state.set_bumped_path(base, "Posts/Posts 2026/b.html", original_mtime=mtime_b_before, bumped_mtime=9_999_999_999.0)

    build_browse_index.build_browse_site(base)
    year_page = base / "_site" / "browse" / "posts" / "Posts 2026" / "index.html"
    html = year_page.read_text(encoding="utf-8")

    assert html.find("b.html") < html.find("a.html")
    assert abs(second.stat().st_mtime - mtime_b_before) < 0.001
    assert build_browse_index.fmt_date(mtime_b_before) in html
    assert build_browse_index.fmt_date(9_999_999_999.0) not in html


def test_tweets_listing_hides_secondary_title_text(tmp_path: Path):
    base = tmp_path / "base"
    tweets = base / "Tweets" / "Tweets 2026"
    tweets.mkdir(parents=True)

    tweet = tweets / "Consolidado Tweets 2026-01-02.html"
    tweet.write_text("<html><title>Tweet Title Extra</title><body>Tweets</body></html>", encoding="utf-8")
    site_state.publish_path(base, "Tweets/Tweets 2026/Consolidado Tweets 2026-01-02.html")

    build_browse_index.build_browse_site(base)
    year_page = base / "_site" / "browse" / "tweets" / "Tweets 2026" / "index.html"
    content = year_page.read_text(encoding="utf-8")

    assert "Tweet Title Extra" not in content
    assert " · Tweet Title Extra" not in content
