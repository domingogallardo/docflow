#!/usr/bin/env python3
"""
Tests for PDFProcessor
"""
import pytest
from pathlib import Path

from pdf_processor import PDFProcessor


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
    
    # Verify the other files remain in incoming.
    assert (incoming / "article.html").exists()
    assert (incoming / "notes.md").exists()
    assert (incoming / "image.jpg").exists() 


def test_pdf_processor_imports_pdfs_from_source_dir(tmp_path, capsys):
    """PDFs downloaded outside Incoming are imported before processing."""

    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    downloads = tmp_path / "iCloud Downloads"
    downloads.mkdir()
    destination = tmp_path / "Pdfs"
    destination.mkdir()

    downloaded_pdf = downloads / "paper.pdf"
    downloaded_pdf.write_bytes(b"%PDF downloaded")

    processor = PDFProcessor(incoming, destination, source_dirs=(downloads,))
    moved_pdfs = processor.process_pdfs()

    assert len(moved_pdfs) == 1
    assert not downloaded_pdf.exists()
    assert not (incoming / "paper.pdf").exists()
    assert (destination / "paper.pdf").read_bytes() == b"%PDF downloaded"
    captured = capsys.readouterr()
    assert "PDF import audit: scanning" in captured.out
    audit_content = (incoming / "import_audit.log").read_text(encoding="utf-8")
    assert "pdf scanning" in audit_content
    assert "1 PDF candidate(s)" in audit_content
    assert "imported PDF: paper.pdf" in audit_content


def test_pdf_processor_import_uses_unique_name_for_collisions(tmp_path):
    """Imported PDFs keep both files when Incoming already has the same name."""

    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    downloads = tmp_path / "iCloud Downloads"
    downloads.mkdir()
    destination = tmp_path / "Pdfs"
    destination.mkdir()

    (incoming / "paper.pdf").write_bytes(b"%PDF incoming")
    (downloads / "paper.pdf").write_bytes(b"%PDF downloaded")

    processor = PDFProcessor(incoming, destination, source_dirs=(downloads,))
    processor.process_pdfs()

    assert (destination / "paper.pdf").read_bytes() == b"%PDF incoming"
    assert (destination / "paper (1).pdf").read_bytes() == b"%PDF downloaded"


def test_pdf_processor_does_not_import_non_pdf_from_source_dir(tmp_path):
    """Only PDFs are imported from external source folders."""

    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    downloads = tmp_path / "iCloud Downloads"
    downloads.mkdir()
    destination = tmp_path / "Pdfs"
    destination.mkdir()

    note = downloads / "note.md"
    note.write_text("# Not a PDF", encoding="utf-8")

    processor = PDFProcessor(incoming, destination, source_dirs=(downloads,))
    moved_pdfs = processor.process_pdfs()

    assert moved_pdfs == []
    assert note.exists()
    assert list(destination.iterdir()) == []


def test_pdf_processor_audits_icloud_placeholders(tmp_path):
    """PDF placeholders are logged because they are not importable yet."""

    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    downloads = tmp_path / "iCloud Downloads"
    downloads.mkdir()
    destination = tmp_path / "Pdfs"
    destination.mkdir()

    placeholder = downloads / "paper.pdf.icloud"
    placeholder.write_text("placeholder", encoding="utf-8")

    processor = PDFProcessor(incoming, destination, source_dirs=(downloads,))
    moved_pdfs = processor.process_pdfs()

    assert moved_pdfs == []
    assert placeholder.exists()
    audit_content = (incoming / "import_audit.log").read_text(encoding="utf-8")
    assert "0 PDF candidate(s), 1 iCloud placeholder candidate(s)" in audit_content
    assert "placeholder not importable yet: paper.pdf.icloud" in audit_content


def test_pdf_processor_does_not_audit_empty_source_dir(tmp_path, capsys):
    """Empty external source folders do not add audit noise."""

    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    downloads = tmp_path / "iCloud Downloads"
    downloads.mkdir()
    destination = tmp_path / "Pdfs"
    destination.mkdir()

    processor = PDFProcessor(incoming, destination, source_dirs=(downloads,))
    moved_pdfs = processor.process_pdfs()

    assert moved_pdfs == []
    assert not (incoming / "import_audit.log").exists()
    captured = capsys.readouterr()
    assert "PDF import audit" not in captured.out
