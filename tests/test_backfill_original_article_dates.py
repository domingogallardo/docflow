from pathlib import Path

from utils import split_front_matter
from utils.backfill_original_article_dates import (
    backfill_original_article_dates,
    extract_original_published_date,
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
