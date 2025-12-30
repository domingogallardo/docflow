#!/usr/bin/env python3
"""Tests for MarkdownProcessor."""
from pathlib import Path

from markdown_processor import MarkdownProcessor


def test_markdown_processor_converts_and_moves_files(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Posts" / "Posts 2025"

    generic_md = incoming / "nota.md"
    generic_md.write_text("# Título\n\nContenido en **Markdown**.", encoding="utf-8")

    # Files that should be ignored by specific pipelines.
    podcast_md = incoming / "snipd_ep.md"
    podcast_md.write_text("""# Episodio\n\n## Episode metadata\n- Episode title: Test\n- Show: Demo\n\n## Snips\n- Contenido""", encoding="utf-8")

    processor = MarkdownProcessor(incoming, destination)
    processor.title_updater.update_titles = lambda files, renamer: None
    moved = processor.process_markdown()

    moved_set = {p.relative_to(tmp_path) for p in moved}
    assert (tmp_path / "Posts" / "Posts 2025" / "nota.md").relative_to(tmp_path) in moved_set
    assert (tmp_path / "Posts" / "Posts 2025" / "nota.html").relative_to(tmp_path) in moved_set

    html_content = (destination / "nota.html").read_text(encoding="utf-8")
    assert "body { margin-left: 6%;" in html_content
    assert "Contenido en <strong>Markdown</strong>." in html_content

    # Ignored files should remain in Incoming.
    assert podcast_md.exists()


def test_markdown_processor_moves_existing_html(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Posts" / "Posts 2025"

    generic_md = incoming / "nota.md"
    generic_md.write_text("# Nota existente", encoding="utf-8")
    existing_html = incoming / "nota.html"
    existing_html.write_text("<html><body>Previo</body></html>", encoding="utf-8")

    processor = MarkdownProcessor(incoming, destination)
    processor.title_updater.update_titles = lambda files, renamer: None
    moved = processor.process_markdown()

    assert len(moved) == 2
    assert not existing_html.exists()
    assert (destination / "nota.html").exists()


def test_markdown_processor_applies_ai_titles(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Posts" / "Posts 2025"

    md_file = incoming / "nota.md"
    md_file.write_text("Contenido", encoding="utf-8")
    (incoming / "nota.html").write_text("<html><body>Contenido</body></html>", encoding="utf-8")

    processor = MarkdownProcessor(incoming, destination)

    def fake_update(files, renamer):
        for path in files:
            renamer(path, "Nuevo título AI")

    processor.title_updater.update_titles = fake_update
    moved = processor.process_markdown()

    moved_names = {p.name for p in moved}
    assert "Nuevo título AI.md" in moved_names
    assert "Nuevo título AI.html" in moved_names
