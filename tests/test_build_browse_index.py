import os
import time
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
    images = base / "Images" / "Images 2026"
    images.mkdir(parents=True)
    image_html = images / "photo.html"
    image_html.write_text("<html><body>Image</body></html>", encoding="utf-8")
    podcasts = base / "Podcasts" / "Podcasts 2026"
    podcasts.mkdir(parents=True)
    podcast_html = podcasts / "episode.html"
    podcast_html.write_text("<html><body>Podcast episode</body></html>", encoding="utf-8")

    stale_incoming = base / "_site" / "browse" / "incoming"
    stale_incoming.mkdir(parents=True)
    (stale_incoming / "index.html").write_text("<p>stale incoming</p>", encoding="utf-8")

    site_state.set_bumped_path(base, "Posts/Posts 2026/doc.html", original_mtime=10.0, bumped_mtime=20.0)
    highlight_store.save_highlights_for_path(
        base,
        "Posts/Posts 2026/doc.html",
        {"highlights": [{"id": "h1", "text": "Doc"}]},
    )

    counts = build_browse_index.build_browse_site(base)

    assert counts["posts"] == 1
    assert counts["pdfs"] == 1
    assert counts["images"] == 1
    assert counts["podcasts"] == 1
    assert "incoming" not in counts

    browse_home = base / "_site" / "browse" / "index.html"
    posts_root_page = base / "_site" / "browse" / "posts" / "index.html"
    posts_year_page = base / "_site" / "browse" / "posts" / "Posts 2026" / "index.html"
    pdfs_year_page = base / "_site" / "browse" / "pdfs" / "Pdfs 2026" / "index.html"
    images_root_page = base / "_site" / "browse" / "images" / "index.html"
    podcasts_year_page = base / "_site" / "browse" / "podcasts" / "Podcasts 2026" / "index.html"
    assets_js = base / "_site" / "assets" / "actions.js"
    browse_sort_js = base / "_site" / "assets" / "browse-sort.js"

    assert browse_home.exists()
    assert posts_root_page.exists()
    assert posts_year_page.exists()
    assert pdfs_year_page.exists()
    assert images_root_page.exists()
    assert podcasts_year_page.exists()
    assert assets_js.exists()
    assert browse_sort_js.exists()
    assert not stale_incoming.exists()

    browse_sort_content = browse_sort_js.read_text(encoding="utf-8")
    assert "window.addEventListener('pageshow'" in browse_sort_content
    assert "back_forward" in browse_sort_content
    assert "const sortableFiles = sortable.filter" in browse_sort_content
    assert "!href.endsWith('/')" in browse_sort_content
    assert "ul.dg-index, ul.dg-done-list" in browse_sort_content

    root_content = posts_root_page.read_text(encoding="utf-8")
    assert "Posts 2026/</a> <span class='dg-count'>(1)</span>" in root_content
    assert "Posts 2026/</a><span class='dg-date'>" not in root_content

    images_root_content = images_root_page.read_text(encoding="utf-8")
    assert "Images 2026/</a> <span class='dg-count'>(1)</span>" in images_root_content
    assert "Images 2026/</a><span class='dg-date'>" not in images_root_content

    content = posts_year_page.read_text(encoding="utf-8")
    assert "Sample Title" not in content
    assert " · Sample Title" not in content
    assert "🔥" in content
    assert "🟡" in content
    assert "doc.md" not in content
    assert "data-dg-sort-toggle" in content
    assert "Highlight: off" in content
    assert "data-dg-sortable='1'" in content
    assert "data-dg-highlighted='1'" in content
    assert "data-dg-done='1'" not in content
    assert "<script src='/assets/browse-sort.js' defer></script>" in content
    assert 'data-api-action="unbump"' not in content
    assert '/posts/raw/Posts%202026/doc.html' in content

    pdf_content = pdfs_year_page.read_text(encoding="utf-8")
    assert 'data-api-action="to-working"' in pdf_content
    assert 'data-api-action="bump"' in pdf_content or 'data-api-action="unbump"' in pdf_content

    browse_home_content = browse_home.read_text(encoding="utf-8")
    assert "Incoming" not in browse_home_content
    assert "🔥 bumped · 🟡 highlight" in browse_home_content
    assert "🔵 working" not in browse_home_content
    assert "🟢 done" not in browse_home_content
    assert 'href="podcasts/">Podcasts/</a> <span class=\'dg-count\'>(1)</span>' in browse_home_content
    assert 'href="posts/">Posts/</a> <span class=\'dg-count\'>(1)</span>' in browse_home_content
    assert 'href="tweets/">Tweets/</a> <span class=\'dg-count\'>(0)</span>' in browse_home_content
    assert 'href="pdfs/">Pdfs/</a> <span class=\'dg-count\'>(1)</span>' in browse_home_content
    assert 'href="images/">Images/</a> <span class=\'dg-count\'>(1)</span>' in browse_home_content
    assert 'href="posts/">Posts (1)/</a>' not in browse_home_content
    assert browse_home_content.find('href="posts/">Posts/') < browse_home_content.find('href="tweets/">Tweets/')
    assert browse_home_content.find('href="tweets/">Tweets/') < browse_home_content.find('href="podcasts/">Podcasts/')
    assert browse_home_content.find('href="podcasts/">Podcasts/') < browse_home_content.find('href="pdfs/">Pdfs/')
    assert browse_home_content.find('href="pdfs/">Pdfs/') < browse_home_content.find('href="images/">Images/')


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

    mtime_b_before = second.stat().st_mtime
    site_state.set_bumped_path(base, "Posts/Posts 2026/b.html", original_mtime=mtime_b_before, bumped_mtime=9_999_999_999.0)

    build_browse_index.build_browse_site(base)
    year_page = base / "_site" / "browse" / "posts" / "Posts 2026" / "index.html"
    html = year_page.read_text(encoding="utf-8")

    assert html.find("b.html") < html.find("a.html")
    assert abs(second.stat().st_mtime - mtime_b_before) < 0.001
    assert "<span class='dg-date'> — " not in html


