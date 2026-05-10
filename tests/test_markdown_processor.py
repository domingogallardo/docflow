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
    podcast_md.write_text(
        """---
source: podcast
---

# Episodio

## Episode metadata
- Episode title: Test
- Show: Demo

## Snips
- Contenido""",
        encoding="utf-8",
    )

    processor = MarkdownProcessor(incoming, destination)
    processor.title_updater.update_titles = lambda files, renamer: None
    moved = processor.process_markdown()

    moved_set = {p.relative_to(tmp_path) for p in moved}
    assert (tmp_path / "Posts" / "Posts 2025" / "nota.md").relative_to(tmp_path) in moved_set
    assert (tmp_path / "Posts" / "Posts 2025" / "nota.html").relative_to(tmp_path) in moved_set

    html_content = (destination / "nota.html").read_text(encoding="utf-8")
    assert "body { margin-left: 6%;" in html_content
    assert "Contenido en <strong>Markdown</strong>." in html_content
    md_content = (destination / "nota.md").read_text(encoding="utf-8")
    assert 'title: "Título"' in md_content
    assert "docflow_source_type: markdown" in md_content
    assert "docflow_html_generated_at:" in md_content
    assert "docflow_word_count:" in md_content
    assert 'name="docflow-html-generated-at"' in html_content

    # Ignored files should remain in Incoming.
    assert podcast_md.exists()


def test_markdown_processor_accepts_external_source_url(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Posts" / "Posts 2025"

    generic_md = incoming / "article.md"
    generic_md.write_text(
        """---
title: External article
source: "https://example.com/article"
---

# External article

Contenido.""",
        encoding="utf-8",
    )

    processor = MarkdownProcessor(incoming, destination)
    processor.title_updater.update_titles = lambda files, renamer: None
    moved = processor.process_markdown()

    moved_names = {p.name for p in moved}
    assert "article.md" in moved_names
    assert "article.html" in moved_names

    html_content = (destination / "article.html").read_text(encoding="utf-8")
    assert "Original link:" in html_content
    assert 'href="https://example.com/article"' in html_content
    assert ">https://example.com/article</a>" in html_content
    md_content = (destination / "article.md").read_text(encoding="utf-8")
    assert "source_url: https://example.com/article" in md_content
    assert "docflow_source_type: web" in md_content


def test_markdown_processor_preserves_remote_images(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Posts" / "Posts 2025"

    generic_md = incoming / "article-with-image.md"
    image_url = "https://content.example.com/images/diagram.png"
    generic_md.write_text(
        f"""---
title: External article
source: "https://example.com/article"
---

# External article

![Diagram]({image_url} "Diagram")
""",
        encoding="utf-8",
    )

    processor = MarkdownProcessor(incoming, destination)
    processor.title_updater.update_titles = lambda files, renamer: None
    processor.process_markdown()

    html_content = (destination / "article-with-image.html").read_text(encoding="utf-8")
    assert f'<img alt="Diagram" src="{image_url}" title="Diagram"/>' in html_content
    assert f'<a class="image-zoom" href="{image_url}"' in html_content


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


def test_markdown_processor_imports_markdown_from_source_dir(tmp_path, capsys):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    downloads = tmp_path / "iCloud Downloads"
    downloads.mkdir()
    destination = tmp_path / "Posts" / "Posts 2025"

    downloaded_md = downloads / "downloaded.md"
    downloaded_md.write_text("# Downloaded\n\nContenido", encoding="utf-8")

    processor = MarkdownProcessor(incoming, destination, source_dirs=(downloads,))
    processor.title_updater.update_titles = lambda files, renamer: None
    moved = processor.process_markdown()

    moved_names = {path.name for path in moved}
    assert "downloaded.md" in moved_names
    assert "downloaded.html" in moved_names
    assert not downloaded_md.exists()
    assert not (incoming / "downloaded.md").exists()
    assert (destination / "downloaded.md").exists()
    assert (destination / "downloaded.html").exists()
    captured = capsys.readouterr()
    assert "Markdown import audit: scanning" in captured.out
    audit_content = (incoming / "import_audit.log").read_text(encoding="utf-8")
    assert "markdown scanning" in audit_content
    assert "1 markdown candidate(s)" in audit_content
    assert "imported Markdown: downloaded.md" in audit_content


def test_markdown_processor_import_uses_unique_name_for_collisions(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    downloads = tmp_path / "iCloud Downloads"
    downloads.mkdir()
    destination = tmp_path / "Posts" / "Posts 2025"

    (incoming / "nota.md").write_text("# Existing\n\nIncoming", encoding="utf-8")
    (downloads / "nota.md").write_text("# Downloaded\n\nDownloads", encoding="utf-8")

    processor = MarkdownProcessor(incoming, destination, source_dirs=(downloads,))
    processor.title_updater.update_titles = lambda files, renamer: None
    processor.process_markdown()

    assert (destination / "nota.md").exists()
    assert (destination / "nota.html").exists()
    assert (destination / "nota (1).md").exists()
    assert (destination / "nota (1).html").exists()


def test_markdown_processor_does_not_import_reserved_source_markdown(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    downloads = tmp_path / "iCloud Downloads"
    downloads.mkdir()
    destination = tmp_path / "Posts" / "Posts 2025"

    podcast_md = downloads / "snipd.md"
    podcast_md.write_text(
        """---
source: podcast
---

# Podcast
""",
        encoding="utf-8",
    )

    processor = MarkdownProcessor(incoming, destination, source_dirs=(downloads,))
    processor.title_updater.update_titles = lambda files, renamer: None
    moved = processor.process_markdown()

    assert moved == []
    assert podcast_md.exists()
    audit_content = (incoming / "import_audit.log").read_text(encoding="utf-8")
    assert "ignored Markdown (podcast): snipd.md" in audit_content


def test_markdown_processor_audits_icloud_placeholders(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    downloads = tmp_path / "iCloud Downloads"
    downloads.mkdir()
    destination = tmp_path / "Posts" / "Posts 2025"

    placeholder = downloads / "article.md.icloud"
    placeholder.write_text("placeholder", encoding="utf-8")

    processor = MarkdownProcessor(incoming, destination, source_dirs=(downloads,))
    processor.title_updater.update_titles = lambda files, renamer: None
    moved = processor.process_markdown()

    assert moved == []
    assert placeholder.exists()
    audit_content = (incoming / "import_audit.log").read_text(encoding="utf-8")
    assert "0 markdown candidate(s), 1 iCloud placeholder candidate(s)" in audit_content
    assert "placeholder not importable yet: article.md.icloud" in audit_content


def test_markdown_processor_does_not_audit_empty_source_dir(tmp_path, capsys):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    downloads = tmp_path / "iCloud Downloads"
    downloads.mkdir()
    destination = tmp_path / "Posts" / "Posts 2025"

    processor = MarkdownProcessor(incoming, destination, source_dirs=(downloads,))
    processor.title_updater.update_titles = lambda files, renamer: None
    moved = processor.process_markdown()

    assert moved == []
    assert not (incoming / "import_audit.log").exists()
    captured = capsys.readouterr()
    assert "Markdown import audit" not in captured.out


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
