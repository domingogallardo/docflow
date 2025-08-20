#!/usr/bin/env python3
"""Tests for process_documents CLI selection."""
import sys
import process_documents


def run_main(monkeypatch, tmp_path, args):
    calls = []

    class DummyProcessor:
        def __init__(self, config):
            pass

        def process_all(self):
            calls.append("all")
            return True

        def process_podcasts(self):
            calls.append("podcasts")
            return []

        def process_tweets(self):
            calls.append("tweets")
            return []

        def process_instapaper_posts(self):
            calls.append("posts")
            return []

        def process_pdfs(self):
            calls.append("pdfs")
            return []

        def register_all_files(self):
            calls.append("register")

    monkeypatch.setattr(process_documents, "DocumentProcessor", DummyProcessor)
    monkeypatch.setattr(process_documents.cfg, "BASE_DIR", tmp_path)
    monkeypatch.setenv("DOCPIPE_YEAR", "2025")

    monkeypatch.setattr(sys, "argv", ["process_documents.py", *args])
    process_documents.main()
    return calls


def test_default_runs_all(monkeypatch, tmp_path):
    calls = run_main(monkeypatch, tmp_path, [])
    assert calls == ["all"]


def test_selective_processing(monkeypatch, tmp_path):
    calls = run_main(monkeypatch, tmp_path, ["tweets", "pdfs"])
    assert calls == ["tweets", "pdfs", "register"]

