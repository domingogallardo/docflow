#!/usr/bin/env python3
"""
Tests for DocumentProcessor
"""
from pipeline_manager import DocumentProcessor


def test_document_processor_integration(tmp_path):
    """Full integration test of the pipeline using temporary directories."""
    
    # 1. Prepare directory structure.
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    
    # 2. Create test files.
    # Test PDF.
    pdf_file = incoming / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 test content")
    
    # Snipd podcast file.
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
    
    # Regular post HTML (simulating Instapaper).
    html_file = incoming / "test_post.html"
    html_file.write_text(
        "<html><head><meta name=\"docflow-source\" content=\"instapaper\">"
        "<title>Test Post</title></head><body>Content</body></html>",
        encoding="utf-8",
    )

    # Generic Markdown.
    generic_md = incoming / "nota.md"
    generic_md.write_text("# Nota\n\nContenido", encoding="utf-8")

    # Test image.
    image_file = incoming / "sample.png"
    image_file.write_bytes(b"\x89PNG\r\n\x1a\n")
    
    # 4. Create and run processor.
    processor = DocumentProcessor(tmp_path, 2025)
    # Avoid Playwright/X calls in tests.
    processor.process_tweet_urls = lambda: []
    processor.markdown_processor.title_updater.update_titles = lambda files, renamer: None
    success = processor.process_all()
    
    # 6. Verify the pipeline ran successfully.
    assert success is True
    
    # 7. Verify files were moved correctly.
    assert (tmp_path / "Podcasts" / "Podcasts 2025" / "Test Show - Test Episode.md").exists()
    assert (tmp_path / "Posts" / "Posts 2025").exists()
    assert (tmp_path / "Pdfs" / "Pdfs 2025" / "test.pdf").exists()
    images_dir = tmp_path / "Images" / "Images 2025"
    assert (images_dir / "sample.png").exists()
    gallery_file = images_dir / "gallery.html"
    assert gallery_file.exists()
    assert "sample.png" in gallery_file.read_text(encoding="utf-8")
    posts_dir = tmp_path / "Posts" / "Posts 2025"
    assert (posts_dir / "nota.md").exists()
    assert (posts_dir / "nota.html").exists()


def test_process_podcasts_only(tmp_path):
    """Specific test for podcast processing."""
    
    # Prepare.
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
    
    processor = DocumentProcessor(tmp_path, 2025)
    
    # Run only the podcasts phase.
    moved_podcasts = processor.process_podcasts()
    
    # Verify - may be 1 or 2 files depending on HTML generation.
    assert len(moved_podcasts) >= 1  # At least the .md
    assert (tmp_path / "Podcasts" / "Podcasts 2025" / "Great Show - Amazing Episode.md").exists()
    
    # External scripts are not run (integrated in processors): no runner validation.
