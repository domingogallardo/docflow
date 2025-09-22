#!/usr/bin/env python3
"""
Tests para PodcastProcessor
"""
import pytest
from pathlib import Path

from podcast_processor import PodcastProcessor


def test_podcast_processor_with_podcasts(tmp_path):
    """Test que verifica el procesamiento exitoso de podcasts."""
    
    # Preparar
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Podcasts"
    destination.mkdir()
    
    # Crear archivo de podcast de prueba
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
    
    # Crear procesador
    processor = PodcastProcessor(incoming, destination)
    
    # Ejecutar
    moved_podcasts = processor.process_podcasts()
    
    # Verificar
    assert len(moved_podcasts) >= 1
    
    # Verificar que el archivo fue renombrado usando metadatos
    renamed_files = list(destination.glob("Great Show - Amazing Episode*"))
    assert len(renamed_files) >= 1
    
    # Verificar que se generó el HTML correspondiente
    html_files = list(destination.glob("*.html"))
    assert len(html_files) >= 1


def test_podcast_processor_no_podcasts(tmp_path, capsys):
    """Test que verifica el comportamiento cuando no hay podcasts."""
    
    # Preparar directorios vacíos
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Podcasts"
    
    # Crear algunos archivos que NO son podcasts
    (incoming / "regular_article.md").write_text("# Regular Article\nNot a podcast")
    (incoming / "document.pdf").write_bytes(b"PDF content")
    
    # Crear procesador
    processor = PodcastProcessor(incoming, destination)
    
    # Ejecutar
    moved_podcasts = processor.process_podcasts()
    
    # Verificar
    assert len(moved_podcasts) == 0
    
    # Verificar mensaje informativo
    captured = capsys.readouterr()
    assert "📻 No se encontraron archivos de podcast para procesar" in captured.out


def test_podcast_processor_clean_snipd_features(tmp_path):
    """Test que verifica la limpieza específica de Snipd."""
    
    # Preparar
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Podcasts"
    
    # Crear archivo con elementos específicos de Snipd
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
    
    # Crear procesador
    processor = PodcastProcessor(incoming, destination)
    
    # Ejecutar
    moved_podcasts = processor.process_podcasts()
    
    # Verificar que se procesó el archivo
    assert len(moved_podcasts) >= 1
    
    # Verificar el contenido fue limpiado
    processed_md = None
    for file in moved_podcasts:
        if file.suffix == '.md':
            processed_md = file
            break
    
    assert processed_md is not None
    content = processed_md.read_text()
    
    # Verificar que se eliminaron elementos específicos de Snipd
    assert "---" not in content  # Reglas horizontales eliminadas
    assert "<details>" not in content  # Tags details eliminados
    assert "🎧 [Play snip]" not in content  # Enlaces de audio reemplazados
    assert "🎧 Reproducir fragmento de audio" in content  # Nuevo botón
    assert "br/>" not in content  # Line breaks procesados
    assert "Click to expand" not in content


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
    """Test que verifica la conversión de Markdown a HTML."""
    
    # Preparar
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Podcasts"
    
    # Crear archivo de podcast con Markdown
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
    
    # Crear procesador
    processor = PodcastProcessor(incoming, destination)
    
    # Ejecutar
    moved_podcasts = processor.process_podcasts()
    
    # Verificar que se creó el HTML
    html_files = [f for f in moved_podcasts if f.suffix == '.html']
    assert len(html_files) >= 1
    
    # Verificar el contenido del HTML
    html_content = html_files[0].read_text()
    assert "<!DOCTYPE html>" in html_content
    assert "<meta charset=\"UTF-8\">" in html_content
    assert "<strong>Bold text</strong>" in html_content
    assert "<em>italic text</em>" in html_content
    assert "<code>Code snippet</code>" in html_content
    assert "<ol>" in html_content  # Lista ordenada
    assert "<a href=\"https://example.com\">" in html_content


def test_podcast_processor_mixed_files(tmp_path):
    """Test que verifica que solo se procesan archivos de podcast."""
    
    # Preparar
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Podcasts"
    
    # Crear mezcla de archivos
    # Archivo de podcast válido
    podcast_file = incoming / "valid_podcast.md"
    podcast_content = """# Valid Podcast

## Episode metadata
- Episode title: Valid Episode
- Show: Valid Show

## Snips
- Valid content
"""
    podcast_file.write_text(podcast_content)
    
    # Archivo que NO es podcast
    regular_file = incoming / "regular.md"
    regular_file.write_text("# Regular Article\nJust regular content without podcast metadata")
    
    # Otros archivos
    (incoming / "document.pdf").write_bytes(b"PDF content")
    (incoming / "image.jpg").write_bytes(b"JPEG content")
    
    # Crear procesador
    processor = PodcastProcessor(incoming, destination)
    
    # Ejecutar
    moved_podcasts = processor.process_podcasts()
    
    # Verificar que solo se procesó el archivo de podcast
    assert len(moved_podcasts) >= 1
    
    # Verificar que el archivo de podcast fue renombrado
    podcast_names = [f.name for f in moved_podcasts]
    assert any("Valid Show - Valid Episode" in name for name in podcast_names)


def test_podcast_processor_splits_multi_episode_file(tmp_path):
    """Debe dividir un .md con varios episodios (H1) y procesarlos por separado."""
    import re

    # Preparar
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
    moved = processor.process_podcasts()

    # El archivo original debe desaparecer tras el split
    assert not multi.exists()

    # Deben existir al menos 2 MD y 2 HTML en destino
    md_files = list(destination.glob("*.md"))
    html_files = list(destination.glob("*.html"))
    assert len(md_files) >= 2
    assert len(html_files) >= 2

    # Comprobar nombres esperados (sanitizados como en utils.extract_episode_title)
    def sanitize(filename: str) -> str:
        s = re.sub(r'[<>:\"/\\|?*#]', '', filename)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    expected1 = sanitize("Upgrade - 579: The 2025 September Event Draft")
    expected2 = sanitize("The Last Theory - Black holes in the hypergraph with Stephen Wolfram")

    md_stems = {p.stem for p in md_files}
    assert any(stem == expected1 or stem.startswith(expected1 + " (") for stem in md_stems)
    assert any(stem == expected2 or stem.startswith(expected2 + " (") for stem in md_stems)
