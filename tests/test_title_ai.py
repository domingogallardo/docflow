"""Tests for TitleAIUpdater language handling."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from title_ai import TitleAIUpdater


class _FakeResponse:
    def __init__(
        self,
        output_text: str = "Generated title",
        *,
        status: str | None = None,
        incomplete_reason: str | None = None,
    ) -> None:
        self.output_text = output_text
        self.status = status
        self.incomplete_details = (
            {"reason": incomplete_reason} if incomplete_reason else None
        )


class _FakeResponses:
    def __init__(self, responses: list[_FakeResponse] | None = None) -> None:
        self.calls = []
        self._responses = responses or [_FakeResponse()]

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class _FakeClient:
    def __init__(self, responses: list[_FakeResponse] | None = None) -> None:
        self.responses = _FakeResponses(responses)


def test_ai_text_uses_low_reasoning_effort() -> None:
    client = _FakeClient()
    updater = TitleAIUpdater(ai_client=client)

    assert updater._ai_text(system="System", prompt="Prompt", max_tokens=8) == "Generated title"
    assert client.responses.calls[0]["reasoning"] == {"effort": "low"}
    assert client.responses.calls[0]["model"] == "gpt-5-nano"
    assert client.responses.calls[0]["text"] == {"verbosity": "low"}
    assert client.responses.calls[0]["max_output_tokens"] == 128


def test_ai_text_retries_incomplete_token_budget() -> None:
    client = _FakeClient(
        [
            _FakeResponse("", status="incomplete", incomplete_reason="max_output_tokens"),
            _FakeResponse("Generated title"),
        ]
    )
    updater = TitleAIUpdater(ai_client=client)

    assert updater._ai_text(system="System", prompt="Prompt", max_tokens=8) == "Generated title"
    assert [call["max_output_tokens"] for call in client.responses.calls] == [128, 256]


@pytest.mark.parametrize("nested", [False, True])
def test_ai_text_rejects_partial_text_before_retrying(nested: bool) -> None:
    partial = _FakeResponse(
        "Federico", status="incomplete", incomplete_reason="max_output_tokens"
    )
    if nested:
        partial.output_text = ""
        partial.output = [{"content": [{"text": "Federico"}]}]
        partial.incomplete_details = SimpleNamespace(reason="max_output_tokens")
    client = _FakeClient([partial, _FakeResponse("Federico Viticci - Multiple Windows")])
    updater = TitleAIUpdater(ai_client=client)

    assert updater._generate_title("Article", "English", "clipper-article") == (
        "Federico Viticci - Multiple Windows"
    )
    assert [call["max_output_tokens"] for call in client.responses.calls] == [512, 1024]


@pytest.mark.parametrize("reason", ["max_output_tokens", "content_filter"])
def test_ai_text_never_accepts_incomplete_text_on_last_attempt(reason: str) -> None:
    client = _FakeClient([
        _FakeResponse("Federico", status="incomplete", incomplete_reason=reason)
    ])
    updater = TitleAIUpdater(ai_client=client)

    with pytest.raises(RuntimeError, match=f"Incomplete OpenAI response: {reason}"):
        updater._ai_text(system="System", prompt="Prompt", max_tokens=128, retries=1)


def test_update_titles_does_not_rename_after_incomplete_response(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "Original title.md"
    path.write_text("Article content", encoding="utf-8")
    client = _FakeClient([
        _FakeResponse("Federico", status="incomplete", incomplete_reason="max_output_tokens")
        for _ in range(6)
    ])
    updater = TitleAIUpdater(ai_client=client, delay_seconds=0)
    monkeypatch.setattr(updater, "_detect_language", lambda _sample: "English")
    renamed = []

    updater.update_titles([path], lambda *args: renamed.append(args))

    assert renamed == []
    assert path.read_text(encoding="utf-8") == "Article content"
    assert len(client.responses.calls) == 6


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


def test_tweet_posted_kind_reads_repost_metadata(tmp_path: Path) -> None:
    content = (
        "---\n"
        "source: tweet\n"
        "tweet_capture_source: posted\n"
        "tweet_posted_kind: repost\n"
        "---\n"
        "\n"
        "# Tweet by Someone\n"
    )
    path = tmp_path / "Tweet posted - test.md"
    path.write_text(content, encoding="utf-8")

    updater = TitleAIUpdater(ai_client=object())

    assert updater._tweet_posted_kind(path) == "repost"


def test_generate_title_prefixes_reposts(monkeypatch) -> None:
    updater = TitleAIUpdater(ai_client=object())
    monkeypatch.setattr(updater, "_ai_text", lambda **_kwargs: "Tweet - Useful thread about AI")

    title = updater._generate_title(
        "Useful thread about AI",
        "English",
        "Tweet posted - author-123",
        tweet_posted_kind="repost",
    )

    assert title == "Repost - Useful thread about AI"


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
