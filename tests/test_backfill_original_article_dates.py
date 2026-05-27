from pathlib import Path

from utils import split_front_matter
from utils.backfill_original_article_dates import (
    backfill_original_article_dates,
    extract_original_published_date,
    extract_original_published_date_from_markdown,
)


def test_extract_original_published_date_prefers_json_ld():
    html = """
    <html><head>
      <meta property="article:published_time" content="2026-05-02T10:00:00Z">
      <script type="application/ld+json">
        {"@type": "Article", "datePublished": "2026-05-01T09:08:07+00:00"}
      </script>
    </head></html>
    """

    candidate = extract_original_published_date(html, url="https://example.com/2026/05/03/article")

    assert candidate is not None
    assert candidate.value == "2026-05-01T09:08:07Z"
    assert candidate.source == "json_ld:datePublished"


def test_extract_original_published_date_ignores_today_json_ld_when_time_disagrees(monkeypatch):
    from datetime import date as real_date

    class FakeDate(real_date):
        @classmethod
        def today(cls):
            return real_date(2026, 5, 27)

    from utils import backfill_original_article_dates as module

    monkeypatch.setattr(module, "date", FakeDate)
    html = """
    <html><head>
      <script type="application/ld+json">
        {"@type": "Article", "datePublished": "2026-05-27T03:33:04-07:00"}
      </script>
    </head><body>
      <article>
        <time datetime="2024-02-07T13:02:50+00:00">February 7, 2024</time>
      </article>
    </body></html>
    """

    candidate = extract_original_published_date(html)

    assert candidate is not None
    assert candidate.value == "2024-02-07T13:02:50Z"
    assert candidate.source == "time:datetime"


def test_extract_original_published_date_ignores_today_json_ld_without_stable_fallback(monkeypatch):
    from datetime import date as real_date

    class FakeDate(real_date):
        @classmethod
        def today(cls):
            return real_date(2026, 5, 27)

    from utils import backfill_original_article_dates as module

    monkeypatch.setattr(module, "date", FakeDate)
    html = """
    <html><head>
      <script type="application/ld+json">
        {"@type": "Article", "datePublished": "2026-05-27T03:33:04-07:00"}
      </script>
    </head><body><article><h1>Article</h1></article></body></html>
    """

    assert extract_original_published_date(html) is None


def test_extract_original_published_date_falls_back_to_url_path():
    candidate = extract_original_published_date("<html></html>", url="https://example.com/2024/12/31/post")

    assert candidate is not None
    assert candidate.value == "2024-12-31"
    assert candidate.source == "url:path"


def test_extract_original_published_date_reads_early_visible_article_date():
    html = """
    <html><body><article>
      <h1>Press release</h1>
      <p>20 November 2017</p>
      <p>On 19 October 2017, something else happened in the story body.</p>
    </article></body></html>
    """

    candidate = extract_original_published_date(html)

    assert candidate is not None
    assert candidate.value == "2017-11-20"
    assert candidate.source == "visible_text:article_start"


def test_extract_original_published_date_reads_submitted_visible_date():
    html = """
    <html><body><main>
      <p>Astrophysics &gt; Earth and Planetary Astrophysics</p>
      <p>arXiv:1711.03558v3</p>
      <p>[Submitted on 9 Nov 2017 (v1), last revised 11 May 2018]</p>
    </main></body></html>
    """

    candidate = extract_original_published_date(html)

    assert candidate is not None
    assert candidate.value == "2017-11-09"
    assert candidate.source == "visible_text:article_start"


def test_extract_original_published_date_prefers_structured_date_over_visible_text():
    html = """
    <html><head>
      <meta property="article:published_time" content="2026-05-02T10:00:00Z">
    </head><body><article>
      <p>Published 1 May 2026</p>
    </article></body></html>
    """

    candidate = extract_original_published_date(html)

    assert candidate is not None
    assert candidate.value == "2026-05-02T10:00:00Z"
    assert candidate.source == "meta:property=article:published_time"


def test_extract_original_published_date_from_markdown_reads_first_lines():
    markdown = """---
title: Article
---

# Article title

Published May 2, 2026

The story body starts here and mentions May 1, 2026 later.
"""

    candidate = extract_original_published_date_from_markdown(markdown)

    assert candidate is not None
    assert candidate.value == "2026-05-02"
    assert candidate.source == "markdown_text:first_lines"


def test_extract_original_published_date_from_markdown_ignores_late_body_dates():
    markdown = """# Article title

This opening line has no date.

This second line also has no date.

This third line still has no date.

Published May 2, 2026
"""

    assert extract_original_published_date_from_markdown(markdown) is None


def test_extract_original_published_date_from_markdown_rejects_old_dates():
    markdown = "Published May 2, 1989\n\nBody"

    assert extract_original_published_date_from_markdown(markdown) is None


