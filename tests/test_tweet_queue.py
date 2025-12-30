#!/usr/bin/env python3
"""Tests for tweet collection via X likes."""
from pathlib import Path
from unittest.mock import patch

from pipeline_manager import DocumentProcessor


def prepare_processor(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    processor = DocumentProcessor(tmp_path, 2025)
    return processor, incoming


def mock_likes(monkeypatch, urls, stop_found=True):
    def fake_fetch(*args, **kwargs):
        return list(urls), stop_found, len(urls)

    monkeypatch.setattr("pipeline_manager.fetch_likes_with_state", fake_fetch)


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
        ("# T1\n\n[View on X](https://x.com/1)\n", "Tweet - user-1.md"),
        ("# T2\n\n[View on X](https://x.com/2)\n", "Tweet - user-2.md"),
    ]

    with patch("pipeline_manager.fetch_tweet_markdown", side_effect=responses):
        created = processor.process_tweet_urls()

    assert len(created) == 2
    assert (incoming / "Tweet - user-1.md").exists()
    assert (incoming / "Tweet - user-2.md").exists()


def test_process_tweet_urls_handles_fetch_error(tmp_path, monkeypatch):
    processor, _ = prepare_processor(tmp_path)

    def failing_fetch(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("pipeline_manager.fetch_likes_with_state", failing_fetch)
    created = processor.process_tweet_urls()
    assert created == []


def test_process_tweets_pipeline_runs_markdown_subset(tmp_path, monkeypatch):
    processor, _ = prepare_processor(tmp_path)
    mock_likes(monkeypatch, ["https://x.com/user/status/1"])

    with patch(
        "pipeline_manager.fetch_tweet_markdown",
        return_value=("# T1\n\n[View on X](https://x.com/1)\n", "Tweet - user-1.md"),
    ):
        captured = {}

        def fake_subset(files):
            captured["files"] = list(files)
            return [processor.tweets_dest / "Tweet - processed.md"]

        monkeypatch.setattr(
            processor.tweet_processor,
            "process_markdown_subset",
            fake_subset,
        )

        moved = processor.process_tweets_pipeline()

    assert captured["files"][0].name.startswith("Tweet - user-1")
    assert moved == [processor.tweets_dest / "Tweet - processed.md"]


def test_process_tweets_pipeline_skips_when_likes_empty(tmp_path, monkeypatch):
    processor, _ = prepare_processor(tmp_path)
    mock_likes(monkeypatch, [])

    def fail_subset(_):
        raise AssertionError("process_markdown_subset debe omitirse")

    monkeypatch.setattr(
        processor.tweet_processor,
        "process_markdown_subset",
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
        "pipeline_manager.fetch_tweet_markdown",
        return_value=("# T2\n\n[View on X](https://x.com/2)\n", "Tweet - user-2.md"),
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
        "pipeline_manager.fetch_tweet_markdown",
        return_value=("# T\n\n[View on X](https://x.com/42)\n", "Tweet - user-42.md"),
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
        "pipeline_manager.fetch_tweet_markdown",
        return_value=("# T4\n\n[View on X](https://x.com/4)\n", "Tweet - user-4.md"),
    ):
        processor.process_tweet_urls()

    lines = processor.tweets_processed.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "https://x.com/user/status/4"


def test_process_tweet_urls_processes_all_when_no_stop(tmp_path, monkeypatch):
    processor, incoming = prepare_processor(tmp_path)
    urls = [f"https://x.com/user/status/{idx}" for idx in range(1, 6)]
    mock_likes(monkeypatch, urls, stop_found=False)

    with patch(
        "pipeline_manager.fetch_tweet_markdown",
        side_effect=[
            ("# T1\n\n[View on X](https://x.com/1)\n", "Tweet - user-1.md"),
            ("# T2\n\n[View on X](https://x.com/2)\n", "Tweet - user-2.md"),
            ("# T3\n\n[View on X](https://x.com/3)\n", "Tweet - user-3.md"),
            ("# T4\n\n[View on X](https://x.com/4)\n", "Tweet - user-4.md"),
            ("# T5\n\n[View on X](https://x.com/5)\n", "Tweet - user-5.md"),
        ],
    ):
        created = processor.process_tweet_urls()

    assert len(created) == 5
