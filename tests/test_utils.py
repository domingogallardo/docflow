import sys
from pathlib import Path
import pytest

sys.path.append(str(Path(__file__).parent.parent))  # Para importar utils.py
import utils

def test_extract_episode_title():
    fixture_path = Path(__file__).parent / "fixtures" / "snipd_example.md"
    title = utils.extract_episode_title(fixture_path)
    assert title == "AI Podcast - The Future of AI" 