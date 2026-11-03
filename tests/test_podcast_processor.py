#!/usr/bin/env python3
"""
Tests for PodcastProcessor
"""

from podcast_processor import PodcastProcessor
import utils as U


def test_podcast_processor_with_podcasts(tmp_path):
    """Test that verifies successful podcast processing."""
    
    # Prepare.
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Podcasts"
    destination.mkdir()
    
    # Create a test podcast file.
    podcast_file = incoming / "test_podcast.md" 
    podcast_content = """# Test Podcast

## Episode metadata
- Episode title: Amazing Episode
- Show: Great Show
- Owner / Host: Host Name

## Snips
- This is a great content with some <details><summary>Click to expand</summary>More details</details>
- Another snippet with 🎧 [Play snip](https://share.snipd.com/snip/test123)
"""
    podcast_file.write_text(podcast_content)
    
    # Create processor.
    processor = PodcastProcessor(incoming, destination)
    
    # Execute.
    moved_podcasts = processor.process_podcasts()
    
    # Verify.
    assert len(moved_podcasts) >= 1
    
    # Verify the file was renamed using metadata.
    renamed_files = list(destination.glob("Great Show - Amazing Episode*"))
    assert len(renamed_files) >= 1
    
    # Verify the corresponding HTML was generated.
    html_files = list(destination.glob("*.html"))
    assert len(html_files) >= 1


def test_podcast_processor_no_podcasts(tmp_path, capsys):
    """Test that verifies behavior when there are no podcasts."""
    
    # Prepare empty directories.
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Podcasts"
    
    # Create some files that are NOT podcasts.
    (incoming / "regular_article.md").write_text("# Regular Article\nNot a podcast")
    (incoming / "document.pdf").write_bytes(b"PDF content")
    
    # Create processor.
    processor = PodcastProcessor(incoming, destination)
    
    # Execute.
    moved_podcasts = processor.process_podcasts()
    
    # Verify.
    assert len(moved_podcasts) == 0
    
    # Verify informational message.
    captured = capsys.readouterr()
    assert "📻 No podcast files found to process" in captured.out


def test_podcast_processor_clean_snipd_features(tmp_path):
    """Test that verifies Snipd-specific cleaning."""
    
    # Prepare.
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Podcasts"
    
    # Create a file with Snipd-specific elements.
    podcast_file = incoming / "snipd_test.md"
    podcast_content = """# Snipd Test

## Episode metadata
- Episode title: Test Episode
- Show: Test Show

## Snips
- Content with horizontal rule below:
---
- Content with details: <details><summary>Click to expand</summary>Hidden content</details>
- Audio link: 🎧 [Play snip](https://share.snipd.com/snip/abc123)
- Line breaks: Content<br/>with<br/>> quoted text
"""
    podcast_file.write_text(podcast_content)
    
    # Create processor.
    processor = PodcastProcessor(incoming, destination)
    
    # Execute.
    moved_podcasts = processor.process_podcasts()
    
    # Verify the file was processed.
    assert len(moved_podcasts) >= 1
    
    # Verify the content was cleaned.
    processed_md = None
    for file in moved_podcasts:
        if file.suffix == '.md':
            processed_md = file
            break
    
    assert processed_md is not None
    content = processed_md.read_text()
    front_matter, body = U.split_front_matter(content)

    # Verify Snipd-specific elements were removed.
    assert front_matter.get("source") == "podcast"
    assert "\n---\n" not in body  # Horizontal rules removed
    assert "<details>" not in body  # <details> tags removed
    assert "🎧 [Play snip]" not in body  # Audio links replaced
    assert "🎧 Play audio clip" in body  # New button
    assert "br/>" not in body  # Line breaks processed
    assert "Click to expand" not in body


def test_podcast_processor_show_notes_promoted(tmp_path):
    """Los bloques de show notes se elevan a títulos H2 y mantienen metadatos."""

    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Podcasts"

    md = incoming / "show_notes.md"
    md.write_text(
        """# Podcast

## Episode metadata
- Episode title: Human ChatGPT: putting Tyler Cowen to the test
- Show: Money Talks
- Owner / Host: The Economist
- Episode link: [open in Snipd](https://example.com/episode)
- Episode publish date: 2025-09-11
<details>
<summary>Show notes</summary>
> Line 1<br/>> Line 2
</details>

- Show notes link: [open website](https://example.com/notes)
- Export date: 2025-09-22T12:42

## Snips
- Snip content
""",
        encoding="utf-8",
    )

    processor = PodcastProcessor(incoming, destination)
    moved = processor.process_podcasts()

    processed_md = next(p for p in moved if p.suffix == ".md")
    content = processed_md.read_text(encoding="utf-8")

    assert "<details>" not in content
    assert "## Show notes" in content
    assert "- Show notes link" in content
    assert "> Line 1" in content and "> Line 2" in content

