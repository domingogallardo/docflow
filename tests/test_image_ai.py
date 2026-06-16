"""Tests for image filename sanitization."""

from pathlib import Path

from image_ai import ImageAIDescriber


class _FakeResponse:
    output_text = "Rainy pavement note"


class _FakeResponses:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return _FakeResponse()


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponses()


def test_image_ai_sanitize_filename_replaces_underscores_with_spaces() -> None:
    describer = ImageAIDescriber(ai_client=None)

    assert (
        describer._sanitize_filename("Rainy_pavement_note.png")
        == "Rainy pavement note"
    )


def test_image_ai_uses_low_reasoning_with_room_for_reasoning_tokens(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client = _FakeClient()
    describer = ImageAIDescriber(ai_client=client)
    monkeypatch.setattr(
        describer,
        "_image_data_url",
        lambda _path: "data:image/jpeg;base64,abc",
    )

    image_path = tmp_path / "sample.jpg"
    image_path.write_bytes(b"jpg")

    assert describer.describe_filename(image_path) == "Rainy pavement note"
    assert client.responses.kwargs["reasoning"] == {"effort": "low"}
    assert client.responses.kwargs["max_output_tokens"] == 128
