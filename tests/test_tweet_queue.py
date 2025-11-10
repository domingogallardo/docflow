#!/usr/bin/env python3
"""Tests para el procesamiento de la cola Incoming/tweets.txt."""
from pathlib import Path
from unittest.mock import patch

from pipeline_manager import DocumentProcessor, DocumentProcessorConfig


def prepare_processor(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    config = DocumentProcessorConfig(base_dir=tmp_path, year=2025)
    processor = DocumentProcessor(config)
    return processor, incoming, config.tweets_queue


def test_process_tweet_urls_creates_files_and_cleans_queue(tmp_path):
    processor, incoming, queue_path = prepare_processor(tmp_path)
    queue_path.write_text(
        "\n".join(
            [
                "# Tweet backlog",
                "https://x.com/user/status/1",
                "",
                "https://x.com/user/status/2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    responses = [
        ("# T1\n\n[Ver en X](https://x.com/1)\n", "Tweet - user-1.md"),
        ("# T2\n\n[Ver en X](https://x.com/2)\n", "Tweet - user-2.md"),
    ]

    with patch("pipeline_manager.fetch_tweet_markdown", side_effect=responses):
        created = processor.process_tweet_urls()

    assert len(created) == 2
    assert (incoming / "Tweet - user-1.md").exists()
    assert (incoming / "Tweet - user-2.md").exists()
    # Solo queda el comentario (se preserva el contexto)
    assert queue_path.read_text(encoding="utf-8") == "# Tweet backlog\n"


def test_process_tweet_urls_keeps_failed_entries(tmp_path):
    processor, incoming, queue_path = prepare_processor(tmp_path)
    queue_path.write_text("https://x.com/user/status/404\n", encoding="utf-8")

    with patch(
        "pipeline_manager.fetch_tweet_markdown",
        side_effect=RuntimeError("fail"),
    ):
        created = processor.process_tweet_urls()

    assert created == []
    assert queue_path.exists()
    assert "https://x.com/user/status/404" in queue_path.read_text(encoding="utf-8")


def test_process_tweets_pipeline_runs_markdown_subset(tmp_path, monkeypatch):
    processor, incoming, queue_path = prepare_processor(tmp_path)
    queue_path.write_text("https://x.com/user/status/1\n", encoding="utf-8")

    responses = ("# T1\n\n[Ver en X](https://x.com/1)\n", "Tweet - user-1.md")

    with patch("pipeline_manager.fetch_tweet_markdown", return_value=responses):
        captured = {}

        def fake_subset(files):
            captured["files"] = list(files)
            return [processor.config.posts_dest / "Tweet - processed.md"]

        monkeypatch.setattr(
            processor.markdown_processor,
            "process_markdown_subset",
            fake_subset,
        )

        moved = processor.process_tweets_pipeline()

    assert queue_path.read_text(encoding="utf-8") == ""
    assert captured["files"][0].name.startswith("Tweet - user-1")
    assert moved == [processor.config.posts_dest / "Tweet - processed.md"]


def test_process_tweets_pipeline_skips_when_no_new(tmp_path, monkeypatch):
    processor, incoming, queue_path = prepare_processor(tmp_path)
    queue_path.write_text("", encoding="utf-8")

    def fail_subset(_):
        raise AssertionError("process_markdown_subset should not be called")

    monkeypatch.setattr(
        processor.markdown_processor,
        "process_markdown_subset",
        fail_subset,
    )

    moved = processor.process_tweets_pipeline()
    assert moved == []


def test_process_tweet_urls_preserves_empty_queue_file(tmp_path):
    processor, incoming, queue_path = prepare_processor(tmp_path)
    queue_path.write_text("https://x.com/user/status/1\n", encoding="utf-8")

    with patch(
        "pipeline_manager.fetch_tweet_markdown",
        return_value=("# T1\n\n[Ver en X](https://x.com/1)\n", "Tweet - user-1.md"),
    ):
        processor.process_tweet_urls()

    assert queue_path.exists()
    assert queue_path.read_text(encoding="utf-8") == ""
