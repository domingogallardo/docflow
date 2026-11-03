#!/usr/bin/env python3
"""Tests for AI Markdown summaries."""

from summary_ai import SummaryAIUpdater
from utils import split_front_matter


def test_summary_ai_sends_terra_detail_prompt_and_medium_verbosity():
    from types import SimpleNamespace

    calls = []
    outputs = iter(["English", "A workshop covers JavaScript, Gulp, Bower and npm."])

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_text=next(outputs))

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    updater = SummaryAIUpdater(client, delay_seconds=0)
    updated = updater.add_summary_to_markdown("# Workshop\n\nJavaScript, Gulp, Bower and npm.")

    meta, _ = split_front_matter(updated)
    assert meta["docflow_summary"] == "A workshop covers JavaScript, Gulp, Bower and npm."
    assert [call["model"] for call in calls] == ["gpt-5-nano", "gpt-6.1-terra"]
    request = calls[1]
    assert request["text"] == {"verbosity": "medium"}
    assert request["reasoning"] == {"effort": "low"}
    assert request["max_output_tokens"] == 2048
    assert "430–500 characters" in request["instructions"]
    assert "Keep specific technical names, tools, libraries" in request["instructions"]
    assert "If the text lacks substantive content" in request["instructions"]
    assert "3 to 5 sentences" not in request["instructions"]


def test_summary_ai_adds_spanish_docflow_summary(monkeypatch):
    updater = SummaryAIUpdater(object(), delay_seconds=0)
    monkeypatch.setattr(updater._language_ai, "_detect_language", lambda snippet: "Spanish")
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


def test_summary_ai_uses_detected_article_language(monkeypatch):
    updater = SummaryAIUpdater(object(), delay_seconds=0)
    calls = []

    monkeypatch.setattr(updater._language_ai, "_detect_language", lambda snippet: "English")

    def fake_ai_text(**kwargs):
        calls.append(kwargs)
        return "The article argues one central idea. It explains the evidence. It closes with practical implications."

    monkeypatch.setattr(updater._ai, "_ai_text", fake_ai_text)

    updated = updater.add_summary_to_markdown(
        "# Title\n\nThis article explains how software teams can use AI tools well."
    )

    meta, _ = split_front_matter(updated)
    assert meta["docflow_summary"].startswith("The article argues")
    assert "summary in English," in calls[0]["system"]


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
    monkeypatch.setattr(updater._language_ai, "_detect_language", lambda snippet: "Spanish")
    monkeypatch.setattr(updater._ai, "_ai_text", lambda **kwargs: "Palabra " * 120)

    updated = updater.add_summary_to_markdown("# Título\n\nContenido del artículo.")
    meta, _ = split_front_matter(updated)

    assert len(meta["docflow_summary"]) <= 500
    assert meta["docflow_summary"].endswith(".")
