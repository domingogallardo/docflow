#!/usr/bin/env python3
"""Tests for AI Markdown summaries."""

from summary_ai import SummaryAIUpdater
from utils import split_front_matter


def test_summary_ai_adds_spanish_docflow_summary(monkeypatch):
    updater = SummaryAIUpdater(object(), delay_seconds=0)
    monkeypatch.setattr(
        updater._ai,
        "_ai_text",
        lambda **kwargs: (
            "El texto defiende una idea central. Explica sus consecuencias "
            "prácticas. Cierra con una implicación útil."
        ),
    )

    updated = updater.add_summary_to_markdown("# Título\n\nContenido del artículo.")

    meta, body = split_front_matter(updated)
    assert meta["docflow_summary"].startswith("El texto defiende")
    assert len(meta["docflow_summary"]) <= 500
    assert body.lstrip().startswith("# Título")


def test_summary_ai_skips_tweets(monkeypatch):
    updater = SummaryAIUpdater(object(), delay_seconds=0)
    called = False

    def fake_ai_text(**kwargs):
        nonlocal called
        called = True
        return "Resumen."

    monkeypatch.setattr(updater._ai, "_ai_text", fake_ai_text)

    md = "---\nsource: tweet\n---\n\n# Tweet\n\nTexto."

    assert updater.add_summary_to_markdown(md) == md
    assert called is False


def test_summary_ai_preserves_existing_summary(monkeypatch):
    updater = SummaryAIUpdater(object(), delay_seconds=0)
    called = False

    def fake_ai_text(**kwargs):
        nonlocal called
        called = True
        return "Resumen nuevo."

    monkeypatch.setattr(updater._ai, "_ai_text", fake_ai_text)

    md = "---\ndocflow_summary: Resumen existente.\n---\n\n# Artículo\n\nTexto."

    assert updater.add_summary_to_markdown(md) == md
    assert called is False


def test_summary_ai_clips_summary_to_500_chars(monkeypatch):
    updater = SummaryAIUpdater(object(), delay_seconds=0)
    monkeypatch.setattr(updater._ai, "_ai_text", lambda **kwargs: "Palabra " * 120)

    updated = updater.add_summary_to_markdown("# Título\n\nContenido del artículo.")
    meta, _ = split_front_matter(updated)

    assert len(meta["docflow_summary"]) <= 500
    assert meta["docflow_summary"].endswith(".")
