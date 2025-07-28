#!/usr/bin/env python3
"""
Tests para PDFProcessor
"""
import pytest
from pathlib import Path

from pdf_processor import PDFProcessor


def test_pdf_processor_with_pdfs(tmp_path):
    """Test que verifica el procesamiento exitoso de PDFs."""
    
    # Preparar
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Pdfs"
    destination.mkdir()
    
    # Crear archivos PDF de prueba
    pdf1 = incoming / "document1.pdf"
    pdf2 = incoming / "document2.pdf"
    pdf1.write_bytes(b"%PDF-1.4 content")
    pdf2.write_bytes(b"%PDF-1.5 content")
    
    # Crear procesador
    processor = PDFProcessor(incoming, destination)
    
    # Ejecutar
    moved_pdfs = processor.process_pdfs()
    
    # Verificar
    assert len(moved_pdfs) == 2
    assert (destination / "document1.pdf").exists()
    assert (destination / "document2.pdf").exists()
    
    # Verificar que el contenido se mantuvo
    assert (destination / "document1.pdf").read_bytes() == b"%PDF-1.4 content"
    assert (destination / "document2.pdf").read_bytes() == b"%PDF-1.5 content"


def test_pdf_processor_no_pdfs(tmp_path, capsys):
    """Test que verifica el comportamiento cuando no hay PDFs."""
    
    # Preparar directorios vacíos
    incoming = tmp_path / "Incoming" 
    incoming.mkdir()
    destination = tmp_path / "Pdfs"
    destination.mkdir()
    
    # Crear algunos archivos que NO son PDFs
    (incoming / "document.txt").write_text("Not a PDF")
    (incoming / "image.png").write_bytes(b"PNG content")
    
    # Crear procesador
    processor = PDFProcessor(incoming, destination)
    
    # Ejecutar
    moved_pdfs = processor.process_pdfs()
    
    # Verificar
    assert len(moved_pdfs) == 0
    assert len(list(destination.glob("*"))) == 0  # Ningún archivo movido
    
    # Verificar mensaje informativo
    captured = capsys.readouterr()
    assert "📚 No se encontraron PDFs para procesar" in captured.out


def test_pdf_processor_mixed_files(tmp_path):
    """Test que verifica que solo se procesan archivos PDF."""
    
    # Preparar
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Pdfs"
    destination.mkdir()
    
    # Crear mezcla de archivos
    (incoming / "document.pdf").write_bytes(b"%PDF content")
    (incoming / "article.html").write_text("<html>Content</html>")
    (incoming / "notes.md").write_text("# Markdown content")
    (incoming / "image.jpg").write_bytes(b"JPEG content")
    
    # Crear procesador
    processor = PDFProcessor(incoming, destination)
    
    # Ejecutar
    moved_pdfs = processor.process_pdfs()
    
    # Verificar que solo se movió el PDF
    assert len(moved_pdfs) == 1
    assert (destination / "document.pdf").exists()
    
    # Verificar que los otros archivos siguen en incoming
    assert (incoming / "article.html").exists()
    assert (incoming / "notes.md").exists()
    assert (incoming / "image.jpg").exists() 