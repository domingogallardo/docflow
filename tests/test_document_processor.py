import sys
from pathlib import Path
import pytest
from unittest.mock import Mock

sys.path.append(str(Path(__file__).parent.parent))
from document_processor import DocumentProcessor, DocumentProcessorConfig


class MockScriptRunner:
    """Mock del ScriptRunner para tests."""
    
    def __init__(self):
        self.executed_scripts = []
    
    def run_script(self, script_name: str, *args) -> bool:
        self.executed_scripts.append((script_name, args))
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
    
    # 7. Verificar que se ejecutaron los scripts correctros
    executed_scripts = [script[0] for script in mock_runner.executed_scripts]
    
    # Scripts de podcasts
    assert "clean_snip.py" in executed_scripts
    assert "md2html.py" in executed_scripts
    
    # Scripts del pipeline regular
    assert "scrape.py" in executed_scripts
    assert "html2md.py" in executed_scripts
    assert "update_titles.py" in executed_scripts
    
    # 8. Verificar estructura de directorios creada
    assert (tmp_path / "Podcasts" / "Podcasts 2025").exists()
    assert (tmp_path / "Posts" / "Posts 2025").exists()
    assert (tmp_path / "Pdfs" / "Pdfs 2025").exists()
    
    # 9. Verificar que los archivos se movieron correctamente
    # El PDF debe mantener su nombre original
    assert (tmp_path / "Pdfs" / "Pdfs 2025" / "test.pdf").exists()
    
    # El podcast debe haberse renombrado usando metadatos
    podcast_files = list((tmp_path / "Podcasts" / "Podcasts 2025").glob("*.md"))
    assert len(podcast_files) > 0
    # Debería contener "Test Show - Test Episode" en el nombre
    assert any("Test Show - Test Episode" in f.name for f in podcast_files)


def test_process_podcasts_only(tmp_path):
    """Test específico para el procesamiento de podcasts."""
    
    # Preparar
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    
    podcast_file = incoming / "test_podcast.md"
    podcast_content = """# My Podcast

## Episode metadata  
- Episode title: Amazing Episode
- Show: Cool Podcast

## Snips
- Content here
"""
    podcast_file.write_text(podcast_content, encoding="utf-8")
    
    config = DocumentProcessorConfig(base_dir=tmp_path, year=2025)
    mock_runner = MockScriptRunner()
    processor = DocumentProcessor(config, script_runner=mock_runner)
    
    # Ejecutar solo fase de podcasts
    moved_podcasts = processor.process_podcasts()
    
    # Verificar
    assert len(moved_podcasts) > 0
    assert (tmp_path / "Podcasts" / "Podcasts 2025").exists()
    
    # Verificar que se ejecutaron solo scripts de podcasts
    executed_scripts = [script[0] for script in mock_runner.executed_scripts]
    assert "clean_snip.py" in executed_scripts
    assert "md2html.py" in executed_scripts
    assert "scrape.py" not in executed_scripts  # No debe ejecutar pipeline regular


def test_process_regular_documents_only(tmp_path):
    """Test específico para el procesamiento de documentos regulares."""
    
    # Preparar
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    
    pdf_file = incoming / "regular.pdf"
    pdf_file.write_bytes(b"%PDF content")
    
    config = DocumentProcessorConfig(base_dir=tmp_path, year=2025)
    mock_runner = MockScriptRunner()
    processor = DocumentProcessor(config, script_runner=mock_runner)
    
    # Ejecutar solo fase regular
    moved_posts, moved_pdfs = processor.process_regular_documents()
    
    # Verificar
    assert len(moved_pdfs) == 1
    assert (tmp_path / "Pdfs" / "Pdfs 2025" / "regular.pdf").exists()
    
    # Verificar scripts ejecutados
    executed_scripts = [script[0] for script in mock_runner.executed_scripts]
    assert "scrape.py" in executed_scripts
    assert "update_titles.py" in executed_scripts
    assert "clean_snip.py" not in executed_scripts  # No debe ejecutar pipeline de podcasts 