import json
import os
import time
from datetime import date, datetime, timezone
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

    saved_highlights = highlight_store.save_highlights_for_path(
        base,
        "Posts/Posts 2026/doc.html",
        {
            "updated_at": "2026-02-03T10:06:00Z",
            "highlights": [{"id": "h1", "text": "Doc", "created_at": "2026-02-03T10:05:00Z"}],
        },
    )

    counts = build_browse_index.build_browse_site(base)

    assert counts["posts"] == 1
    assert counts["pdfs"] == 1
    assert counts["images"] == 1
    assert counts["podcasts"] == 1
    assert "incoming" not in counts

    browse_home = base / "_site" / "browse" / "index.html"
    site_home = base / "_site" / "index.html"
    search_index = base / "_site" / "search-index.json"
    posts_root_page = base / "_site" / "browse" / "posts" / "index.html"
    posts_year_page = base / "_site" / "browse" / "posts" / "Posts 2026" / "index.html"
    pdfs_year_page = base / "_site" / "browse" / "pdfs" / "Pdfs 2026" / "index.html"
    images_root_page = base / "_site" / "browse" / "images" / "index.html"
    podcasts_year_page = base / "_site" / "browse" / "podcasts" / "Podcasts 2026" / "index.html"
    assets_js = base / "_site" / "assets" / "actions.js"
    browse_sort_js = base / "_site" / "assets" / "browse-sort.js"

    assert browse_home.exists()
    assert site_home.exists()
    assert search_index.exists()
    assert posts_root_page.exists()
    assert posts_year_page.exists()
    assert pdfs_year_page.exists()
    assert images_root_page.exists()
    assert podcasts_year_page.exists()
    assert assets_js.exists()
    assert browse_sort_js.exists()
    assert not stale_incoming.exists()

    assets_content = assets_js.read_text(encoding="utf-8")
    assert "window.addEventListener('pageshow'" in assets_content
    assert "back_forward" in assets_content
    assert "document.querySelector('[data-dg-search-form]')" in assets_content

    browse_sort_content = browse_sort_js.read_text(encoding="utf-8")
    assert "window.addEventListener('pageshow'" in browse_sort_content
    assert "back_forward" in browse_sort_content
    assert "const sortableFiles = sortable.filter" in browse_sort_content
    assert "!href.endsWith('/')" in browse_sort_content
    assert "ul.dg-index, ul.dg-done-list, ul.dg-reading-list" in browse_sort_content
    assert "data-dg-sort-direction" in browse_sort_content
    assert "defaultSortDirection" in browse_sort_content
    assert 'data-dg-highlight-view="default"' in browse_sort_content
    assert "renderDoneViews" in browse_sort_content
    assert "highlightPreferenceKey = 'docflow.highlight-sort'" in browse_sort_content
    assert "window.localStorage.getItem(highlightPreferenceKey) === 'on'" in browse_sort_content
    assert "window.localStorage.setItem(highlightPreferenceKey, highlightsFirst ? 'on' : 'off')" in browse_sort_content
    assert "syncToggleState(toggle, highlightsFirst)" in browse_sort_content
    assert "dataset.dgHighlightLast" in browse_sort_content
    assert "bLast - aLast" in browse_sort_content
    assert "dgWorking" not in browse_sort_content

    root_content = posts_root_page.read_text(encoding="utf-8")
    assert "Posts 2026/</a> <span class='dg-count'>(1)</span>" in root_content
    assert "Posts 2026/</a><span class='dg-date'>" not in root_content

    images_root_content = images_root_page.read_text(encoding="utf-8")
    assert "Images 2026/</a> <span class='dg-count'>(1)</span>" in images_root_content
    assert "Images 2026/</a><span class='dg-date'>" not in images_root_content

    content = posts_year_page.read_text(encoding="utf-8")
    assert "Sample Title" not in content
    assert " · Sample Title" not in content
    assert "🔥" not in content
    assert "🟡" in content
    assert "doc.md" not in content
    assert "data-dg-sort-toggle" in content
    assert "Highlight: off" in content
    assert "data-dg-sortable='1'" in content
    assert "data-dg-working" not in content
    assert "data-dg-done" not in content
    assert "data-dg-highlighted='1'" in content
    assert f"data-dg-highlight-last='{highlight_store.latest_highlight_epoch(saved_highlights):.6f}'" in content
    assert "<script src='/assets/browse-sort.js' defer></script>" in content
    assert 'data-api-action="to-reading"' not in content
    assert '/posts/raw/Posts%202026/doc.html' in content

    pdf_content = pdfs_year_page.read_text(encoding="utf-8")
    assert "/pdfs/view/Pdfs%202026/paper.pdf" in pdf_content
    assert 'data-api-action="to-reading"' not in pdf_content
    assert 'data-api-action="to-done"' not in pdf_content

    browse_home_content = browse_home.read_text(encoding="utf-8")
    assert "Incoming" not in browse_home_content
    assert "🟡 highlight" in browse_home_content
    assert "data-dg-sort-toggle" not in browse_home_content
    assert "data-dg-search-input" not in browse_home_content
    assert "data-dg-search-button" not in browse_home_content
    assert "dg-browse-search-data" not in browse_home_content
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

    site_home_content = site_home.read_text(encoding="utf-8")
    assert "data-dg-search-input" in site_home_content
    assert "data-dg-search-button" in site_home_content
    assert "data-dg-search-random" in site_home_content
    assert "data-dg-search-tweets" in site_home_content
    assert "dg-browse-search-data" not in site_home_content
    assert "dg-search-suggestions" not in site_home_content
    assert '"stem": "doc"' not in site_home_content
    assert "fetch('/search-index.json',{cache:'no-store'})" in site_home_content
    assert "entries.filter" in site_home_content
    assert "Search title text or term + term" in site_home_content
    assert "function queryTerms(v)" in site_home_content
    assert "split(/\\s+\\+\\s+/)" in site_home_content
    assert "const includeTweets=!tweetsToggle||tweetsToggle.checked;" in site_home_content
    assert "if(!includeTweets&&e&&e.category==='tweets')return false;" in site_home_content
    assert "function wholeTermMatch(title,term)" in site_home_content
    assert "'iu').test(title)" in site_home_content
    assert "terms.every(function(term){return wholeTermMatch(title,term);})" in site_home_content
    assert "title.indexOf(term)" not in site_home_content
    assert "dg-search-results" in site_home_content
    assert "docflow.home.search" in site_home_content
    assert "docflow.home.search.tweets" in site_home_content
    assert "Math.random()" in site_home_content
    assert "saveSearch(norm(input.value));render(null);input.focus();" in site_home_content
    assert "input.value=suggestions[Math.floor(Math.random()*suggestions.length)];run();" not in site_home_content
    assert "window.addEventListener('pageshow',function(){if(input.value){run();}})" in site_home_content
    assert site_home_content.find("Rebuild browse + reading + done") < site_home_content.find("data-dg-search-input")

    search_index_payload = json.loads(search_index.read_text(encoding="utf-8"))
    assert search_index_payload["version"] == 1
    search_entries = {entry["name"]: entry for entry in search_index_payload["entries"]}
    assert search_entries["doc.html"]["stem"] == "doc"
    assert search_entries["doc.html"]["folder"] == "Posts 2026"
    assert search_entries["doc.html"]["category"] == "posts"
    assert isinstance(search_index_payload["suggestions"], list)