def test_browse_hides_working_and_done_items(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    working_doc = posts / "working.html"
    done_doc = posts / "done.html"
    rest_doc = posts / "rest.html"
    working_doc.write_text("<html><body>Working</body></html>", encoding="utf-8")
    done_doc.write_text("<html><body>Done</body></html>", encoding="utf-8")
    rest_doc.write_text("<html><body>Rest</body></html>", encoding="utf-8")

    os.utime(working_doc, (1_700_000_000, 1_700_000_000))
    os.utime(done_doc, (1_700_000_100, 1_700_000_100))
    # Keep a very recent mtime so rest beats done once done has no stage priority.
    os.utime(rest_doc, (1_900_000_200, 1_900_000_200))

    times = iter(["2026-02-01T10:00:00Z", "2026-02-01T10:00:05Z"])
    monkeypatch.setattr(site_state, "_utc_now_iso", lambda: next(times))
    site_state.set_working_path(base, "Posts/Posts 2026/working.html")
    site_state.set_done_path(base, "Posts/Posts 2026/done.html")

    build_browse_index.build_browse_site(base)
    year_page = base / "_site" / "browse" / "posts" / "Posts 2026" / "index.html"
    html = year_page.read_text(encoding="utf-8")

    assert "working.html" not in html
    assert "done.html" not in html
    assert "rest.html" in html


def test_browse_keeps_bumped_and_hides_done(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    bumped = posts / "bumped.html"
    done_old = posts / "done-old.html"
    done_new = posts / "done-new.html"
    other = posts / "other.html"
    bumped.write_text("<html><body>Bumped</body></html>", encoding="utf-8")
    done_old.write_text("<html><body>Done old</body></html>", encoding="utf-8")
    done_new.write_text("<html><body>Done new</body></html>", encoding="utf-8")
    other.write_text("<html><body>Other</body></html>", encoding="utf-8")

    # Make file mtime conflict with desired order so state-driven priority is tested.
    os.utime(bumped, (1_700_000_000, 1_700_000_000))
    os.utime(done_old, (1_700_000_400, 1_700_000_400))
    os.utime(done_new, (1_700_000_100, 1_700_000_100))
    os.utime(other, (1_700_000_900, 1_700_000_900))

    done_times = iter(["2026-02-01T10:00:00Z", "2026-02-01T10:00:05Z", "2026-02-01T10:00:10Z"])
    monkeypatch.setattr(site_state, "_utc_now_iso", lambda: next(done_times))

    site_state.set_done_path(base, "Posts/Posts 2026/done-old.html")
    site_state.set_done_path(base, "Posts/Posts 2026/done-new.html")
    site_state.set_bumped_path(base, "Posts/Posts 2026/bumped.html", original_mtime=1_700_000_000.0, bumped_mtime=9_999_999_999.0)

    build_browse_index.build_browse_site(base)
    year_page = base / "_site" / "browse" / "posts" / "Posts 2026" / "index.html"
    html = year_page.read_text(encoding="utf-8")

    assert html.find("bumped.html") < html.find("other.html")
    assert "done-new.html" not in html
    assert "done-old.html" not in html


def test_tweets_listing_hides_secondary_title_text(tmp_path: Path):
    base = tmp_path / "base"
    tweets = base / "Tweets" / "Tweets 2026"
    tweets.mkdir(parents=True)

    tweet = tweets / "Tweets 2026-01-02.html"
    tweet.write_text("<html><title>Tweet Title Extra</title><body>Tweets</body></html>", encoding="utf-8")

    build_browse_index.build_browse_site(base)
    year_page = base / "_site" / "browse" / "tweets" / "Tweets 2026" / "index.html"
    content = year_page.read_text(encoding="utf-8")

    assert "Tweet Title Extra" not in content
    assert " · Tweet Title Extra" not in content


def test_pdfs_root_is_sorted_by_year_desc(tmp_path: Path):
    base = tmp_path / "base"
    pdfs_2024 = base / "Pdfs" / "Pdfs 2024"
    pdfs_2026 = base / "Pdfs" / "Pdfs 2026"
    pdfs_2024.mkdir(parents=True)
    pdfs_2026.mkdir(parents=True)
    (pdfs_2024 / "older.pdf").write_bytes(b"%PDF-1.4\n")
    (pdfs_2026 / "newer.pdf").write_bytes(b"%PDF-1.4\n")

    build_browse_index.build_browse_site(base)

    root_page = base / "_site" / "browse" / "pdfs" / "index.html"
    content = root_page.read_text(encoding="utf-8")
    assert content.find("Pdfs 2026/") < content.find("Pdfs 2024/")
    assert "Pdfs 2026/</a> <span class='dg-count'>(1)</span>" in content
    assert "Pdfs 2026/</a><span class='dg-date'>" not in content


def test_posts_root_is_sorted_by_year_desc(tmp_path: Path):
    base = tmp_path / "base"
    posts_1990 = base / "Posts" / "Posts 1990"
    posts_2026 = base / "Posts" / "Posts 2026"
    posts_1990.mkdir(parents=True)
    posts_2026.mkdir(parents=True)
    (posts_1990 / "old.html").write_text("<html><body>1990</body></html>", encoding="utf-8")
    (posts_2026 / "new.html").write_text("<html><body>2026</body></html>", encoding="utf-8")

    build_browse_index.build_browse_site(base)

    root_page = base / "_site" / "browse" / "posts" / "index.html"
    content = root_page.read_text(encoding="utf-8")
    assert content.find("Posts 2026/") < content.find("Posts 1990/")


def test_tweets_root_is_sorted_by_year_desc(tmp_path: Path):
    base = tmp_path / "base"
    tweets_2025 = base / "Tweets" / "Tweets 2025"
    tweets_2026 = base / "Tweets" / "Tweets 2026"
    tweets_2025.mkdir(parents=True)
    tweets_2026.mkdir(parents=True)
    (tweets_2025 / "Tweets 2025-12-31.html").write_text("<html><body>2025</body></html>", encoding="utf-8")
    (tweets_2026 / "Tweets 2026-01-01.html").write_text("<html><body>2026</body></html>", encoding="utf-8")

    build_browse_index.build_browse_site(base)

    root_page = base / "_site" / "browse" / "tweets" / "index.html"
    content = root_page.read_text(encoding="utf-8")
    assert content.find("Tweets 2026/") < content.find("Tweets 2025/")
    assert "Tweets 2026/</a> <span class='dg-count'>(1)</span>" in content
    assert "Tweets 2026/</a><span class='dg-date'>" not in content


def test_rebuild_browse_for_path_updates_only_target_branch(tmp_path: Path):
    base = tmp_path / "base"
    posts_2025 = base / "Posts" / "Posts 2025"
    posts_2026 = base / "Posts" / "Posts 2026"
    posts_2025.mkdir(parents=True)
    posts_2026.mkdir(parents=True)

    old_doc = posts_2025 / "old.html"
    new_doc = posts_2026 / "new.html"
    old_doc.write_text("<html><body>Old</body></html>", encoding="utf-8")
    new_doc.write_text("<html><body>New</body></html>", encoding="utf-8")

    build_browse_index.build_browse_site(base)
    untouched_page = base / "_site" / "browse" / "posts" / "Posts 2025" / "index.html"
    target_page = base / "_site" / "browse" / "posts" / "Posts 2026" / "index.html"
    category_root_page = base / "_site" / "browse" / "posts" / "index.html"
    untouched_mtime_before = untouched_page.stat().st_mtime
    category_root_mtime_before = category_root_page.stat().st_mtime

    site_state.set_done_path(base, "Posts/Posts 2026/new.html")
    time.sleep(1.1)
    result = build_browse_index.rebuild_browse_for_path(base, "Posts/Posts 2026/new.html")

    assert result["mode"] == "partial"
    assert result["category"] == "posts"
    assert "/browse/posts/Posts 2026/" in result["updated"]
    target_content = target_page.read_text(encoding="utf-8")
    assert "new.html" not in target_content
    assert "🟢" not in target_content
    assert abs(untouched_page.stat().st_mtime - untouched_mtime_before) < 0.001
    assert abs(category_root_page.stat().st_mtime - category_root_mtime_before) < 0.001
