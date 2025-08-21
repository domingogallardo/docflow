#!/usr/bin/env python3
"""
Tests para InstapaperProcessor
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from instapaper_processor import InstapaperProcessor


def test_star_prefix_stripping_variants():
    """Quita prefijos de estrella comunes del título."""
    p = InstapaperProcessor(Path("/tmp/incoming"), Path("/tmp/dest"))
    cases = [
        ("⭐ Title", "Title"),
        ("⭐️ Title", "Title"),
        ("★ Title", "Title"),
        ("✪ Title", "Title"),
        ("✭ Title", "Title"),
        ("  ⭐   Title", "Title"),
        ("No Star Title", "No Star Title"),
    ]
    for raw, expected in cases:
        assert p._strip_star_prefix(raw) == expected


def test_instapaper_star_detection_and_propagation_from_read_html(tmp_path):
    """Detecta estrella en /read y la propaga a HTML y Markdown."""
    incoming = tmp_path / "Incoming"
    destination = tmp_path / "Posts"
    incoming.mkdir()
    destination.mkdir()

    # Página de lectura con estrella en <title> y en H1
    read_html = """<!DOCTYPE html>
    <html>
    <head>
      <title>⭐ Starred Sample</title>
    </head>
    <body>
      <div id=\"titlebar\">
        <h1>⭐ Starred Sample</h1>
        <div class=\"origin_line\">Example.com</div>
      </div>
      <div id=\"story\"><p>Body</p></div>
    </body>
    </html>"""

    processor = InstapaperProcessor(incoming, destination)

    # Mockear la sesión HTTP
    mock_resp = Mock()
    mock_resp.text = read_html
    processor.session = Mock()
    processor.session.get.return_value = mock_resp

    # Descargar y escribir el HTML del artículo
    html_path = processor._download_article("12345")
    html_text = html_path.read_text(encoding="utf-8")

    # Debe contener la marca de estrella y atributo en <html>
    assert '<meta name="instapaper-starred" content="true">' in html_text
    assert 'data-instapaper-starred="true"' in html_text
    # El título debe estar limpio (sin prefijo de estrella)
    assert "<title>Starred Sample</title>" in html_text
    assert "<h1>Starred Sample</h1>" in html_text

    # Convertir a Markdown debe añadir front matter
    processor._convert_html_to_markdown()
    md_path = html_path.with_suffix('.md')
    md_text = md_path.read_text(encoding="utf-8")
    assert md_text.startswith("---\ninstapaper_starred: true\n---\n")
    # No debe quedar estrella al inicio del encabezado
    assert not md_text.splitlines()[3].startswith("# ⭐")


def test_instapaper_processor_with_existing_html(tmp_path):
    """Test que verifica el procesamiento de archivos HTML existentes (sin descarga)."""
    
    # Preparar
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Posts"
    destination.mkdir()
    
    # Crear archivo HTML de prueba
    html_file = incoming / "test_article.html"
    html_content = """<!DOCTYPE html>
    <html>
    <head><title>Test Article</title></head>
    <body>
        <h1>Test Article</h1>
        <p>This is a test article with <img src="http://example.com/image.jpg" width="500"> some content.</p>
    </body>
    </html>"""
    html_file.write_text(html_content)
    
    # Crear procesador con mocks para APIs externas
    processor = InstapaperProcessor(incoming, destination)
    
    # Mock para evitar llamadas reales a Anthropic API
    with patch.object(processor.anthropic_client, 'messages') as mock_anthropic:
        # Mock respuesta de detección de idioma
        mock_lang_response = Mock()
        mock_lang_response.content = [Mock(text="inglés")]
        
        # Mock respuesta de generación de título
        mock_title_response = Mock()
        mock_title_response.content = [Mock(text="Amazing Test Article")]
        
        mock_anthropic.create.side_effect = [mock_lang_response, mock_title_response]
        
        # Ejecutar procesamiento
        moved_posts = processor.process_instapaper_posts()
    
    # Verificar
    assert len(moved_posts) >= 1  # Al menos archivos procesados
    
    # Verificar que se generó el archivo Markdown
    md_files = list(destination.glob("*.md"))
    assert len(md_files) >= 1
    
    # Verificar que los archivos fueron renombrados
    renamed_files = list(destination.glob("Amazing Test Article*"))
    assert len(renamed_files) >= 1


def test_instapaper_processor_no_credentials(tmp_path):
    """Test que verifica el comportamiento cuando no hay credenciales de Instapaper."""
    
    # Preparar
    incoming = tmp_path / "Incoming" 
    incoming.mkdir()
    destination = tmp_path / "Posts"
    
    # Crear procesador
    processor = InstapaperProcessor(incoming, destination)
    
    # Mock para simular falta de credenciales
    with patch('instapaper_processor.INSTAPAPER_USERNAME', None), \
         patch('instapaper_processor.INSTAPAPER_PASSWORD', None):
        
        # Ejecutar
        moved_posts = processor.process_instapaper_posts()
    
    # Verificar - debería continuar sin error y devolver lista vacía
    assert moved_posts == []


def test_instapaper_processor_html_encoding_fix(tmp_path):
    """Test que verifica la corrección de codificación HTML."""
    
    # Preparar
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Posts"
    
    # Crear archivo HTML sin charset
    html_file = incoming / "no_charset.html"
    html_content = """<html>
    <head><title>No Charset</title></head>
    <body>Content without charset</body>
    </html>"""
    html_file.write_text(html_content)
    
    # Crear procesador
    processor = InstapaperProcessor(incoming, destination)
    
    # Ejecutar solo la corrección de codificación
    processor._fix_html_encoding()
    
    # Verificar que se agregó el charset
    updated_content = html_file.read_text()
    assert '<meta charset="utf-8">' in updated_content


def test_instapaper_processor_image_width_reduction(tmp_path):
    """Test que verifica la reducción de ancho de imágenes."""
    
    # Preparar
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Posts"
    
    # Crear archivo HTML con imagen grande
    html_file = incoming / "big_image.html"
    html_content = """<html>
    <body>
        <img src="http://example.com/big.jpg" width="800" height="600">
        <p>Content</p>
    </body>
    </html>"""
    html_file.write_text(html_content)
    
    # Crear procesador
    processor = InstapaperProcessor(incoming, destination)
    
    # Mock para get_image_width que devuelva ancho grande
    with patch.object(processor, '_get_image_width', return_value=800):
        # Ejecutar reducción de imágenes
        processor._reduce_images_width()
    
    # Verificar que se redujo el ancho
    updated_content = html_file.read_text()
    assert 'width="300"' in updated_content
    assert 'height="600"' not in updated_content  # height debería eliminarse


def test_instapaper_processor_title_generation(tmp_path):
    """Test que verifica la generación de títulos con IA."""
    
    # Preparar
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Posts"
    
    # Crear archivo Markdown de prueba
    md_file = incoming / "original_title.md"
    md_content = """# Original Title

This is a test article about artificial intelligence and machine learning.
It contains interesting information about the latest developments in the field.
The content is written in English and discusses various technical topics.
"""
    md_file.write_text(md_content)
    
    # Crear procesador
    processor = InstapaperProcessor(incoming, destination)
    
    # Mock para Anthropic API
    with patch.object(processor.anthropic_client, 'messages') as mock_anthropic:
        # Mock respuesta de detección de idioma
        mock_lang_response = Mock()
        mock_lang_response.content = [Mock(text="inglés")]
        
        # Mock respuesta de generación de título
        mock_title_response = Mock()
        mock_title_response.content = [Mock(text="AI and Machine Learning - Latest Developments")]
        
        mock_anthropic.create.side_effect = [mock_lang_response, mock_title_response]
        
        # Ejecutar generación de títulos
        processor._update_titles_with_ai()
    
    # Verificar que el archivo fue renombrado
    renamed_files = list(incoming.glob("AI and Machine Learning - Latest Developments*"))
    assert len(renamed_files) >= 1
    
    # Verificar que se marcó como procesado
    assert processor.done_file.exists()
    done_content = processor.done_file.read_text()
    assert "AI and Machine Learning - Latest Developments" in done_content 