def test_podcast_processor_markdown_to_html_conversion(tmp_path):
    """Test that verifies Markdown to HTML conversion."""
    
    # Prepare.
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Podcasts"
    
    # Create a podcast file with Markdown.
    podcast_file = incoming / "markdown_test.md"
    podcast_content = """# Markdown Test

## Episode metadata
- Episode title: HTML Test
- Show: Conversion Show

## Snips
- **Bold text** and *italic text*
- `Code snippet` in the content
- [Link](https://example.com) to external site

### Subheading
1. First item
2. Second item
"""
    podcast_file.write_text(podcast_content)
    
    # Create processor.
    processor = PodcastProcessor(incoming, destination)
    processor.summary_updater.add_summary_to_markdown = lambda text: U.upsert_front_matter(
        text,
        {"docflow_summary": "Resumen del episodio."},
    )
    
    # Execute.
    moved_podcasts = processor.process_podcasts()
    
    # Verify the HTML was created.
    html_files = [f for f in moved_podcasts if f.suffix == '.html']
    assert len(html_files) >= 1
    
    # Verify the HTML content.
    html_content = html_files[0].read_text()
    assert "<!DOCTYPE html>" in html_content
    assert 'charset="utf-8"' in html_content.lower()
    assert 'name="docflow-source"' in html_content
    assert 'name="docflow-id"' in html_content
    assert 'name="docflow-markdown-path"' in html_content
    assert 'name="docflow-html-path"' in html_content
    assert 'name="docflow-html-generated-at"' in html_content
    assert "<strong>Bold text</strong>" in html_content
    assert "<em>italic text</em>" in html_content
    assert "<code>Code snippet</code>" in html_content
    assert "<ol>" in html_content  # Ordered list
    assert "<a href=\"https://example.com\">" in html_content
    md_files = [f for f in moved_podcasts if f.suffix == ".md"]
    md_content = md_files[0].read_text(encoding="utf-8")
    assert "docflow_id:" in md_content
    assert "docflow_markdown_path:" in md_content
    assert "docflow_html_path:" in md_content
    assert "docflow_html_generated_at:" in md_content
    assert "docflow_summary: Resumen del episodio." in md_content
    assert 'name="docflow-summary"' in html_content
    assert 'content="Resumen del episodio."' in html_content


def test_podcast_processor_mixed_files(tmp_path):
    """Test that verifies only podcast files are processed."""
    
    # Prepare.
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Podcasts"
    
    # Create a mix of files.
    # Valid podcast file.
    podcast_file = incoming / "valid_podcast.md"
    podcast_content = """# Valid Podcast

## Episode metadata
- Episode title: Valid Episode
- Show: Valid Show

## Snips
- Valid content
"""
    podcast_file.write_text(podcast_content)
    
    # File that is NOT a podcast.
    regular_file = incoming / "regular.md"
    regular_file.write_text("# Regular Article\nJust regular content without podcast metadata")
    
    # Other files.
    (incoming / "document.pdf").write_bytes(b"PDF content")
    (incoming / "image.jpg").write_bytes(b"JPEG content")
    
    # Create processor.
    processor = PodcastProcessor(incoming, destination)
    
    # Execute.
    moved_podcasts = processor.process_podcasts()
    
    # Verify only the podcast file was processed.
    assert len(moved_podcasts) >= 1
    
    # Verify the podcast file was renamed.
    podcast_names = [f.name for f in moved_podcasts]
    assert any("Valid Show - Valid Episode" in name for name in podcast_names)


def test_podcast_processor_splits_multi_episode_file(tmp_path):
    """Should split a .md with multiple episodes (H1) and process separately."""
    import re

    # Prepare.
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Podcasts"

    multi = incoming / "multi_podcast.md"
    multi.write_text(
        """# 579: The 2025 September Event Draft

<img src=\"https://example.com/cover1.png\" width=\"200\" alt=\"Cover\" />

## Episode metadata
- Episode title: 579: The 2025 September Event Draft
- Show: Upgrade
- Owner / Host: Relay
- Episode link: [open in Snipd](https://share.snipd.com/episode/aaaa)
- Episode publish date: 2025-09-01

## Snips
- A snippet 1

---

# Black holes in the hypergraph with Stephen Wolfram

<img src=\"https://example.com/cover2.png\" width=\"200\" alt=\"Cover\" />

## Episode metadata
- Episode title: Black holes in the hypergraph with Stephen Wolfram
- Show: The Last Theory
- Owner / Host: Kootenay Village Ventures Inc.
- Episode link: [open in Snipd](https://share.snipd.com/episode/bbbb)
- Episode publish date: 2025-08-29

## Snips
- A snippet 2
""",
        encoding="utf-8",
    )

    processor = PodcastProcessor(incoming, destination)
    processor.process_podcasts()

    # The original file should disappear after the split.
    assert not multi.exists()

    # At least 2 MD and 2 HTML should exist in the destination.
    md_files = list(destination.glob("*.md"))
    html_files = list(destination.glob("*.html"))
    assert len(md_files) >= 2
    assert len(html_files) >= 2

    # Check expected names (sanitized as in utils.extract_episode_title).
    def sanitize(filename: str) -> str:
        s = re.sub(r'[<>:\"/\\|?*#]', '', filename)
        return re.sub(r"\s+", " ", s).strip()

    expected1 = sanitize("Upgrade - 579: The 2025 September Event Draft")
    expected2 = sanitize("The Last Theory - Black holes in the hypergraph with Stephen Wolfram")

    md_stems = {p.stem for p in md_files}
    assert any(stem == expected1 or stem.startswith(expected1 + " (") for stem in md_stems)
    assert any(stem == expected2 or stem.startswith(expected2 + " (") for stem in md_stems)


