#!/usr/bin/env python3
"""Tests for tweet collection via X likes."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline_manager import DocumentProcessor
from utils.x_likes_fetcher import LikeTweet


@pytest.fixture(autouse=True)
def isolate_tweet_queue_config(monkeypatch):
    monkeypatch.setattr("pipeline_manager.cfg.TWEET_POSTS_URL", "")
    monkeypatch.setattr("pipeline_manager.cfg.TWEET_REPLIES_URL", "")


def prepare_processor(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    processor = DocumentProcessor(tmp_path, 2025)
    return processor, incoming


def mock_likes(monkeypatch, urls, stop_found=True):
    items = [
        LikeTweet(
            url=url,
            author_handle="@user",
            time_text="4h",
            time_datetime="2026-01-09T12:00:00.000Z",
        )
        for url in urls
    ]

    def fake_fetch(*args, **kwargs):
        return list(items), stop_found, len(items)

    monkeypatch.setattr("pipeline_manager.fetch_like_items_with_state", fake_fetch)


def mock_posts(monkeypatch, urls, stop_found=True):
    items = [
        LikeTweet(
            url=url,
            author_handle="@self",
            time_text="1h",
            time_datetime="2026-01-10T12:00:00.000Z",
        )
        for url in urls
    ]

    def fake_fetch(*args, **kwargs):
        return list(items), stop_found, len(items)

    monkeypatch.setattr("pipeline_manager.fetch_post_items_with_state", fake_fetch)


def mock_replies(monkeypatch, urls, stop_found=True):
    items = [
        LikeTweet(
            url=url,
            author_handle="@self",
            time_text="1h",
            time_datetime="2026-01-10T12:00:00.000Z",
            posted_kind="reply",
            reply_to_url="https://x.com/other/status/9",
        )
        for url in urls
    ]

    def fake_fetch(*args, **kwargs):
        return list(items), stop_found, len(items)

    monkeypatch.setattr("pipeline_manager.fetch_reply_items_with_state", fake_fetch)


def test_process_tweet_urls_creates_files_from_likes(tmp_path, monkeypatch):
    processor, incoming = prepare_processor(tmp_path)
    mock_likes(
        monkeypatch,
        [
            "https://x.com/user/status/1",
            "https://x.com/user/status/2",
        ],
    )

    responses = [
        ("---\nsource: tweet\n---\n\n# T1\n\n[View on X](https://x.com/1)\n", "Tweet - user-1.md"),
        ("---\nsource: tweet\n---\n\n# T2\n\n[View on X](https://x.com/2)\n", "Tweet - user-2.md"),
    ]

    with patch("pipeline_manager.fetch_tweet_thread_markdown", side_effect=responses):
        created = processor.process_tweet_urls()

    assert len(created) == 2
    assert (incoming / "Tweet - user-1.md").exists()
    assert (incoming / "Tweet - user-2.md").exists()


def test_process_tweet_urls_queues_primary_article_link(tmp_path, monkeypatch):
    processor, incoming = prepare_processor(tmp_path)
    mock_likes(monkeypatch, ["https://x.com/user/status/1"])

    markdown = (
        "---\nsource: tweet\n---\n\n"
        "# T1\n\n"
        "[View on X](https://x.com/user/status/1)\n"
        "Useful article:\n"
        "https://example.com/article?utm_source=x\n"
        "Original link: https://t.co/abc\n"
    )

    with patch(
        "pipeline_manager.fetch_tweet_thread_markdown",
        return_value=(markdown, "Tweet - user-1.md"),
    ):
        created = processor.process_tweet_urls()

    assert created == [incoming / "Tweet - user-1.md"]
    assert processor.links_file.read_text(encoding="utf-8") == (
        "https://example.com/article?utm_source=x\n"
    )
    assert json.loads(processor.tweet_article_sources.read_text(encoding="utf-8")) == {
        "https://example.com/article?utm_source=x": "https://x.com/user/status/1"
    }


def test_process_tweet_urls_queues_one_primary_article_per_thread_block(tmp_path, monkeypatch):
    processor, _ = prepare_processor(tmp_path)
    mock_likes(monkeypatch, ["https://x.com/user/status/1"])

    markdown = (
        "---\nsource: tweet\n---\n\n"
        "# Thread\n"
        "[View on X](https://x.com/user/status/1)\n"
        "https://example.com/one\n"
        "https://example.com/secondary\n"
        "---\n"
        "[View on X](https://x.com/user/status/2)\n"
        "[![image](https://pbs.twimg.com/media/1.jpg)](https://pbs.twimg.com/media/1.jpg)\n"
        "https://example.com/two\n"
    )

    with patch(
        "pipeline_manager.fetch_tweet_thread_markdown",
        return_value=(markdown, "Tweet - thread.md"),
    ):
        processor.process_tweet_urls()

    assert processor.links_file.read_text(encoding="utf-8") == (
        "https://example.com/one\n"
        "https://example.com/two\n"
    )


def test_process_tweet_urls_ignores_quoted_tweet_links(tmp_path, monkeypatch):
    processor, _ = prepare_processor(tmp_path)
    mock_likes(monkeypatch, ["https://x.com/user/status/1"])

    markdown = (
        "---\nsource: tweet\n---\n\n"
        "# T\n"
        "[View on X](https://x.com/user/status/1)\n"
        "Comment with no article.\n"
        "[View quoted tweet](https://x.com/other/status/2)\n"
        "Quote\n"
        "Other User\n"
        "https://quoted.example.com/article\n"
    )

    with patch(
        "pipeline_manager.fetch_tweet_thread_markdown",
        return_value=(markdown, "Tweet - user-1.md"),
    ):
        processor.process_tweet_urls()

    assert not processor.links_file.exists()


def test_process_tweet_urls_does_not_duplicate_existing_queued_link(tmp_path, monkeypatch):
    processor, _ = prepare_processor(tmp_path)
    mock_likes(monkeypatch, ["https://x.com/user/status/1"])
    processor.links_file.write_text("# queue\nhttps://example.com/article\n", encoding="utf-8")

    markdown = (
        "---\nsource: tweet\n---\n\n"
        "# T\n"
        "[View on X](https://x.com/user/status/1)\n"
        "https://example.com/article\n"
    )

    with patch(
        "pipeline_manager.fetch_tweet_thread_markdown",
        return_value=(markdown, "Tweet - user-1.md"),
    ):
        processor.process_tweet_urls()

    assert processor.links_file.read_text(encoding="utf-8") == (
        "# queue\nhttps://example.com/article\n"
    )


def test_process_tweet_urls_skips_direct_pdf_links(tmp_path, monkeypatch):
    processor, _ = prepare_processor(tmp_path)
    mock_likes(monkeypatch, ["https://x.com/user/status/1"])

    markdown = (
        "---\nsource: tweet\n---\n\n"
        "# T\n"
        "[View on X](https://x.com/user/status/1)\n"
        "https://example.com/paper.pdf\n"
        "https://example.com/article\n"
    )

    with patch(
        "pipeline_manager.fetch_tweet_thread_markdown",
        return_value=(markdown, "Tweet - user-1.md"),
    ):
        processor.process_tweet_urls()

    assert processor.links_file.read_text(encoding="utf-8") == "https://example.com/article\n"


def test_process_tweet_urls_skips_arxiv_pdf_but_keeps_abs_page(tmp_path, monkeypatch):
    processor, _ = prepare_processor(tmp_path)
    mock_likes(monkeypatch, ["https://x.com/user/status/1"])

    markdown = (
        "---\nsource: tweet\n---\n\n"
        "# T\n"
        "[View on X](https://x.com/user/status/1)\n"
        "https://arxiv.org/pdf/2605.01190\n"
        "https://arxiv.org/abs/2605.01190\n"
    )

    with patch(
        "pipeline_manager.fetch_tweet_thread_markdown",
        return_value=(markdown, "Tweet - user-1.md"),
    ):
        processor.process_tweet_urls()

    assert processor.links_file.read_text(encoding="utf-8") == "https://arxiv.org/abs/2605.01190\n"


def test_process_tweet_urls_resolves_tco_when_no_expanded_article_link(tmp_path, monkeypatch):
    processor, _ = prepare_processor(tmp_path)
    mock_likes(monkeypatch, ["https://x.com/user/status/1"])
    monkeypatch.setattr(
        "pipeline_manager.DocumentProcessor._resolve_tco_url",
        staticmethod(lambda url: "https://example.com/article" if url == "https://t.co/abc" else None),
    )

    markdown = (
        "---\nsource: tweet\n---\n\n"
        "# T\n"
        "[View on X](https://x.com/user/status/1)\n"
        "Article card from example.com\n"
        "Original link: https://t.co/abc\n"
    )

    with patch(
        "pipeline_manager.fetch_tweet_thread_markdown",
        return_value=(markdown, "Tweet - user-1.md"),
    ):
        processor.process_tweet_urls()

    assert processor.links_file.read_text(encoding="utf-8") == "https://example.com/article\n"


def test_process_tweet_urls_prefers_expanded_link_over_tco_resolution(tmp_path, monkeypatch):
    processor, _ = prepare_processor(tmp_path)
    mock_likes(monkeypatch, ["https://x.com/user/status/1"])
    called = False

    def fake_resolve(url):
        nonlocal called
        called = True
        return "https://example.com/from-tco"

    monkeypatch.setattr(
        "pipeline_manager.DocumentProcessor._resolve_tco_url",
        staticmethod(fake_resolve),
    )

    markdown = (
        "---\nsource: tweet\n---\n\n"
        "# T\n"
        "[View on X](https://x.com/user/status/1)\n"
        "https://example.com/expanded\n"
        "Original link: https://t.co/abc\n"
    )

    with patch(
        "pipeline_manager.fetch_tweet_thread_markdown",
        return_value=(markdown, "Tweet - user-1.md"),
    ):
        processor.process_tweet_urls()

    assert processor.links_file.read_text(encoding="utf-8") == "https://example.com/expanded\n"
    assert not called


def test_process_tweet_urls_handles_fetch_error(tmp_path, monkeypatch):
    processor, _ = prepare_processor(tmp_path)

    def failing_fetch(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("pipeline_manager.fetch_like_items_with_state", failing_fetch)
    created = processor.process_tweet_urls()
    assert created == []


def test_process_tweet_urls_records_failed_download(tmp_path, monkeypatch):
    processor, _ = prepare_processor(tmp_path)
    url = "https://x.com/user/status/1"
    mock_likes(monkeypatch, [url])

    with patch("pipeline_manager.fetch_tweet_thread_markdown", side_effect=RuntimeError("boom")):
        created = processor.process_tweet_urls()

    assert created == []
    assert processor.tweets_failed.exists()
    assert processor.tweets_failed.read_text(encoding="utf-8") == url + "\n"
    assert not processor.tweets_processed.exists()


def test_process_tweet_urls_retries_failed_on_next_run(tmp_path, monkeypatch):
    processor, incoming = prepare_processor(tmp_path)
    url = "https://x.com/user/status/99"
    processor.tweets_failed.write_text(url + "\n", encoding="utf-8")
    mock_likes(monkeypatch, [])

    with patch(
        "pipeline_manager.fetch_tweet_thread_markdown",
        return_value=(
            "---\nsource: tweet\n---\n\n# T\n\n[View on X](https://x.com/99)\n",
            "Tweet - user-99.md",
        ),
    ):
        created = processor.process_tweet_urls()

    assert len(created) == 1
    assert (incoming / "Tweet - user-99.md").exists()
    assert processor.tweets_processed.read_text(encoding="utf-8") == url + "\n"
    assert not processor.tweets_failed.exists()


def test_process_tweet_urls_retry_keeps_existing_anchor_first(tmp_path, monkeypatch):
    processor, _ = prepare_processor(tmp_path)
    anchor_url = "https://x.com/user/status/10"
    retry_url = "https://x.com/user/status/99"
    processor.tweets_processed.write_text(anchor_url + "\n", encoding="utf-8")
    processor.tweets_failed.write_text(retry_url + "\n", encoding="utf-8")
    mock_likes(monkeypatch, [])

    with patch(
        "pipeline_manager.fetch_tweet_thread_markdown",
        return_value=(
            "---\nsource: tweet\n---\n\n# Retry\n\n[View on X](https://x.com/99)\n",
            "Tweet - user-99.md",
        ),
    ):
        processor.process_tweet_urls()

    lines = processor.tweets_processed.read_text(encoding="utf-8").splitlines()
    assert lines == [anchor_url, retry_url]


def test_process_tweet_urls_reanchors_when_previous_first_url_disappears(tmp_path, monkeypatch):
    processor, _ = prepare_processor(tmp_path)
    stale_first = "https://x.com/user/status/999"
    expected_anchor = "https://x.com/user/status/10"
    older = "https://x.com/user/status/9"
    processor.tweets_processed.write_text(
        "\n".join([stale_first, expected_anchor, older]) + "\n",
        encoding="utf-8",
    )
    mock_likes(monkeypatch, [expected_anchor, older], stop_found=False)

    created = processor.process_tweet_urls()

    assert created == []
    lines = processor.tweets_processed.read_text(encoding="utf-8").splitlines()
    assert lines[0] == expected_anchor
    assert lines[1:] == [stale_first, older]


def test_process_tweets_pipeline_runs_markdown_subset(tmp_path, monkeypatch):
    processor, _ = prepare_processor(tmp_path)
    mock_likes(monkeypatch, ["https://x.com/user/status/1"])

    with patch(
        "pipeline_manager.fetch_tweet_thread_markdown",
        return_value=(
            "---\nsource: tweet\n---\n\n# T1\n\n[View on X](https://x.com/1)\n",
            "Tweet - user-1.md",
        ),
    ):
        captured = {}

        def fake_subset(files):
            captured["files"] = list(files)
            return [processor.tweets_dest / "Tweet - processed.md"]

        monkeypatch.setattr(
            processor.tweet_processor,
            "process_tweet_markdown_subset",
            fake_subset,
        )

        moved = processor.process_tweets_pipeline()

    assert captured["files"][0].name.startswith("Tweet - user-1")
    assert moved == [processor.tweets_dest / "Tweet - processed.md"]


def test_process_tweets_pipeline_moves_tweet_articles_to_posts(tmp_path, monkeypatch):
    processor, incoming = prepare_processor(tmp_path)
    mock_likes(monkeypatch, [])

    regular_md = incoming / "Tweet - regular.md"
    regular_md.write_text(
        "---\nsource: tweet\n---\n\n# Regular tweet\n\nShort text.",
        encoding="utf-8",
    )
    article_md = incoming / "Tweet - article.md"
    article_md.write_text(
        "---\nsource: tweet\ntweet_content_type: article\n---\n\n# Article tweet\n\nLong article text.",
        encoding="utf-8",
    )

    processor.tweet_processor.title_updater.update_titles = lambda files, renamer: None
    processor.markdown_processor.title_updater.update_titles = lambda files, renamer: None

    moved = processor.process_tweets_pipeline()

    moved_set = {path.relative_to(tmp_path) for path in moved}
    assert Path("Tweets/Tweets 2025/Tweet - regular.md") in moved_set
    assert Path("Tweets/Tweets 2025/Tweet - regular.html") in moved_set
    assert Path("Posts/Posts 2025/Tweet - article.md") in moved_set
    assert Path("Posts/Posts 2025/Tweet - article.html") in moved_set
    assert not (tmp_path / "Tweets" / "Tweets 2025" / "Tweet - article.md").exists()


def test_process_tweets_pipeline_skips_when_likes_empty(tmp_path, monkeypatch):
    processor, _ = prepare_processor(tmp_path)
    mock_likes(monkeypatch, [])

    def fail_subset(_):
        raise AssertionError("process_tweet_markdown_subset debe omitirse")

    monkeypatch.setattr(
        processor.tweet_processor,
        "process_tweet_markdown_subset",
        fail_subset,
    )

    moved = processor.process_tweets_pipeline()
    assert moved == []


def test_process_tweet_urls_skips_already_processed(tmp_path, monkeypatch):
    processor, incoming = prepare_processor(tmp_path)
    existing_url = "https://x.com/user/status/1"
    processor.tweets_processed.write_text(existing_url + "\n", encoding="utf-8")

    mock_likes(
        monkeypatch,
        [
            existing_url,
            "https://x.com/user/status/2",
        ],
    )

    with patch(
        "pipeline_manager.fetch_tweet_thread_markdown",
        return_value=(
            "---\nsource: tweet\n---\n\n# T2\n\n[View on X](https://x.com/2)\n",
            "Tweet - user-2.md",
        ),
    ) as mocked:
        created = processor.process_tweet_urls()

    assert len(created) == 1
    assert mocked.call_count == 1
    assert (incoming / "Tweet - user-2.md").exists()
    processed_lines = processor.tweets_processed.read_text(encoding="utf-8").splitlines()
    assert processed_lines == ["https://x.com/user/status/2", existing_url]


def test_process_tweet_urls_appends_processed_file(tmp_path, monkeypatch):
    processor, _ = prepare_processor(tmp_path)
    url = "https://x.com/user/status/42"
    mock_likes(monkeypatch, [url])

    with patch(
        "pipeline_manager.fetch_tweet_thread_markdown",
        return_value=(
            "---\nsource: tweet\n---\n\n# T\n\n[View on X](https://x.com/42)\n",
            "Tweet - user-42.md",
        ),
    ):
        processor.process_tweet_urls()

    assert processor.tweets_processed.exists()
    assert processor.tweets_processed.read_text(encoding="utf-8") == url + "\n"


def test_last_processed_uses_first_line(tmp_path, monkeypatch):
    processor, _ = prepare_processor(tmp_path)
    urls = [
        "https://x.com/user/status/1",
        "https://x.com/user/status/2",
        "https://x.com/user/status/3",
    ]
    # Most recent saved first.
    processor.tweets_processed.write_text("\n".join(reversed(urls)) + "\n", encoding="utf-8")

    assert processor._last_processed_tweet_url() == urls[-1]

    mock_likes(monkeypatch, ["https://x.com/user/status/4"])
    with patch(
        "pipeline_manager.fetch_tweet_thread_markdown",
        return_value=(
            "---\nsource: tweet\n---\n\n# T4\n\n[View on X](https://x.com/4)\n",
            "Tweet - user-4.md",
        ),
    ):
        processor.process_tweet_urls()

    lines = processor.tweets_processed.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "https://x.com/user/status/4"


def test_process_tweet_urls_processes_all_when_no_stop(tmp_path, monkeypatch):
    processor, incoming = prepare_processor(tmp_path)
    urls = [f"https://x.com/user/status/{idx}" for idx in range(1, 6)]
    mock_likes(monkeypatch, urls, stop_found=False)

    with patch(
        "pipeline_manager.fetch_tweet_thread_markdown",
        side_effect=[
            ("---\nsource: tweet\n---\n\n# T1\n\n[View on X](https://x.com/1)\n", "Tweet - user-1.md"),
            ("---\nsource: tweet\n---\n\n# T2\n\n[View on X](https://x.com/2)\n", "Tweet - user-2.md"),
            ("---\nsource: tweet\n---\n\n# T3\n\n[View on X](https://x.com/3)\n", "Tweet - user-3.md"),
            ("---\nsource: tweet\n---\n\n# T4\n\n[View on X](https://x.com/4)\n", "Tweet - user-4.md"),
            ("---\nsource: tweet\n---\n\n# T5\n\n[View on X](https://x.com/5)\n", "Tweet - user-5.md"),
        ],
    ):
        created = processor.process_tweet_urls()

    assert len(created) == 5


def test_process_tweet_urls_creates_files_from_posts_with_separate_state(tmp_path, monkeypatch):
    processor, incoming = prepare_processor(tmp_path)
    url = "https://x.com/self/status/10"

    monkeypatch.setattr("pipeline_manager.cfg.TWEET_POSTS_URL", "https://x.com/self")
    mock_likes(monkeypatch, [])
    mock_posts(monkeypatch, [url])
    mock_replies(monkeypatch, [])

    with patch(
        "pipeline_manager.fetch_tweet_thread_markdown",
        return_value=(
            "---\nsource: tweet\ntweet_capture_source: posted\n---\n\n# T\n\n[View on X](https://x.com/10)\n",
            "Tweet posted - self-10.md",
        ),
    ) as mocked:
        created = processor.process_tweet_urls()

    assert len(created) == 1
    assert (incoming / "Tweet posted - self-10.md").exists()
    assert processor.tweets_posted_processed.read_text(encoding="utf-8") == url + "\n"
    assert not processor.tweets_processed.exists()
    assert mocked.call_args.kwargs["capture_source"] == "posted"


def test_process_tweet_urls_creates_files_from_replies_with_parent_context(
    tmp_path,
    monkeypatch,
):
    processor, incoming = prepare_processor(tmp_path)
    url = "https://x.com/self/status/11"

    monkeypatch.setattr("pipeline_manager.cfg.TWEET_POSTS_URL", "https://x.com/self")
    mock_likes(monkeypatch, [])
    mock_posts(monkeypatch, [])
    mock_replies(monkeypatch, [url])

    with patch(
        "pipeline_manager.fetch_tweet_thread_markdown",
        return_value=(
            "---\nsource: tweet\ntweet_capture_source: posted\ntweet_posted_kind: reply\n---\n\n# T\n",
            "Tweet posted - self-11.md",
        ),
    ) as mocked:
        created = processor.process_tweet_urls()

    assert len(created) == 1
    assert (incoming / "Tweet posted - self-11.md").exists()
    assert processor.tweets_replies_processed.read_text(encoding="utf-8") == url + "\n"
    assert mocked.call_args.kwargs["capture_source"] == "posted"
    assert mocked.call_args.kwargs["posted_kind"] == "reply"
    assert mocked.call_args.kwargs["reply_parent_url"] == "https://x.com/other/status/9"


def test_process_tweet_urls_skips_replies_already_processed_as_posts(tmp_path, monkeypatch):
    processor, _ = prepare_processor(tmp_path)
    url = "https://x.com/self/status/11"
    processor.tweets_posted_processed.write_text(url + "\n", encoding="utf-8")

    monkeypatch.setattr("pipeline_manager.cfg.TWEET_POSTS_URL", "https://x.com/self")
    mock_likes(monkeypatch, [])
    mock_posts(monkeypatch, [])
    mock_replies(monkeypatch, [url], stop_found=False)

    with patch("pipeline_manager.fetch_tweet_thread_markdown") as mocked:
        created = processor.process_tweet_urls()

    assert created == []
    mocked.assert_not_called()
