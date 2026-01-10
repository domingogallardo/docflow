"""Tests for TitleAIUpdater language handling."""
from pathlib import Path

from title_ai import TitleAIUpdater


def test_extract_language_sample_ignores_tweet_boilerplate(tmp_path: Path) -> None:
    content = (
        "---\n"
        "source: tweet\n"
        "tweet_url: https://x.com/user/status/1\n"
        "tweet_author: \"@sebkrier\"\n"
        "tweet_author_name: \"S\u00e9b Krier\"\n"
        "---\n"
        "\n"
        "# Tweet by S\u00e9b Krier (@sebkrier)\n"
        "# Thread by S\u00e9b Krier (@sebkrier)\n"
        "\n"
        "[View on X](https://x.com/user/status/1)\n"
        "\n"
        "![avatar](https://example.com/a.jpg)\n"
        "\n"
        "S\u00e9b Krier\n"
        "@sebkrier\n"
        "\u00b7\n"
        "6h\n"
        "I also don't have particularly good intuitions about what a world with ASI looks like.\n"
    )
    path = tmp_path / "Tweet - test.md"
    path.write_text(content, encoding="utf-8")

    updater = TitleAIUpdater(ai_client=object())
    sample = updater._extract_language_sample(path)

    assert "I also don't have" in sample
    assert "tweet_url" not in sample
    assert "Tweet by" not in sample
    assert "Thread by" not in sample
    assert "View on X" not in sample
    assert "S\u00e9b" not in sample
    assert "@sebkrier" not in sample


def test_detect_language_fallback_ignores_single_accent(monkeypatch) -> None:
    updater = TitleAIUpdater(ai_client=object())

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(updater, "_ai_text", _raise)

    sample = "S\u00e9b Krier says I don't have good intuitions about ASI."
    assert updater._detect_language(sample) == "English"


def test_detect_language_fallback_spanish_with_stopwords(monkeypatch) -> None:
    updater = TitleAIUpdater(ai_client=object())

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(updater, "_ai_text", _raise)

    sample = "No tengo buenas intuiciones sobre lo que pasa en el futuro."
    assert updater._detect_language(sample) == "Spanish"
