import sys
from pathlib import Path
import pytest

sys.path.append(str(Path(__file__).parent.parent))  # Para importar utils.py
import utils
from tweet_processor import TweetProcessor
from podcast_processor import PodcastProcessor

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


# Tests para CSS centralizado
def test_get_base_css():
    """Test que verifica que get_base_css() devuelve el CSS correcto."""
    css = utils.get_base_css()
    
    # Verificar que contiene los elementos esperados
    assert "-apple-system" in css, "CSS no contiene la tipografía del sistema"
    assert "margin: 6%" in css, "CSS no contiene los márgenes"
    assert "font-weight: bold" in css, "CSS no contiene títulos en negrita"
    assert "border-bottom: 1px solid #eee" in css, "CSS no contiene la línea inferior"
    assert "blockquote" in css, "CSS no contiene estilos de blockquote"
    assert "hr" in css, "CSS no contiene estilos de separadores"


def test_tweet_processor_uses_centralized_css():
    """Test que verifica que TweetProcessor usa el CSS centralizado."""
    processor = TweetProcessor(Path("/tmp"), Path("/tmp"))
    html = processor._wrap_html("Test Tweet", "<p>Contenido de prueba</p>")
    
    # Verificar que usa el CSS base
    assert "-apple-system" in html, "TweetProcessor no usa tipografía del sistema"
    assert "margin: 6%" in html, "TweetProcessor no usa márgenes centralizados"
    assert "#1DA1F2" in html, "TweetProcessor no usa color de Twitter"
    assert "border-left: 4px solid #1DA1F2" in html, "TweetProcessor no usa borde azul Twitter"


def test_podcast_processor_uses_centralized_css():
    """Test que verifica que PodcastProcessor usa el CSS centralizado."""
    processor = PodcastProcessor(Path("/tmp"), Path("/tmp"))
    html = processor._wrap_html("Test Podcast", "<p>Contenido de prueba</p>")
    
    # Verificar que usa el CSS base
    assert "-apple-system" in html, "PodcastProcessor no usa tipografía del sistema"
    assert "margin: 6%" in html, "PodcastProcessor no usa márgenes centralizados"
    assert "#667eea" in html, "PodcastProcessor no usa color de podcast"
    assert "border-left: 4px solid #667eea" in html, "PodcastProcessor no usa borde azul podcast"


def test_processors_maintain_different_colors():
    """Test que verifica que cada procesador mantiene sus colores específicos."""
    tweet_proc = TweetProcessor(Path("/tmp"), Path("/tmp"))
    podcast_proc = PodcastProcessor(Path("/tmp"), Path("/tmp"))
    
    tweet_html = tweet_proc._wrap_html("Tweet", "<p>test</p>")
    podcast_html = podcast_proc._wrap_html("Podcast", "<p>test</p>")
    
    # Verificar colores específicos
    assert "#1DA1F2" in tweet_html and "#1DA1F2" not in podcast_html, "Colores no diferenciados correctamente"
    assert "#667eea" in podcast_html and "#667eea" not in tweet_html, "Colores no diferenciados correctamente"


def test_clean_duplicate_markdown_links():
    """Test para verificar la limpieza de enlaces Markdown duplicados."""
    from utils import clean_duplicate_markdown_links
    
    # Test con enlace duplicado
    text_with_duplicate = """See more details: [https://people.idsia.ch/~juergen/who-invented-backpropagation.html](https://people.idsia.ch/~juergen/who-invented-backpropagation.html)"""
    
    result = clean_duplicate_markdown_links(text_with_duplicate)
    
    # Verificar que la URL se truncó y limpió
    assert "people.idsia.ch/~juergen/who-invented-back..." in result
    assert result.count("https://people.idsia.ch/~juergen/who-invented-backpropagation.html") == 1  # Solo en el enlace
    
    # Test con enlace normal (no duplicado) - no debe cambiar
    text_normal = """See [this article](https://example.com) for more info."""
    result_normal = clean_duplicate_markdown_links(text_normal)
    assert result_normal == text_normal
    
    # Test con URL corta - no debe truncarse
    text_short = """Visit [https://x.com/test](https://x.com/test)"""
    result_short = clean_duplicate_markdown_links(text_short)
    assert "x.com/test" in result_short
    assert "..." not in result_short


def test_convert_urls_integration():
    """Test integral del procesamiento de URLs (duplicados + conversión)."""
    from utils import convert_urls_to_links
    
    test_text = """Enlaces duplicados: [https://people.idsia.ch/~juergen/very-long-path-that-should-be-truncated.html](https://people.idsia.ch/~juergen/very-long-path-that-should-be-truncated.html)
    
URL aislada: https://x.com/SchmidhuberAI/status/1950194864940835159"""
    
    result = convert_urls_to_links(test_text)
    
    # Verificar que el enlace duplicado se limpió
    assert "people.idsia.ch/~juergen/very-long-path-th..." in result
    
    # Verificar que la URL aislada se convirtió a enlace
    assert "[https://x.com/SchmidhuberAI/status/1950194864940835159](https://x.com/SchmidhuberAI/status/1950194864940835159)" in result 


# (tests de is_instapaper_starred_file se movieron a tests/test_instapaper_starred_utils.py
