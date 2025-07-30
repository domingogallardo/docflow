#!/usr/bin/env python3
"""
Tests para DocumentProcessor
"""
import pytest
from pathlib import Path

from pipeline_manager import DocumentProcessor, DocumentProcessorConfig


class MockScriptRunner:
    """Mock del script runner para tests."""
    
    def __init__(self):
        self.executed_scripts = []
    
    def run_script(self, script_name: str, *args) -> bool:
        self.executed_scripts.append((script_name, *args))
        return True
    
    def run_script_with_dir(self, script_name: str, directory: str) -> bool:
        self.executed_scripts.append((script_name, "--dir", directory))
        return True


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
    
    # 4. Crear mock del script runner
    mock_runner = MockScriptRunner()
    
    # 5. Crear y ejecutar procesador
    processor = DocumentProcessor(config, script_runner=mock_runner)
    success = processor.process_all()
    
    # 6. Verificar que el pipeline se ejecutó exitosamente
    assert success is True
    
    # 7. Verificar que NO se ejecutan scripts independientes (todo está integrado)
    executed_scripts = [script[0] for script in mock_runner.executed_scripts]
    
    # Ya no se ejecutan scripts independientes - márgenes integrados en cada procesador
    assert len(executed_scripts) == 0
    
    # Scripts de podcasts ya NO aparecen porque están integrados en PodcastProcessor
    # Scripts de Instapaper ya NO aparecen porque están integrados en InstapaperProcessor
    
    # 8. Verificar que los archivos se movieron correctamente
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
    mock_runner = MockScriptRunner()
    processor = DocumentProcessor(config, script_runner=mock_runner)
    
    # Ejecutar solo fase de podcasts
    moved_podcasts = processor.process_podcasts()
    
    # Verificar - puede ser 1 o 2 archivos dependiendo de si se genera HTML
    assert len(moved_podcasts) >= 1  # Al menos el .md
    assert (tmp_path / "Podcasts" / "Podcasts 2025" / "Great Show - Amazing Episode.md").exists()
    
    # Verificar scripts ejecutados - ya no se ejecutan independientemente
    executed_scripts = [script[0] for script in mock_runner.executed_scripts]
    # Ya no se ejecuta add_margin_html.py independientemente (integrado en procesadores)
    assert len(executed_scripts) == 0
    
    # Scripts de podcasts ya NO se ejecutan independientemente (están integrados en PodcastProcessor)
    assert "clean_snip.py" not in executed_scripts
    assert "md2html.py" not in executed_scripts
    
    # Scripts de Instapaper tampoco (están integrados)
    assert "scrape.py" not in executed_scripts
    assert "update_titles.py" not in executed_scripts


 