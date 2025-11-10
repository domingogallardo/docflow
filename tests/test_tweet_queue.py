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
