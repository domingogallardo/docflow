#!/usr/bin/env python3
"""Tests para la recolección de tweets vía editor remoto."""
from pathlib import Path
from unittest.mock import patch

import requests

from pipeline_manager import DocumentProcessor, DocumentProcessorConfig


class DummyResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


def prepare_processor(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    config = DocumentProcessorConfig(base_dir=tmp_path, year=2025)
    processor = DocumentProcessor(config)
    return processor, incoming, config


def mock_editor(monkeypatch, text: str, status_code: int = 200):
    monkeypatch.setattr(
        "pipeline_manager.requests.get",
        lambda url, auth=None, timeout=None: DummyResponse(text, status_code),
    )


def test_process_tweet_urls_creates_files_from_editor(tmp_path, monkeypatch):
    processor, incoming, _ = prepare_processor(tmp_path)
    mock_editor(
        monkeypatch,
        "\n".join(
            [
                "# comentarios",
                "",
                "https://x.com/user/status/1",
                "https://x.com/user/status/2",
            ]
        ),
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


def test_process_tweet_urls_handles_editor_error(tmp_path, monkeypatch):
    processor, _, _ = prepare_processor(tmp_path)

    def failing_get(*args, **kwargs):
        raise requests.RequestException("boom")

    monkeypatch.setattr("pipeline_manager.requests.get", failing_get)
    created = processor.process_tweet_urls()
    assert created == []


def test_process_tweets_pipeline_runs_markdown_subset(tmp_path, monkeypatch):
    processor, _, _ = prepare_processor(tmp_path)
    mock_editor(monkeypatch, "https://x.com/user/status/1")

    with patch(
        "pipeline_manager.fetch_tweet_markdown",
        return_value=("# T1\n\n[Ver en X](https://x.com/1)\n", "Tweet - user-1.md"),
    ):
        captured = {}

        def fake_subset(files):
            captured["files"] = list(files)
            return [processor.config.tweets_dest / "Tweet - processed.md"]

        monkeypatch.setattr(
            processor.tweet_processor,
            "process_markdown_subset",
            fake_subset,
        )

        moved = processor.process_tweets_pipeline()

    assert captured["files"][0].name.startswith("Tweet - user-1")
    assert moved == [processor.config.tweets_dest / "Tweet - processed.md"]


def test_process_tweets_pipeline_skips_when_editor_empty(tmp_path, monkeypatch):
    processor, _, _ = prepare_processor(tmp_path)
    mock_editor(monkeypatch, "# sin urls")

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
    processor, incoming, config = prepare_processor(tmp_path)
    existing_url = "https://x.com/user/status/1"
    config.tweets_processed.write_text(existing_url + "\n", encoding="utf-8")

    mock_editor(
        monkeypatch,
        "\n".join(
            [
                existing_url,
                "https://x.com/user/status/2",
            ]
        ),
    )

    with patch(
        "pipeline_manager.fetch_tweet_markdown",
        return_value=("# T2\n\n[Ver en X](https://x.com/2)\n", "Tweet - user-2.md"),
    ) as mocked:
        created = processor.process_tweet_urls()

    assert len(created) == 1
    assert mocked.call_count == 1
    assert (incoming / "Tweet - user-2.md").exists()
    processed_lines = config.tweets_processed.read_text(encoding="utf-8").splitlines()
    assert processed_lines == [existing_url, "https://x.com/user/status/2"]


def test_process_tweet_urls_appends_processed_file(tmp_path, monkeypatch):
    processor, _, config = prepare_processor(tmp_path)
    url = "https://x.com/user/status/42"
    mock_editor(monkeypatch, url)

    with patch(
        "pipeline_manager.fetch_tweet_markdown",
        return_value=("# T\n\n[Ver en X](https://x.com/42)\n", "Tweet - user-42.md"),
    ):
        processor.process_tweet_urls()

    assert config.tweets_processed.exists()
    assert config.tweets_processed.read_text(encoding="utf-8") == url + "\n"
