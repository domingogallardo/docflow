import os
from datetime import datetime
from pathlib import Path

from utils.markdown_utils import split_front_matter
from utils.backfill_post_ingested_dates_from_mtime import (
    backfill_post_ingested_dates_from_mtime,
)


def _set_mtime(path: Path, iso_value: str) -> int:
    epoch = int(datetime.fromisoformat(iso_value.replace("Z", "+00:00")).timestamp())
    path.touch()
    os_time = (epoch, epoch)
    os.utime(path, os_time)
    return epoch


def test_backfill_post_ingested_dates_from_mtime_updates_posts_only_and_preserves_mtime(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    tweets = base / "Tweets" / "Tweets 2026"
    posts.mkdir(parents=True)
    tweets.mkdir(parents=True)

    md = posts / "Article.md"
    html = posts / "Article.html"
    md.write_text("---\ntitle: Article\n---\n\n# Article\n", encoding="utf-8")
    html.write_text("<html><head></head><body>Article</body></html>", encoding="utf-8")
    epoch = _set_mtime(md, "2026-01-02T03:04:05Z")
    _set_mtime(html, "2026-01-02T03:04:05Z")

    tweet_md = tweets / "Tweet.md"
    tweet_md.write_text("---\ntitle: Tweet\n---\n\n# Tweet\n", encoding="utf-8")
    _set_mtime(tweet_md, "2026-01-02T03:04:05Z")

    result = backfill_post_ingested_dates_from_mtime(
        base,
        after="2025-03-20T23:59:59Z",
    )

    assert result.scanned == 1
    assert result.updated == 1
    assert md.stat().st_mtime == epoch
    assert html.stat().st_mtime == epoch

    meta, _ = split_front_matter(md.read_text(encoding="utf-8"))
    assert meta["docflow_ingested_at"] == "2026-01-02T03:04:05Z"
    html_text = html.read_text(encoding="utf-8")
    assert 'name="docflow-ingested-at"' in html_text
    assert 'content="2026-01-02T03:04:05Z"' in html_text
    tweet_meta, _ = split_front_matter(tweet_md.read_text(encoding="utf-8"))
    assert "docflow_ingested_at" not in tweet_meta


def test_backfill_post_ingested_dates_from_mtime_skips_old_mtime_and_existing(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    old = posts / "Old.md"
    old.write_text("---\ntitle: Old\n---\n\n# Old\n", encoding="utf-8")
    _set_mtime(old, "2025-03-20T12:00:00Z")

    existing = posts / "Existing.md"
    existing.write_text(
        "---\n"
        "title: Existing\n"
        "docflow_ingested_at: 2026-01-01T00:00:00Z\n"
        "---\n\n# Existing\n",
        encoding="utf-8",
    )
    _set_mtime(existing, "2026-01-02T03:04:05Z")

    result = backfill_post_ingested_dates_from_mtime(
        base,
        after="2025-03-20T23:59:59Z",
    )

    assert result.scanned == 2
    assert result.updated == 0
    assert result.skipped_existing == 1
    assert result.skipped_old_mtime == 1

    old_meta, _ = split_front_matter(old.read_text(encoding="utf-8"))
    assert "docflow_ingested_at" not in old_meta


def test_backfill_post_ingested_dates_from_mtime_dry_run_does_not_write(tmp_path: Path):
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    md = posts / "Article.md"
    md.write_text("---\ntitle: Article\n---\n\n# Article\n", encoding="utf-8")
    _set_mtime(md, "2026-01-02T03:04:05Z")

    result = backfill_post_ingested_dates_from_mtime(
        base,
        after="2025-03-20T23:59:59Z",
        dry_run=True,
    )

    assert result.updated == 1
    meta, _ = split_front_matter(md.read_text(encoding="utf-8"))
    assert "docflow_ingested_at" not in meta
