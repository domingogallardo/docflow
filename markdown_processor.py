#!/usr/bin/env python3
"""MarkdownProcessor - Convierte Markdown genérico a HTML y lo archiva junto a Instapaper."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

import anthropic

import config as cfg
import utils as U
from title_ai import TitleAIUpdater, rename_markdown_pair


class MarkdownProcessor:
    """Procesa archivos Markdown ubicados en Incoming/ que no pertenecen a otros pipelines."""

    def __init__(self, incoming_dir: Path, destination_dir: Path):
        self.incoming_dir = incoming_dir
        self.destination_dir = destination_dir
        self.title_updater = TitleAIUpdater(
            anthropic.Anthropic(api_key=cfg.ANTHROPIC_KEY),
            incoming_dir / "titles_done_markdown.txt",
        )

    def process_markdown(self) -> List[Path]:
        """Convierte Markdown a HTML, aplica márgenes y mueve ambos archivos al destino anual."""
        print("📝 Procesando archivos Markdown...")

        markdown_files = [
            path
            for path in self.incoming_dir.glob("*.md")
            if self._is_generic_markdown(path)
        ]

        if not markdown_files:
            print("📝 No se encontraron archivos Markdown para procesar")
            return []

        generated_html: List[Path] = []
        for md_file in markdown_files:
            html_path = md_file.with_suffix(".html")

            if html_path.exists():
                print(f"⏭️  Saltando conversión (HTML ya existe): {html_path.name}")
                continue

            try:
                md_text = md_file.read_text(encoding="utf-8", errors="replace")
                full_html = U.markdown_to_html(md_text, title=md_file.stem)
                html_path.write_text(full_html, encoding="utf-8")
                generated_html.append(html_path)
                print(f"✅ HTML generado: {html_path.name}")
            except Exception as exc:
                print(f"❌ Error convirtiendo {md_file.name}: {exc}")

        if generated_html:
            html_targets = {path.resolve() for path in generated_html}

            def _filter(html_path: Path) -> bool:
                return html_path.resolve() in html_targets

            U.add_margins_to_html_files(self.incoming_dir, file_filter=_filter)

        self.title_updater.update_titles(markdown_files, rename_markdown_pair)

        # Recalcular tras posibles renombrados por IA
        markdown_files = [
            path
            for path in self.incoming_dir.glob("*.md")
            if self._is_generic_markdown(path)
        ]

        files_to_move = self._collect_move_candidates(markdown_files)
        moved_files = U.move_files_with_replacement(files_to_move, self.destination_dir)

        if moved_files:
            print(f"📝 {len(moved_files)} archivo(s) Markdown movidos a {self.destination_dir}")

        return moved_files

    def _is_generic_markdown(self, path: Path) -> bool:
        """Determina si el archivo Markdown no pertenece a otros pipelines especializados."""
        if not path.is_file() or path.suffix.lower() != ".md":
            return False
        if U.is_podcast_file(path):
            return False
        if path.name.startswith("Tweets"):
            return False
        return True

    def _collect_move_candidates(self, markdown_files: Iterable[Path]) -> List[Path]:
        """Recopila los archivos (MD + HTML) que deben moverse al destino anual."""
        candidates: List[Path] = []
        for md_file in markdown_files:
            if not md_file.exists():
                continue
            candidates.append(md_file)
            html_file = md_file.with_suffix(".html")
            if html_file.exists():
                candidates.append(html_file)
        return candidates
