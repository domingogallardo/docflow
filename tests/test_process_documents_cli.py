#!/usr/bin/env python3
"""Tests for process_documents CLI selection."""
import sys
from types import SimpleNamespace
import pytest
import process_documents


def run_main(monkeypatch, tmp_path, args):
    calls = []

    class DummyProcessor:
        def __init__(self, base_dir, year):
            pass

        def process_all(self):
            calls.append("all")
            return True

        def process_podcasts(self):
            calls.append("podcasts")
            return []

        def process_tweets_pipeline(self):
            calls.append("tweets")
            return []
        def process_instapaper_posts(self):
            calls.append("posts")
            return []

        def process_pdfs(self):
            calls.append("pdfs")
            return []

        def process_images(self):
            calls.append("images")
            return []

        def process_markdown(self):
            calls.append("md")
            return []

        def register_all_files(self):
            calls.append("register")

    monkeypatch.setattr(process_documents, "DocumentProcessor", DummyProcessor)
    monkeypatch.setattr(process_documents.cfg, "BASE_DIR", tmp_path)
    monkeypatch.setenv("DOCPIPE_YEAR", "2025")

    monkeypatch.setattr(sys, "argv", ["process_documents.py", *args])
    process_documents.main()
    return calls


def test_no_args_shows_help_and_exits(monkeypatch, tmp_path, capsys):
    # Sin argumentos debe mostrar ayuda y salir con código 2
    monkeypatch.setattr(process_documents.cfg, "BASE_DIR", tmp_path)
    monkeypatch.setenv("DOCPIPE_YEAR", "2025")
    monkeypatch.setattr(sys, "argv", ["process_documents.py"]) 
    with pytest.raises(SystemExit) as e:
        process_documents.main()
    assert e.value.code == 2
    captured = capsys.readouterr()
    assert "usage:" in captured.err.lower()


def test_selective_processing(monkeypatch, tmp_path):
    calls = run_main(monkeypatch, tmp_path, ["tweets", "pdfs", "md"])
    assert calls == ["tweets", "pdfs", "md", "register"]


def test_all_processing(monkeypatch, tmp_path):
    calls = run_main(monkeypatch, tmp_path, ["all"])
    assert calls == ["all"]


def test_process_images(monkeypatch, tmp_path):
    calls = run_main(monkeypatch, tmp_path, ["images"])
    assert calls == ["images", "register"]


def test_default_year_without_env(monkeypatch):
    monkeypatch.delenv("DOCPIPE_YEAR", raising=False)
    args = SimpleNamespace(year=None)

    assert process_documents.get_year_from_args_and_env(args) == 2026
