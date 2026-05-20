#!/usr/bin/env python3
"""MarkdownProcessor - convert generic Markdown to HTML and archive it."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

import config as cfg
import utils as U
from title_ai import TitleAIUpdater, rename_markdown_pair
from openai_client import build_openai_client
from summary_ai import SummaryAIUpdater


class MarkdownProcessor:
    """Process Markdown files in Incoming/ that do not belong to other pipelines."""

    RESERVED_SOURCES = {"podcast", "tweet"}

    def __init__(
        self,
        incoming_dir: Path,
        destination_dir: Path,
    ):
        self.incoming_dir = incoming_dir
        self.destination_dir = destination_dir
        openai_client = build_openai_client(cfg.OPENAI_KEY)
        self.title_updater = TitleAIUpdater(openai_client)
        self.summary_updater = SummaryAIUpdater(openai_client)

    def process_markdown(self) -> List[Path]:
        """Convert Markdown to HTML, apply margins, and move both files to the yearly destination."""
        markdown_files = [
            path
            for path in self.incoming_dir.glob("*.md")
            if self._is_generic_markdown(path)
        ]

        if not markdown_files:
            print("📝 No Markdown files found to process")
            return []

        return self._process_markdown_batch(
            markdown_files,
            context="📝 Processing Markdown files...",
            include_summary=True,
        )

    def process_tweet_markdown_subset(self, markdown_files: Iterable[Path]) -> List[Path]:
        """Process a specific tweet Markdown subset (for example, newly downloaded tweets)."""
        selected: List[Path] = []
        for raw_path in markdown_files:
            path = Path(raw_path)
            if self.is_tweet_markdown(path):
                selected.append(path)

        if not selected:
            print("🐦 No valid tweet Markdown files to process")
            return []

        return self._process_markdown_batch(
            selected,
            context=f"📝 Processing {len(selected)} selected Markdown file(s)...",
            include_summary=False,
        )

    def _process_markdown_batch(
        self,
        markdown_files: List[Path],
        *,
        context: str,
        include_summary: bool,
    ) -> List[Path]:
        print(context)

        markdown_files = self._ensure_docflow_metadata(
            markdown_files,
            include_summary=include_summary,
        )

        generated_html: List[Path] = []
        for md_file in markdown_files:
            html_path = md_file.with_suffix(".html")

            if html_path.exists():
                print(f"⏭️  Skipping conversion (HTML already exists): {html_path.name}")
                continue

            try:
                md_text = md_file.read_text(encoding="utf-8", errors="replace")
                md_text = U.upsert_front_matter(
                    md_text,
                    {"docflow_html_generated_at": U.utc_now_iso()},
                )
                md_file.write_text(md_text, encoding="utf-8")
                full_html = U.markdown_to_html(md_text, title=md_file.stem)
                html_path.write_text(full_html, encoding="utf-8")
                generated_html.append(html_path)
                print(f"✅ HTML generated: {html_path.name}")
            except Exception as exc:
                print(f"❌ Error converting {md_file.name}: {exc}")

        if generated_html:
            html_targets = {path.resolve() for path in generated_html}

            def _filter(html_path: Path) -> bool:
                return html_path.resolve() in html_targets

            U.add_margins_to_html_files(self.incoming_dir, file_filter=_filter)

        tracked_paths: List[Path] = []

        def _rename(md_path: Path, new_title: str) -> Path:
            new_path = rename_markdown_pair(md_path, new_title)
            self._refresh_title_metadata(new_path, new_title)
            tracked_paths.append(new_path)
            return new_path

        self.title_updater.update_titles(markdown_files, _rename)

        if tracked_paths:
            markdown_files = tracked_paths
        else:
            markdown_files = [path for path in markdown_files if path.exists()]

        files_to_move = self._collect_move_candidates(markdown_files)
        moved_files = U.move_files_with_replacement(files_to_move, self.destination_dir)
        U.sync_markdown_html_pairs_metadata(moved_files, base_dir=cfg.BASE_DIR)

        if moved_files:
            print(f"📝 {len(moved_files)} Markdown file(s) moved to {self.destination_dir}")

        return moved_files

    def _ensure_docflow_metadata(
        self,
        markdown_files: Iterable[Path],
        *,
        include_summary: bool,
    ) -> List[Path]:
        """Ensure Markdown files carry baseline docflow metadata before conversion."""
        updated_paths: List[Path] = []
        for md_file in markdown_files:
            if not md_file.exists():
                continue
            try:
                original = md_file.read_text(encoding="utf-8", errors="replace")
                title = U.extract_markdown_title(original) or md_file.stem
                updated = U.enrich_markdown_metadata(original, title=title)
                if updated != original:
                    md_file.write_text(updated, encoding="utf-8")
                if include_summary:
                    self.summary_updater.add_summary_to_file(md_file)
            except Exception as exc:
                print(f"⚠️ Could not update metadata for {md_file.name}: {exc}")
            updated_paths.append(md_file)
        return updated_paths

    @staticmethod
    def _refresh_title_metadata(md_path: Path, title: str) -> None:
        if not md_path.exists():
            return
        try:
            original = md_path.read_text(encoding="utf-8", errors="replace")
            updated = U.upsert_front_matter(original, {"title": title})
            if updated != original:
                md_path.write_text(updated, encoding="utf-8")
        except Exception as exc:
            print(f"⚠️ Could not refresh title metadata for {md_path.name}: {exc}")

    def _is_generic_markdown(self, path: Path) -> bool:
        """Determine whether the Markdown file does not belong to other specialized pipelines."""
        if not path.is_file() or path.suffix.lower() != ".md":
            return False
        return self._front_matter_source(path) not in self.RESERVED_SOURCES

    @staticmethod
    def is_tweet_markdown(path: Path) -> bool:
        return MarkdownProcessor._front_matter_source(path) == "tweet"

    @staticmethod
    def is_tweet_article_markdown(path: Path) -> bool:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return False
        meta, _ = U.split_front_matter(text)
        return (
            meta.get("source", "").strip().lower() == "tweet"
            and meta.get("tweet_content_type", "").strip().lower() == "article"
        )

    @staticmethod
    def _front_matter_source(path: Path) -> str:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                lines = []
                for _ in range(64):
                    line = fh.readline()
                    if not line:
                        break
                    lines.append(line.rstrip("\n"))
        except Exception:
            return ""

        if not lines or lines[0].strip() != "---":
            return ""

        for line in lines[1:]:
            stripped = line.strip()
            if stripped == "---":
                return ""
            if ":" not in line:
                continue
            key, raw = line.split(":", 1)
            key = key.strip()
            if key != "source":
                continue
            value = raw.strip().strip("'\"")
            return value.lower()
        return ""

    def _collect_move_candidates(self, markdown_files: Iterable[Path]) -> List[Path]:
        """Collect files (MD + HTML) to move to the yearly destination."""
        candidates: List[Path] = []
        for md_file in markdown_files:
            if not md_file.exists():
                continue
            candidates.append(md_file)
            html_file = md_file.with_suffix(".html")
            if html_file.exists():
                candidates.append(html_file)
        return candidates
