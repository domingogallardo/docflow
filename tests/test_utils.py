import sys
from pathlib import Path
import pytest

sys.path.append(str(Path(__file__).parent.parent))  # To import utils.py.
import utils
from podcast_processor import PodcastProcessor

def test_extract_episode_title():
    fixture_path = Path(__file__).parent / "fixtures" / "snipd_example.md"
    title = utils.extract_episode_title(fixture_path)
    assert title == "AI Podcast - The Future of AI"

def test_is_podcast_file_true():
    fixture_path = Path(__file__).parent / "fixtures" / "snipd_example.md"
    assert utils.is_podcast_file(fixture_path) is True

def test_is_podcast_file_false():
    # Create a temporary file that is not from Snipd.
    non_podcast_path = Path(__file__).parent / "fixtures" / "not_a_podcast.md"
    non_podcast_path.write_text("# Not a podcast\nSome random markdown content\n", encoding="utf-8")
    try:
        assert utils.is_podcast_file(non_podcast_path) is False
    finally:
        non_podcast_path.unlink()  # Clean up the temporary file.


# Tests for centralized CSS.
def test_get_base_css():
    """Test that verifies get_base_css() returns the correct CSS."""
    css = utils.get_base_css()
    
    # Verify it contains the expected elements.
    assert "-apple-system" in css, "CSS no contiene la tipografía del sistema"
    assert "margin: 6%" in css, "CSS no contiene los márgenes"
    assert "font-weight: bold" in css, "CSS no contiene títulos en negrita"
    assert "border-bottom: 1px solid #eee" in css, "CSS no contiene la línea inferior"
    assert "blockquote" in css, "CSS no contiene estilos de blockquote"
    assert "hr" in css, "CSS no contiene estilos de separadores"


def test_podcast_processor_uses_centralized_css():
    """Test that verifies PodcastProcessor uses centralized CSS."""
    processor = PodcastProcessor(Path("/tmp"), Path("/tmp"))
    html = processor._wrap_html("Test Podcast", "<p>Contenido de prueba</p>")
    
    # Verify it uses the base CSS.
    assert "-apple-system" in html, "PodcastProcessor no usa tipografía del sistema"
    assert "margin: 6%" in html, "PodcastProcessor no usa márgenes centralizados"
    assert "#667eea" in html, "PodcastProcessor no usa color de podcast"
    assert "border-left: 4px solid #667eea" in html, "PodcastProcessor no usa borde azul podcast"


def test_clean_duplicate_markdown_links():
    """Test to verify cleaning duplicated Markdown links."""
    from utils import clean_duplicate_markdown_links
    
    # Test with a duplicated link.
    text_with_duplicate = """See more details: [https://people.idsia.ch/~juergen/who-invented-backpropagation.html](https://people.idsia.ch/~juergen/who-invented-backpropagation.html)"""
    
    result = clean_duplicate_markdown_links(text_with_duplicate)
    
    # Verify the URL was truncated and cleaned.
    assert "people.idsia.ch/~juergen/who-invented-back..." in result
    assert result.count("https://people.idsia.ch/~juergen/who-invented-backpropagation.html") == 1  # Only in the link.
    
    # Test with a normal (non-duplicated) link - should not change.
    text_normal = """See [this article](https://example.com) for more info."""
    result_normal = clean_duplicate_markdown_links(text_normal)
    assert result_normal == text_normal
    
    # Test with a short URL - should not be truncated.
    text_short = """Visit [https://x.com/test](https://x.com/test)"""
    result_short = clean_duplicate_markdown_links(text_short)
    assert "x.com/test" in result_short
    assert "..." not in result_short


def test_add_margins_wraps_images(tmp_path):
    html = tmp_path / "sample.html"
    html.write_text("<html><head></head><body><p>hola</p><img src=\"https://img.test/x.jpg\"></body></html>", encoding="utf-8")

    utils.add_margins_to_html_files(tmp_path)

    out = html.read_text(encoding="utf-8")
    assert '<a href="https://img.test/x.jpg" rel="noopener" target="_blank"><img src="https://img.test/x.jpg"/></a>' in out
    assert "cursor: zoom-in" in out


def test_convert_urls_integration():
    """End-to-end test for URL processing (dedupe + conversion)."""
    from utils import convert_urls_to_links
    
    test_text = """Enlaces duplicados: [https://people.idsia.ch/~juergen/very-long-path-that-should-be-truncated.html](https://people.idsia.ch/~juergen/very-long-path-that-should-be-truncated.html)
    
URL aislada: https://x.com/SchmidhuberAI/status/1950194864940835159"""
    
    result = convert_urls_to_links(test_text)
    
    # Verify the duplicated link was cleaned.
    assert "people.idsia.ch/~juergen/very-long-path-th..." in result
    
    # Verify the standalone URL was converted to a link.
    assert "[https://x.com/SchmidhuberAI/status/1950194864940835159](https://x.com/SchmidhuberAI/status/1950194864940835159)" in result 


# (tests for is_instapaper_starred_file moved to tests/test_instapaper_starred_utils.py)
