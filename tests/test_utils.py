import sys
from pathlib import Path
import pytest

sys.path.append(str(Path(__file__).parent.parent))  # Para importar utils.py
import utils

def test_extract_episode_title():
    fixture_path = Path(__file__).parent / "fixtures" / "snipd_example.md"
    title = utils.extract_episode_title(fixture_path)
    assert title == "AI Podcast - The Future of AI"

def test_is_podcast_file_true():
    fixture_path = Path(__file__).parent / "fixtures" / "snipd_example.md"
    assert utils.is_podcast_file(fixture_path) is True

def test_is_podcast_file_false():
    # Crear un archivo temporal que no es de Snipd
    non_podcast_path = Path(__file__).parent / "fixtures" / "not_a_podcast.md"
    non_podcast_path.write_text("# Not a podcast\nSome random markdown content\n", encoding="utf-8")
    try:
        assert utils.is_podcast_file(non_podcast_path) is False
    finally:
        non_podcast_path.unlink()  # Limpiar el archivo temporal 