def test_backfill_original_article_dates_updates_markdown_and_preserves_mtime(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    md = posts / "Article.md"
    md.write_text(
        "---\ndocflow_post_url: https://example.com/article\n---\n\n# Article\n",
        encoding="utf-8",
    )
    original_mtime_ns = md.stat().st_mtime_ns

    def fetch_url(url: str, timeout: float) -> str:
        assert url == "https://example.com/article"
        assert timeout == 3
        return '<meta property="article:published_time" content="2026-05-02T10:00:00Z">'

    result = backfill_original_article_dates(base, timeout=3, fetch_url=fetch_url)

    assert result.scanned == 1
    assert result.with_url == 1
    assert result.updated == 1
    assert result.not_found == 0
    assert md.stat().st_mtime_ns == original_mtime_ns
    meta, _ = split_front_matter(md.read_text(encoding="utf-8"))
    assert meta["docflow_original_published_at"] == "2026-05-02T10:00:00Z"
    assert meta["docflow_original_published_source"] == "meta:property=article:published_time"


def test_backfill_original_article_dates_updates_html_meta_and_preserves_mtime(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    md = posts / "Article.md"
    html = posts / "Article.html"
    md.write_text(
        "---\n"
        "docflow_post_url: https://example.com/article\n"
        "docflow_original_published_at: 2026-05-01\n"
        "docflow_original_published_source: json_ld:datePublished\n"
        "---\n\n# Article\n",
        encoding="utf-8",
    )
    html.write_text(
        "<html><head>"
        '<meta name="docflow-original-published-at" content="2026-05-01">'
        '<meta name="docflow-original-published-source" content="json_ld:datePublished">'
        "</head><body></body></html>",
        encoding="utf-8",
    )
    original_md_mtime_ns = md.stat().st_mtime_ns
    original_html_mtime_ns = html.stat().st_mtime_ns

    result = backfill_original_article_dates(
        base,
        force=True,
        fetch_url=lambda url, timeout: '<time datetime="2026-05-02T10:00:00Z"></time>',
    )

    assert result.updated == 1
    assert md.stat().st_mtime_ns == original_md_mtime_ns
    assert html.stat().st_mtime_ns == original_html_mtime_ns
    meta, _ = split_front_matter(md.read_text(encoding="utf-8"))
    assert meta["docflow_original_published_at"] == "2026-05-02T10:00:00Z"
    html_text = html.read_text(encoding="utf-8")
    assert 'content="2026-05-02T10:00:00Z"' in html_text
    assert 'content="time:datetime"' in html_text


def test_backfill_original_article_dates_dry_run_does_not_write(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    md = posts / "Article.md"
    md.write_text(
        "---\ndocflow_post_url: https://example.com/article\n---\n\n# Article\n",
        encoding="utf-8",
    )

    result = backfill_original_article_dates(
        base,
        dry_run=True,
        fetch_url=lambda url, timeout: '<time datetime="2026-05-02"></time>',
    )

    assert result.updated == 1
    meta, _ = split_front_matter(md.read_text(encoding="utf-8"))
    assert "docflow_original_published_at" not in meta


def test_backfill_original_article_dates_skips_existing_unless_forced(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    md = posts / "Article.md"
    md.write_text(
        "---\n"
        "docflow_post_url: https://example.com/article\n"
        "docflow_original_published_at: 2026-05-01\n"
        "---\n\n# Article\n",
        encoding="utf-8",
    )

    result = backfill_original_article_dates(
        base,
        fetch_url=lambda url, timeout: '<time datetime="2026-05-02"></time>',
    )

    assert result.updated == 0
    assert result.skipped_existing == 1
    meta, _ = split_front_matter(md.read_text(encoding="utf-8"))
    assert meta["docflow_original_published_at"] == "2026-05-01"

    result = backfill_original_article_dates(
        base,
        force=True,
        fetch_url=lambda url, timeout: '<time datetime="2026-05-02"></time>',
    )

    assert result.updated == 1
    meta, _ = split_front_matter(md.read_text(encoding="utf-8"))
    assert meta["docflow_original_published_at"] == "2026-05-02"


def test_backfill_original_article_dates_uses_url_path_when_fetch_fails(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    md = posts / "Article.md"
    md.write_text(
        "---\ndocflow_post_url: https://example.com/2026/05/02/article\n---\n\n# Article\n",
        encoding="utf-8",
    )

    def fetch_url(url: str, timeout: float) -> str:
        raise RuntimeError("offline")

    result = backfill_original_article_dates(base, fetch_url=fetch_url)

    assert result.updated == 1
    assert result.failed == 0
    meta, _ = split_front_matter(md.read_text(encoding="utf-8"))
    assert meta["docflow_original_published_at"] == "2026-05-02"
    assert meta["docflow_original_published_source"] == "url:path"
