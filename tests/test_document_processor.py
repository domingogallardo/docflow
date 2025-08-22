#!/usr/bin/env python3
"""
Tests para DocumentProcessor
"""
import pytest
from pathlib import Path
import time

from pipeline_manager import DocumentProcessor, DocumentProcessorConfig


def test_document_processor_integration(tmp_path):
    """Test de integración completo del pipeline usando directorios temporales."""
    
    # 1. Preparar estructura de directorios
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    
    # 2. Crear archivos de prueba
    # PDF de prueba
    pdf_file = incoming / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 test content")
    
    # Archivo de podcast de Snipd
    podcast_file = incoming / "snipd_test.md"
    podcast_content = """# Test Podcast

## Episode metadata
- Episode title: Test Episode
- Show: Test Show
- Owner / Host: Test Host

## Snips
- Some test content
"""
    podcast_file.write_text(podcast_content, encoding="utf-8")
    
    # HTML de post regular (simulando Instapaper)
    html_file = incoming / "test_post.html"
    html_file.write_text("<html><head><title>Test Post</title></head><body>Content</body></html>", encoding="utf-8")
    
    # 3. Crear configuración de test
    config = DocumentProcessorConfig(base_dir=tmp_path, year=2025)
    
    # 4. Crear y ejecutar procesador
    processor = DocumentProcessor(config)
    success = processor.process_all()
    
    # 6. Verificar que el pipeline se ejecutó exitosamente
    assert success is True
    
    # 7. Verificar que los archivos se movieron correctamente
    assert (tmp_path / "Podcasts" / "Podcasts 2025" / "Test Show - Test Episode.md").exists()
    assert (tmp_path / "Posts" / "Posts 2025").exists()
    assert (tmp_path / "Pdfs" / "Pdfs 2025" / "test.pdf").exists()


def test_process_podcasts_only(tmp_path):
    """Test específico para el procesamiento de podcasts."""
    
    # Preparar
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    
    podcast_file = incoming / "podcast.md"
    podcast_content = """# Test Podcast

## Episode metadata
- Episode title: Amazing Episode
- Show: Great Show
- Owner / Host: Host Name

## Snips
- Great content here
"""
    podcast_file.write_text(podcast_content, encoding="utf-8")
    
    config = DocumentProcessorConfig(base_dir=tmp_path, year=2025)
    processor = DocumentProcessor(config)
    
    # Ejecutar solo fase de podcasts
    moved_podcasts = processor.process_podcasts()
    
    # Verificar - puede ser 1 o 2 archivos dependiendo de si se genera HTML
    assert len(moved_podcasts) >= 1  # Al menos el .md
    assert (tmp_path / "Podcasts" / "Podcasts 2025" / "Great Show - Amazing Episode.md").exists()
    
    # Scripts externos no se ejecutan (integrado en procesadores): ya no se valida vía runner


def test_bump_starred_instapaper_html(tmp_path):
    """Los HTML marcados como 'starred' en Instapaper reciben bump automático."""

    incoming = tmp_path / "Incoming"
    incoming.mkdir()

    # Crear un HTML con meta de 'starred'
    starred_html = incoming / "sample.html"
    starred_html.write_text(
        """<!DOCTYPE html>
        <html data-instapaper-starred=\"true\">
        <head>
          <meta charset=\"UTF-8\">
          <meta name=\"instapaper-starred\" content=\"true\">
          <title>Sample</title>
        </head>
        <body><h1>Sample</h1></body>
        </html>
        """,
        encoding="utf-8",
    )

    config = DocumentProcessorConfig(base_dir=tmp_path, year=2025)
    processor = DocumentProcessor(config)

    # Evitar ejecutar el pipeline real de Instapaper: simulamos el movimiento
    def fake_process_instapaper_posts():
        config.posts_dest.mkdir(parents=True, exist_ok=True)
        dest = config.posts_dest / starred_html.name
        dest.write_text(starred_html.read_text(encoding="utf-8"), encoding="utf-8")
        return [dest]

    processor.instapaper_processor.process_instapaper_posts = fake_process_instapaper_posts

    processor.process_instapaper_posts()

    moved = config.posts_dest / "sample.html"
    assert moved.exists()

    # Debe tener un mtime muy en el futuro (aprox. > 90 años)
    future_threshold = time.time() + 90 * 365 * 24 * 3600
    assert moved.stat().st_mtime > future_threshold


 
