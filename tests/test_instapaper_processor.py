#!/usr/bin/env python3
"""
Tests for InstapaperProcessor
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from instapaper_processor import InstapaperDownloadRegistry, InstapaperProcessor


def test_star_prefix_stripping_variants():
    """Remove common star prefixes from the title."""
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

    # Read page with a star in <title> and H1.
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

    # Mock the HTTP session.
    mock_resp = Mock()
    mock_resp.text = read_html
    processor.session = Mock()
    processor.session.get.return_value = mock_resp

    # Download and write the article HTML.
    html_path, is_starred = processor._download_article("12345")
    assert is_starred is True
    html_text = html_path.read_text(encoding="utf-8")

    # It must contain the star marker and attribute in <html>.
    assert '<meta name="instapaper-starred" content="true">' in html_text
    assert 'data-instapaper-starred="true"' in html_text
    # Title must be clean (no star prefix).
    assert "<title>Starred Sample</title>" in html_text
    assert "<h1>Starred Sample</h1>" in html_text

    # Converting to Markdown should add front matter.
    processor._convert_html_to_markdown()
    md_path = html_path.with_suffix('.md')
    md_text = md_path.read_text(encoding="utf-8")
    assert md_text.startswith("---\ninstapaper_starred: true\n---\n")
    # No star should remain at the start of the heading.
    assert not md_text.splitlines()[3].startswith("# ⭐")


def test_instapaper_processor_no_star_no_meta(tmp_path):
    """If the <title> does not start with ⭐, it should not be marked starred."""
    incoming = tmp_path / "Incoming"
    destination = tmp_path / "Posts"
    incoming.mkdir()
    destination.mkdir()

    # Read page WITHOUT a star in <title> or H1.
    read_html = """<!DOCTYPE html>
    <html>
    <head>
      <title>Normal Sample</title>
    </head>
    <body>
      <div id=\"titlebar\">
        <h1>Normal Sample</h1>
        <div class=\"origin_line\">Example.com</div>
      </div>
      <div id=\"story\"><p>Body</p></div>
    </body>
    </html>"""

    processor = InstapaperProcessor(incoming, destination)

    # Mock the HTTP session.
    mock_resp = Mock()
    mock_resp.text = read_html
    processor.session = Mock()
    processor.session.get.return_value = mock_resp

    # Download and write the article HTML.
    html_path, is_starred = processor._download_article("99999")
    assert is_starred is False
    html_text = html_path.read_text(encoding="utf-8")

    # It should not contain starred markers.
    assert '<meta name="instapaper-starred" content="true">' not in html_text
    assert 'data-instapaper-starred="true"' not in html_text

    # Title and H1 should remain unchanged.
    assert "<title>Normal Sample</title>" in html_text
    assert "<h1>Normal Sample</h1>" in html_text

    # Converting to Markdown should not add starred front matter.
    processor._convert_html_to_markdown()
    md_path = html_path.with_suffix('.md')
    md_text = md_path.read_text(encoding="utf-8")
    assert not md_text.startswith("---\ninstapaper_starred: true\n---\n")
    assert "instapaper_starred:" not in md_text


def test_download_registry_persistence(tmp_path):
    registry_path = tmp_path / ".instapaper_downloads.txt"
    registry = InstapaperDownloadRegistry(registry_path)

    assert registry.should_skip("abc", True) is False

    registry.mark_downloaded("abc", True)
    assert registry.should_skip("abc", True) is True
    assert registry.should_skip("abc", False) is False

    # Re-instantiate to verify persistence.
    registry_again = InstapaperDownloadRegistry(registry_path)
    assert registry_again.should_skip("abc", True) is True


def test_download_registry_batch_persists_on_exit(tmp_path):
    """In batch mode, persistence happens on context exit."""
    registry_path = tmp_path / ".instapaper_downloads.txt"
    registry = InstapaperDownloadRegistry(registry_path)

    with registry.batch():
        registry.mark_downloaded("abc", True)
        assert not registry_path.exists()

    assert registry_path.exists()
    assert "abc\t1" in registry_path.read_text(encoding="utf-8")


def test_download_skips_articles_on_registry(tmp_path, monkeypatch):
    incoming = tmp_path / "Incoming"
    destination = tmp_path / "Posts"
    incoming.mkdir()
    destination.mkdir()

    processor = InstapaperProcessor(incoming, destination)
    processor.download_registry.mark_downloaded("123", False)

    with patch('instapaper_processor.INSTAPAPER_USERNAME', 'user'), \
         patch('instapaper_processor.INSTAPAPER_PASSWORD', 'pass'):

        mock_session = Mock()
        mock_login_response = Mock()
        mock_login_response.status_code = 200
        mock_login_response.url = "https://www.instapaper.com/u/1"
        mock_login_response.text = "<html><body><div>ok</div></body></html>"
        mock_session.post.return_value = mock_login_response

        monkeypatch.setattr('instapaper_processor.requests.Session', lambda: mock_session)

        processor._get_article_ids = Mock(return_value=([("123", False)], False))
        processor._download_article = Mock()

        assert processor._download_from_instapaper() is True

    processor._download_article.assert_not_called()


def test_instapaper_processor_with_existing_html(tmp_path):
    """Test that verifies processing existing HTML files (no download)."""
    
    # Prepare.
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Posts"
    destination.mkdir()
    
    # Create a test HTML file.
    html_file = incoming / "test_article.html"
    html_content = """<!DOCTYPE html>
    <html>
    <head><title>Test Article</title></head>
    <body>
        <h1>Test Article</h1>
        <div id="origin">Example.com · 123</div>
        <p>This is a test article with <img src="http://example.com/image.jpg" width="500"> some content.</p>
    </body>
    </html>"""
    html_file.write_text(html_content)
    
    # Create processor with mocks for external APIs.
    processor = InstapaperProcessor(incoming, destination)
    
    processor.title_updater.client = object()
    # Mock download and title generation to avoid external dependencies.
    with patch.object(processor, "_download_from_instapaper", return_value=False), \
         patch.object(processor.title_updater, '_ai_text', side_effect=["inglés", "Amazing Test Article"]):
        moved_posts = processor.process_instapaper_posts()
    
    # Verify.
    assert len(moved_posts) >= 1  # Al menos archivos procesados
    
    # Verify the Markdown file was generated.
    md_files = list(destination.glob("*.md"))
    assert len(md_files) >= 1
    
    # Verify the files were renamed.
    renamed_files = list(destination.glob("Amazing Test Article*"))
    assert len(renamed_files) >= 1


def test_instapaper_processor_skips_non_instapaper_html(tmp_path):
    """Non-Instapaper HTML should not be converted or moved as posts."""
    incoming = tmp_path / "Incoming"
    destination = tmp_path / "Posts"
    incoming.mkdir()
    destination.mkdir()

    html_file = incoming / "tweet_like.html"
    html_file.write_text(
        """<!DOCTYPE html>
        <html>
        <head><title>Tweet - someone-123</title></head>
        <body>
          <h1>Tweet by Someone (@someone)</h1>
          <p><a href="https://x.com/someone/status/123">View on X</a></p>
        </body>
        </html>""",
        encoding="utf-8",
    )

    processor = InstapaperProcessor(incoming, destination)

    processor._convert_html_to_markdown()

    # The tweet-like HTML must not be converted.
    assert not (incoming / "tweet_like.md").exists()

    # Even if a Markdown file exists, it should not be treated as Instapaper.
    md_file = incoming / "tweet_like.md"
    md_file.write_text("# Tweet by Someone (@someone)\n", encoding="utf-8")

    assert processor._list_processed_files() == []


def test_instapaper_processor_no_credentials(tmp_path):
    """Test that verifies behavior when Instapaper credentials are missing."""
    
    # Prepare.
    incoming = tmp_path / "Incoming" 
    incoming.mkdir()
    destination = tmp_path / "Posts"
    
    # Create processor.
    processor = InstapaperProcessor(incoming, destination)
    
    # Mock to simulate missing credentials.
    with patch('instapaper_processor.INSTAPAPER_USERNAME', None), \
         patch('instapaper_processor.INSTAPAPER_PASSWORD', None):
        
        # Execute.
        moved_posts = processor.process_instapaper_posts()
    
    # Verify - should continue without error and return an empty list.
    assert moved_posts == []


def test_instapaper_processor_html_encoding_fix(tmp_path):
    """Test that verifies HTML encoding fixes."""
    
    # Prepare.
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Posts"
    
    # Create an HTML file without charset.
    html_file = incoming / "no_charset.html"
    html_content = """<html>
    <head><title>No Charset</title></head>
    <body>Content without charset</body>
    </html>"""
    html_file.write_text(html_content)
    
    # Create processor.
    processor = InstapaperProcessor(incoming, destination)
    
    # Run only the encoding fix.
    processor._fix_html_encoding()
    
    # Verify the charset was added.
    updated_content = html_file.read_text()
    assert '<meta charset="utf-8">' in updated_content


def test_instapaper_processor_image_width_reduction(tmp_path):
    """Test that verifies image width reduction."""
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Posts"

    html_file = incoming / "big_image.html"
    html_content = """<html>
    <body>
        <img src="http://example.com/big.jpg" width="800" height="600">
        <p>Content</p>
    </body>
    </html>"""
    html_file.write_text(html_content)

    processor = InstapaperProcessor(incoming, destination)

    processor._reduce_images_width()

    updated_content = html_file.read_text()
    assert 'width="300"' in updated_content
    assert 'height="600"' not in updated_content


def test_instapaper_processor_title_generation(tmp_path):
    """Test that verifies AI title generation."""
    
    # Prepare.
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Posts"
    
    # Create a test Markdown file.
    md_file = incoming / "original_title.md"
    md_content = """# Original Title

This is a test article about artificial intelligence and machine learning.
It contains interesting information about the latest developments in the field.
The content is written in English and discusses various technical topics.
"""
    md_file.write_text(md_content)
    (incoming / "original_title.html").write_text("<html><div id='origin'>demo</div></html>", encoding="utf-8")
    
    # Create processor.
    processor = InstapaperProcessor(incoming, destination)
    
    processor.title_updater.client = object()
    # Mock to avoid real OpenAI calls.
    with patch.object(
        processor.title_updater,
        '_ai_text',
        side_effect=["inglés", "AI and Machine Learning - Latest Developments"],
    ):
        processor._update_titles_with_ai()
    
    # Verify the file was renamed.
    renamed_files = list(incoming.glob("AI and Machine Learning - Latest Developments*"))
    assert len(renamed_files) >= 1
    
    # No longer recorded in a control file; only the rename should exist.
    done_file = incoming / "titles_done_instapaper.txt"
    assert not done_file.exists()
