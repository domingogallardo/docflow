#!/usr/bin/env python3
"""Tests for MarkdownProcessor."""

import time

from markdown_processor import MarkdownProcessor
import utils as U


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
    assert "docflow_id:" in md_content
    assert "docflow_markdown_path:" in md_content
    assert "docflow_html_path:" in md_content
    assert "docflow_source_type: markdown" in md_content
    assert "docflow_html_generated_at:" in md_content
    assert "docflow_word_count:" in md_content
    assert 'name="docflow-id"' in html_content
    assert 'name="docflow-markdown-path"' in html_content
    assert 'name="docflow-html-path"' in html_content
    assert 'name="docflow-html-generated-at"' in html_content

    # Ignored files should remain in Incoming.
    assert podcast_md.exists()


def test_markdown_processor_adds_docflow_summary_before_html(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Posts" / "Posts 2025"

    generic_md = incoming / "nota.md"
    generic_md.write_text("# Título\n\nContenido en Markdown.", encoding="utf-8")

    processor = MarkdownProcessor(incoming, destination)
    processor.title_updater.update_titles = lambda files, renamer: None

    def fake_summary(path):
        text = path.read_text(encoding="utf-8")
        path.write_text(U.upsert_front_matter(text, {"docflow_summary": "Resumen breve."}), encoding="utf-8")
        return True

    processor.summary_updater.add_summary_to_file = fake_summary
    processor.process_markdown()

    md_content = (destination / "nota.md").read_text(encoding="utf-8")
    html_content = (destination / "nota.html").read_text(encoding="utf-8")
    assert "docflow_summary: Resumen breve." in md_content
    assert 'name="docflow-summary"' in html_content
    assert 'content="Resumen breve."' in html_content


def test_markdown_processor_skips_docflow_summary_for_tweets(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Tweets" / "Tweets 2025"

    tweet_md = incoming / "tweet.md"
    tweet_md.write_text("---\nsource: tweet\n---\n\n# Tweet\n\nTexto.", encoding="utf-8")

    processor = MarkdownProcessor(incoming, destination)
    processor.title_updater.update_titles = lambda files, renamer: None

    calls = []
    processor.summary_updater.add_summary_to_file = lambda path: calls.append(path) or True
    processor.process_tweet_markdown_subset([tweet_md])

    md_content = (destination / "tweet.md").read_text(encoding="utf-8")
    assert "docflow_summary:" not in md_content
    assert calls == []


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
    assert "docflow_post_url: https://example.com/article" in md_content
    assert 'name="docflow-post-url"' in html_content


def test_markdown_processor_removes_imported_description_and_tags(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    destination = tmp_path / "Posts" / "Posts 2025"

    generic_md = incoming / "article.md"
    generic_md.write_text(
        """---
title: External article
description: "Imported summary"
tags:
  - "clippings"
source: "https://example.com/article"
---

# External article

Contenido.
""",
        encoding="utf-8",
    )

    processor = MarkdownProcessor(incoming, destination)
    processor.title_updater.update_titles = lambda files, renamer: None
    processor.process_markdown()

    md_content = (destination / "article.md").read_text(encoding="utf-8")
    assert "description:" not in md_content
    assert "\ntags:\n" not in md_content
    assert "clippings" not in md_content
    assert "source_url: https://example.com/article" in md_content


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


def test_markdown_processor_routes_full_snipd_transcripts_to_podcasts(
    tmp_path,
    monkeypatch,
):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    posts_destination = tmp_path / "Posts" / "Posts 2026"
    podcasts_destination = tmp_path / "Podcasts" / "Podcasts 2026"
    monkeypatch.setattr("markdown_processor.cfg.BASE_DIR", tmp_path)

    examples = [
        (
            "podcast 1.md",
            "Earth is getting dimmer and hotter",
            "Babbage from The Economist (subscriber edition)",
            "2026-07-22",
            "76516dfe-7da5-473b-a11d-629f97f48953",
        ),
        (
            "podcast 2.md",
            "Is Life Just Different?",
            "The Quanta Podcast",
            "2026-07-21",
            "6d28b3d1-5035-4618-aff9-4493efb3d6ad",
        ),
    ]
    for filename, episode_title, show, publish_date, episode_id in examples:
        (incoming / filename).write_text(
            f"""# {episode_title}

## Episode metadata
- Show: {show}
- Episode link: https://share.snipd.com/episode/{episode_id}
- Publish date: {publish_date}

## Transcript
**Host** [00:00:01]
Full episode transcript.
""",
            encoding="utf-8",
        )

    processor = MarkdownProcessor(
        incoming,
        posts_destination,
        podcast_destination_dir=podcasts_destination,
    )
    processor.summary_updater.add_summary_to_file = lambda path: False
    processor.title_updater.update_titles = lambda files, renamer: (_ for _ in ()).throw(
        AssertionError("AI titles must not be applied to Snipd transcripts")
    )

    processing_started_at = time.time()
    moved = processor.process_markdown()
    processing_finished_at = time.time()

    assert len(moved) == 4
    assert not posts_destination.exists()

    for _, episode_title, show, publish_date, _ in examples:
        safe_episode_title = episode_title.replace("?", "")
        canonical_title = f"{show} - {safe_episode_title} - Transcripción"
        md_path = podcasts_destination / f"{canonical_title}.md"
        html_path = podcasts_destination / f"{canonical_title}.html"
        assert md_path.exists()
        assert html_path.exists()

        md_content = md_path.read_text(encoding="utf-8")
        meta, _ = U.split_front_matter(md_content)
        assert meta["source"] == "podcast"
        assert meta["title"] == canonical_title
        assert meta["docflow_source_type"] == "podcast"
        assert meta["podcast_show"] == show
        assert meta["podcast_episode_title"] == episode_title
        assert meta["podcast_publish_date"] == publish_date
        assert meta["podcast_content_type"] == "transcript"
        assert meta["docflow_markdown_path"] == (
            f"Podcasts/Podcasts 2026/{canonical_title}.md"
        )
        assert meta["docflow_html_path"] == (
            f"Podcasts/Podcasts 2026/{canonical_title}.html"
        )

        html_content = html_path.read_text(encoding="utf-8")
        assert f'content="{canonical_title}" name="docflow-title"' in html_content
        assert 'content="podcast" name="docflow-source-type"' in html_content
        assert processing_started_at <= md_path.stat().st_mtime <= processing_finished_at
        assert processing_started_at <= html_path.stat().st_mtime <= processing_finished_at


def test_markdown_processor_does_not_route_ambiguous_transcript_to_podcasts(
    tmp_path,
):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    posts_destination = tmp_path / "Posts" / "Posts 2026"
    podcasts_destination = tmp_path / "Podcasts" / "Podcasts 2026"

    ambiguous = incoming / "transcript.md"
    ambiguous.write_text(
        """# Interview notes

## Episode metadata
- Show: Demo
- Publish date: 2026-07-22

## Transcript
This document has no Snipd episode link.
""",
        encoding="utf-8",
    )

    processor = MarkdownProcessor(
        incoming,
        posts_destination,
        podcast_destination_dir=podcasts_destination,
    )
    processor.summary_updater.add_summary_to_file = lambda path: False
    processor.title_updater.update_titles = lambda files, renamer: None
    processor.process_markdown()

    assert (posts_destination / "transcript.md").exists()
    assert not podcasts_destination.exists()
