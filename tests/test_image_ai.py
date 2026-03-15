"""Tests for image filename sanitization."""

from image_ai import ImageAIDescriber


def test_image_ai_sanitize_filename_replaces_underscores_with_spaces() -> None:
    describer = ImageAIDescriber(ai_client=None)

    assert (
        describer._sanitize_filename("Rainy_pavement_note.png")
        == "Rainy pavement note"
    )
