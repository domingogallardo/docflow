import sys
from pathlib import Path
import pytest

sys.path.append(str(Path(__file__).parent.parent))
from clean_snip import clean_lines

def test_clean_lines_removes_click_to_expand_and_details():
    fixture_path = Path(__file__).parent / "fixtures" / "snipd_clean_example.md"
    with open(fixture_path, encoding="utf-8") as f:
        original_lines = f.readlines()
    cleaned = clean_lines(original_lines)
    cleaned_text = "".join(cleaned)
    # No debe quedar "Click to expand" ni <details> ni <summary>
    assert "Click to expand" not in cleaned_text
    assert "<details" not in cleaned_text
    assert "</details>" not in cleaned_text
    assert "<summary>" not in cleaned_text
    # El contenido útil (por ejemplo, el título del episodio) debe seguir presente
    assert "Episode metadata" in cleaned_text
    assert "## Snips" in cleaned_text
    assert "The Path Is the Goal" in cleaned_text
    assert "They're just choosing things they like" in cleaned_text 