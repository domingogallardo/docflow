#!/usr/bin/env python3
"""
Tests for PDFProcessor
"""

from pdf_processor import PDFProcessor
from utils import split_front_matter


def test_pdf_processor_with_pdfs(tmp_path):
    """Test that verifies successful PDF processing."""
    
    # Prepare.
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Pdfs"
    destination.mkdir()
    
    # Create test PDF files.
    pdf1 = incoming / "document1.pdf"
    pdf2 = incoming / "document2.pdf"
    pdf1.write_bytes(b"%PDF-1.4 content")
    pdf2.write_bytes(b"%PDF-1.5 content")
    
    # Create processor.
    processor = PDFProcessor(incoming, destination)
    
    # Execute.
    moved_pdfs = processor.process_pdfs()
    
    # Verify.
    assert len(moved_pdfs) == 2
    assert (destination / "document1.pdf").exists()
    assert (destination / "document2.pdf").exists()
    
    # Verify content was preserved.
    assert (destination / "document1.pdf").read_bytes() == b"%PDF-1.4 content"
    assert (destination / "document2.pdf").read_bytes() == b"%PDF-1.5 content"

    md1 = destination / "document1.md"
    md2 = destination / "document2.md"
    assert md1.exists()
    assert md2.exists()
    meta, body = split_front_matter(md1.read_text(encoding="utf-8"))
    assert meta["title"] == "document1"
    assert meta["source"] == "pdf"
    assert meta["docflow_source_type"] == "pdf"
    assert meta["docflow_pdf_path"] == "Pdfs/document1.pdf"
    assert meta["docflow_markdown_path"] == "Pdfs/document1.md"
    assert meta["docflow_render_status"] == "markdown_only"
    assert meta["docflow_ingested_at"].endswith("Z")
    assert "Associated PDF: `document1.pdf`" in body


def test_pdf_processor_no_pdfs(tmp_path, capsys):
    """Test that verifies behavior when there are no PDFs."""
    
    # Prepare empty directories.
    incoming = tmp_path / "Incoming" 
    incoming.mkdir()
    destination = tmp_path / "Pdfs"
    destination.mkdir()
    
    # Create some files that are NOT PDFs.
    (incoming / "document.txt").write_text("Not a PDF")
    (incoming / "image.png").write_bytes(b"PNG content")
    
    # Create processor.
    processor = PDFProcessor(incoming, destination)
    
    # Execute.
    moved_pdfs = processor.process_pdfs()
    
    # Verify.
    assert len(moved_pdfs) == 0
    assert len(list(destination.glob("*"))) == 0  # No files moved.
    
    # Verify informational message.
    captured = capsys.readouterr()
    assert "📚 No PDFs found to process" in captured.out


def test_pdf_processor_mixed_files(tmp_path):
    """Test that verifies only PDF files are processed."""
    
    # Prepare.
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Pdfs"
    destination.mkdir()
    
    # Create a mix of files.
    (incoming / "document.pdf").write_bytes(b"%PDF content")
    (incoming / "article.html").write_text("<html>Content</html>")
    (incoming / "notes.md").write_text("# Markdown content")
    (incoming / "image.jpg").write_bytes(b"JPEG content")
    
    # Create processor.
    processor = PDFProcessor(incoming, destination)
    
    # Execute.
    moved_pdfs = processor.process_pdfs()
    
    # Verify only the PDF was moved.
    assert len(moved_pdfs) == 1
    assert (destination / "document.pdf").exists()
    assert (destination / "document.md").exists()
    
    # Verify the other files remain in incoming.
    assert (incoming / "article.html").exists()
    assert (incoming / "notes.md").exists()
    assert (incoming / "image.jpg").exists() 