def test_podcast_processor_builds_snip_index(tmp_path):
    """Should add an index linking to each snip and anchors in titles."""

    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Podcasts"
    processor = PodcastProcessor(incoming, destination)

    md = incoming / "snip_index.md"
    md.write_text(
        """# Snip Index Episode

## Episode metadata
- Episode title: Snip Index Episode
- Show: Index Show

## Snips

### [00:01] Primer snip
- Punto destacado

### [10:00] Segundo snip
- Otro punto
""",
        encoding="utf-8",
    )

    moved = processor.process_podcasts()

    processed_md = next(p for p in moved if p.suffix == ".md")
    md_content = processed_md.read_text(encoding="utf-8")

    assert "<!-- snip-index -->" in md_content
    assert "- [[00:01] Primer snip](#snip-01-00-01-primer-snip)" in md_content
    assert "- [[10:00] Segundo snip](#snip-02-10-00-segundo-snip)" in md_content
    assert "### [00:01] Primer snip {#snip-01-00-01-primer-snip}" in md_content
    assert "### [10:00] Segundo snip {#snip-02-10-00-segundo-snip}" in md_content

    processed_html = next(p for p in moved if p.suffix == ".html")
    html_content = processed_html.read_text(encoding="utf-8")
    assert 'id="snip-01-00-01-primer-snip"' in html_content
    assert 'href="#snip-02-10-00-segundo-snip"' in html_content


def _snip_case_processor(tmp_path, response):
    from types import SimpleNamespace

    processor = PodcastProcessor(tmp_path, tmp_path)
    processor.snip_title_ai.client = object()
    calls = []

    def ai_text(**kwargs):
        calls.append(kwargs)
        return response

    processor.snip_title_ai = SimpleNamespace(client=object(), _ai_text=ai_text)
    return processor, calls


def test_snip_sentence_case_preserves_links_names_and_acronyms(tmp_path, monkeypatch):
    import json

    titles = ['[19:43] La IA Cambiará La Literatura', '[20:40] Apple Y Stephen Wolfram']
    normalized = ['[19:43] La IA cambiará la literatura', '[20:40] Apple y Stephen Wolfram']
    processor, calls = _snip_case_processor(tmp_path, json.dumps(normalized))
    original = '# Episode\n\n## Snips\n\n' + '\n\n'.join('### ' + t for t in titles)
    indexed = processor._add_snip_index(original)
    updated = processor._sentence_case_snip_titles(indexed)
    assert '- [[19:43] La IA cambiará la literatura](#snip-01-19-43-la-ia-cambiara-la-literatura)' in updated
    assert '### [20:40] Apple y Stephen Wolfram {#snip-02-20-40-apple-y-stephen-wolfram}' in updated
    assert processor._sentence_case_snip_titles(updated) == updated
    assert len(calls) == 1


def test_snip_sentence_case_rejects_rewriting_and_lowercased_acronyms(tmp_path, monkeypatch):
    import json

    original = '# Episode\n\n## Snips\n\n### [00:01] La IA Cambia Todo\n'
    for response in (['[00:01] La IA transforma todo'], ['[00:01] La ia cambia todo'],
                     [], ['[00:01] La IA cambia todo!']):
        processor, _ = _snip_case_processor(tmp_path, json.dumps(response))
        assert processor._sentence_case_snip_titles(original) == original


def test_snip_sentence_case_failure_and_no_client_keep_original(tmp_path, monkeypatch):
    original = '# Episode\n\n## Snips\n\n### [00:01] Primer Snip\n'
    processor, calls = _snip_case_processor(tmp_path, 'not JSON')
    assert processor._sentence_case_snip_titles(original) == original
    processor.snip_title_ai.client = None
    assert processor._sentence_case_snip_titles(original) == original
    assert len(calls) == 1


def test_snip_sentence_case_before_index_leaves_other_sections_unchanged(tmp_path, monkeypatch):
    processor, _ = _snip_case_processor(tmp_path, '["[00:01] Primer snip"]')
    original = ('# Episode\n\n## Snips\n\n### [00:01] Primer Snip\n\n'
                'Some Body Text.\n\n## Notes\n\n### Other Title\n')
    updated = processor._add_snip_index(processor._sentence_case_snip_titles(original))
    assert '- [[00:01] Primer snip](#snip-01-00-01-primer-snip)' in updated
    assert 'Some Body Text.\n\n## Notes\n\n### Other Title\n' in updated