def test_browse_search_entries_include_full_name_folder_and_viewer_url(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    pdfs = base / "Pdfs" / "Pdfs 2025"
    posts.mkdir(parents=True)
    pdfs.mkdir(parents=True)
    (posts / "Alan Kay on objects.html").write_text("<html><body>Article</body></html>", encoding="utf-8")
    (pdfs / "Notes from Alan Kay.pdf").write_bytes(b"%PDF-1.4\n")

    entries = build_browse_index._collect_browse_search_entries(base, build_browse_index._category_roots(base))

    alan_entries = {entry["name"]: entry for entry in entries}
    assert alan_entries["Alan Kay on objects.html"]["stem"] == "Alan Kay on objects"
    assert alan_entries["Alan Kay on objects.html"]["folder"] == "Posts 2026"
    assert alan_entries["Alan Kay on objects.html"]["category"] == "posts"
    assert alan_entries["Alan Kay on objects.html"]["href"] == "/posts/raw/Posts%202026/Alan%20Kay%20on%20objects.html"
    assert alan_entries["Notes from Alan Kay.pdf"]["folder"] == "Pdfs 2025"
    assert alan_entries["Notes from Alan Kay.pdf"]["category"] == "pdfs"
    assert alan_entries["Notes from Alan Kay.pdf"]["href"] == "/pdfs/view/Pdfs%202025/Notes%20from%20Alan%20Kay.pdf"


def test_browse_search_entries_sort_by_markdown_docflow_ingested_at(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    older_html = posts / "Older mtime but newer ingest.html"
    older_html.write_text("<html><body>Newer ingest</body></html>", encoding="utf-8")
    older_html.with_suffix(".md").write_text(
        "---\ndocflow_ingested_at: 2026-05-20T10:00:00Z\n---\n\n# Newer ingest\n",
        encoding="utf-8",
    )
    newer_html = posts / "Newer mtime but older ingest.html"
    newer_html.write_text("<html><body>Older ingest</body></html>", encoding="utf-8")
    newer_html.with_suffix(".md").write_text(
        "---\ndocflow_ingested_at: 2026-05-19T10:00:00Z\n---\n\n# Older ingest\n",
        encoding="utf-8",
    )
    os.utime(older_html, (1_700_000_000, 1_700_000_000))
    os.utime(newer_html, (1_800_000_000, 1_800_000_000))

    entries = build_browse_index._collect_browse_search_entries(base, build_browse_index._category_roots(base))

    names = [entry["name"] for entry in entries]
    assert names.index("Older mtime but newer ingest.html") < names.index("Newer mtime but older ingest.html")


def test_browse_search_entries_include_tweet_titles_with_consolidated_anchor(tmp_path: Path):
    base = tmp_path / "base"
    tweets = base / "Tweets" / "Tweets 2026"
    tweets.mkdir(parents=True)
    (tweets / "Tweet - Example Author - File Title With Apple Inside.md").write_text(
        "\n".join(
            [
                "---",
                "source: tweet",
                "title: Tweet by Example Author (@example)",
                "tweet_consolidated_url: /tweets/raw/Tweets%202026/Tweets%202026-05-19.html#tweet-example",
                "tweet_consolidated_anchor: tweet-example",
                "---",
                "",
                "# Tweet by Example Author (@example)",
                "",
                "Tweet body.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tweets / "Tweet - Example Author - File Title With Apple Inside.html").write_text("<html><body>Tweet</body></html>", encoding="utf-8")

    entries = build_browse_index._collect_browse_search_entries(base, build_browse_index._category_roots(base))

    title_entries = [entry for entry in entries if entry["stem"] == "Tweet - Example Author - File Title With Apple Inside"]
    assert title_entries == [
        {
            "stem": "Tweet - Example Author - File Title With Apple Inside",
            "name": "Tweet - Example Author - File Title With Apple Inside",
            "href": "/tweets/raw/Tweets%202026/Tweets%202026-05-19.html#tweet-example",
            "folder": "Tweets 2026 / Tweet",
            "category": "tweets",
        }
    ]
    assert all(entry["href"] != "/tweets/raw/Tweets%202026/Tweet%20-%20Example%20Author%20-%20File%20Title%20With%20Apple%20Inside.html" for entry in entries)


def test_browse_search_entries_skip_tweet_markdown_without_consolidated_anchor(tmp_path: Path):
    base = tmp_path / "base"
    tweets = base / "Tweets" / "Tweets 2026"
    tweets.mkdir(parents=True)
    (tweets / "loose-tweet.md").write_text(
        "---\nsource: tweet\ntitle: Loose tweet title\n---\n\n# Loose tweet title\n",
        encoding="utf-8",
    )

    entries = build_browse_index._collect_browse_search_entries(base, build_browse_index._category_roots(base))

    assert all(entry["stem"] != "Loose tweet title" for entry in entries)


def test_browse_search_suggestions_are_derived_from_indexed_titles():
    entries = [
        {"stem": "Alan Kay on objects", "name": "Alan Kay on objects.html", "href": "#", "folder": "Posts 2026", "category": "posts"},
        {"stem": "Notes from Alan Kay", "name": "Notes from Alan Kay.pdf", "href": "#", "folder": "Pdfs 2025", "category": "pdfs"},
        {"stem": "Artificial intelligence and creativity", "name": "Artificial intelligence and creativity.html", "href": "#", "folder": "Posts 2026", "category": "posts"},
        {"stem": "Podcast title should not suggest", "name": "Podcast title should not suggest.html", "href": "#", "folder": "Podcasts 2026", "category": "podcasts"},
        {"stem": "Tweet title should not suggest", "name": "Tweet title should not suggest", "href": "#", "folder": "Tweets 2026 / Tweet", "category": "tweets"},
    ]

    suggestions = build_browse_index._collect_browse_search_suggestions(entries, limit=20)

    assert "Alan Kay" in suggestions
    assert "Artificial intelligence" in suggestions
    assert "Notes from Alan" not in suggestions
    assert "Podcast title" not in suggestions
    assert "Tweet title" not in suggestions
    assert len(suggestions) <= 20
    assert build_browse_index.SEARCH_SUGGESTION_LIMIT == 400


def test_collect_category_items_handles_missing_dirs(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()

    items = build_browse_index.collect_category_items(base, "images")
    assert items == []


def test_browse_hides_reading_items_without_touching_mtime(tmp_path: Path):
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
    site_state.set_reading_path(base, "Posts/Posts 2026/b.html")

    build_browse_index.build_browse_site(base)
    year_page = base / "_site" / "browse" / "posts" / "Posts 2026" / "index.html"
    html = year_page.read_text(encoding="utf-8")

    assert "b.html" not in html
    assert "a.html" in html
    assert abs(second.stat().st_mtime - mtime_b_before) < 0.001
    assert "<span class='dg-date'> — " not in html


def test_browse_hides_recently_staged_items(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    reading_doc = posts / "reading.html"
    done_doc = posts / "done.html"
    rest_doc = posts / "rest.html"
    reading_doc.write_text("<html><body>Reading</body></html>", encoding="utf-8")
    done_doc.write_text("<html><body>Done</body></html>", encoding="utf-8")
    rest_doc.write_text("<html><body>Rest</body></html>", encoding="utf-8")

    os.utime(reading_doc, (1_700_000_050, 1_700_000_050))
    os.utime(done_doc, (1_700_000_100, 1_700_000_100))
    # Keep a very recent mtime so rest beats done once done has no stage priority.
    os.utime(rest_doc, (1_900_000_200, 1_900_000_200))

    times = iter(["2026-02-01T10:00:00Z", "2026-02-01T10:00:05Z"])
    monkeypatch.setattr(site_state, "_utc_now_iso", lambda: next(times))
    site_state.set_reading_path(base, "Posts/Posts 2026/reading.html")
    site_state.set_done_path(base, "Posts/Posts 2026/done.html")

    build_browse_index.build_browse_site(base)
    year_page = base / "_site" / "browse" / "posts" / "Posts 2026" / "index.html"
    html = year_page.read_text(encoding="utf-8")

    assert "reading.html" not in html
    assert "done.html" not in html
    assert "rest.html" in html


def test_browse_hides_reading_and_done(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    reading = posts / "reading.html"
    done_old = posts / "done-old.html"
    done_new = posts / "done-new.html"
    other = posts / "other.html"
    reading.write_text("<html><body>Reading</body></html>", encoding="utf-8")
    done_old.write_text("<html><body>Done old</body></html>", encoding="utf-8")
    done_new.write_text("<html><body>Done new</body></html>", encoding="utf-8")
    other.write_text("<html><body>Other</body></html>", encoding="utf-8")

    os.utime(reading, (1_700_000_000, 1_700_000_000))
    os.utime(done_old, (1_700_000_400, 1_700_000_400))
    os.utime(done_new, (1_700_000_100, 1_700_000_100))
    os.utime(other, (1_700_000_900, 1_700_000_900))

    done_times = iter(["2026-02-01T10:00:00Z", "2026-02-01T10:00:05Z", "2026-02-01T10:00:10Z"])
    monkeypatch.setattr(site_state, "_utc_now_iso", lambda: next(done_times))

    site_state.set_reading_path(base, "Posts/Posts 2026/reading.html")
    site_state.set_done_path(base, "Posts/Posts 2026/done-old.html")
    site_state.set_done_path(base, "Posts/Posts 2026/done-new.html")

    build_browse_index.build_browse_site(base)
    year_page = base / "_site" / "browse" / "posts" / "Posts 2026" / "index.html"
    html = year_page.read_text(encoding="utf-8")

    assert "reading.html" not in html
    assert "done-new.html" not in html
    assert "done-old.html" not in html
    assert "other.html" in html


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


def test_current_year_browse_pages_group_articles_by_relative_time(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    monkeypatch.setattr(build_browse_index, "_local_today", lambda: date(2026, 5, 18))

    categories = [
        ("posts", "Posts", "Posts 2026", "post"),
        ("tweets", "Tweets", "Tweets 2026", "tweet"),
        ("podcasts", "Podcasts", "Podcasts 2026", "podcast"),
    ]
    dated_files = [
        ("today", datetime(2026, 5, 18, 12, tzinfo=timezone.utc)),
        ("yesterday", datetime(2026, 5, 17, 12, tzinfo=timezone.utc)),
        ("last-seven", datetime(2026, 5, 14, 12, tzinfo=timezone.utc)),
        ("last-thirty", datetime(2026, 4, 25, 12, tzinfo=timezone.utc)),
        ("april", datetime(2026, 4, 10, 12, tzinfo=timezone.utc)),
        ("march", datetime(2026, 3, 20, 12, tzinfo=timezone.utc)),
        ("february", datetime(2026, 2, 5, 12, tzinfo=timezone.utc)),
    ]

    for _, root_name, year_dir_name, prefix in categories:
        year_dir = base / root_name / year_dir_name
        year_dir.mkdir(parents=True)
        for suffix, mtime in dated_files:
            doc = year_dir / f"{prefix}-{suffix}.html"
            doc.write_text(f"<html><body>{prefix} {suffix}</body></html>", encoding="utf-8")
            epoch = mtime.timestamp()
            os.utime(doc, (epoch, epoch))

    build_browse_index.build_browse_site(base)

    for category, _, year_dir_name, prefix in categories:
        page = base / "_site" / "browse" / category / year_dir_name / "index.html"
        content = page.read_text(encoding="utf-8")

        assert "<h3 class='dg-time-heading'>Hoy</h3>" in content
        assert "<h3 class='dg-time-heading'>Ayer</h3>" in content
        assert "<h3 class='dg-time-heading'>Últimos 7 días</h3>" in content
        assert "<h3 class='dg-time-heading'>Últimos 30 días</h3>" in content
        assert "<h3 class='dg-time-heading'>Abril 2026</h3>" in content
        assert "<h3 class='dg-time-heading'>Marzo 2026</h3>" in content
        assert "<h3 class='dg-time-heading'>Febrero 2026</h3>" in content
        assert content.find("Hoy") < content.find(f"{prefix}-today.html")
        assert content.find("Ayer") < content.find(f"{prefix}-yesterday.html")
        assert content.find("Últimos 7 días") < content.find(f"{prefix}-last-seven.html")
        assert content.find("Últimos 30 días") < content.find(f"{prefix}-last-thirty.html")
        assert content.find("Abril 2026") < content.find(f"{prefix}-april.html")
        assert content.find("Marzo 2026") < content.find(f"{prefix}-march.html")
        assert content.find("Febrero 2026") < content.find(f"{prefix}-february.html")


def test_non_current_year_browse_pages_group_by_month(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    monkeypatch.setattr(build_browse_index, "_local_today", lambda: date(2026, 5, 18))
    posts = base / "Posts" / "Posts 2025"
    posts.mkdir(parents=True)
    old = posts / "old.html"
    old.write_text("<html><body>Old</body></html>", encoding="utf-8")
    old_epoch = datetime(2025, 12, 20, 12, tzinfo=timezone.utc).timestamp()
    os.utime(old, (old_epoch, old_epoch))

    build_browse_index.build_browse_site(base)

    page = base / "_site" / "browse" / "posts" / "Posts 2025" / "index.html"
    content = page.read_text(encoding="utf-8")
    assert "<h3 class='dg-time-heading'>Diciembre 2025</h3>" in content
    assert "old.html" in content


def test_previous_year_browse_pages_group_by_month(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    monkeypatch.setattr(build_browse_index, "_local_today", lambda: date(2026, 5, 18))
    posts = base / "Posts" / "Posts 2025"
    posts.mkdir(parents=True)

    april = posts / "april.html"
    march = posts / "march.html"
    april.write_text("<html><body>April</body></html>", encoding="utf-8")
    march.write_text("<html><body>March</body></html>", encoding="utf-8")
    april_epoch = datetime(2025, 4, 10, 12, tzinfo=timezone.utc).timestamp()
    march_epoch = datetime(2025, 3, 10, 12, tzinfo=timezone.utc).timestamp()
    os.utime(april, (april_epoch, april_epoch))
    os.utime(march, (march_epoch, march_epoch))

    build_browse_index.build_browse_site(base)

    page = base / "_site" / "browse" / "posts" / "Posts 2025" / "index.html"
    content = page.read_text(encoding="utf-8")
    assert "<h3 class='dg-time-heading'>Abril 2025</h3>" in content
    assert "<h3 class='dg-time-heading'>Marzo 2025</h3>" in content
    assert content.find("Abril 2025") < content.find("april.html")
    assert content.find("Marzo 2025") < content.find("march.html")
    assert content.find("Abril 2025") < content.find("Marzo 2025")


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
