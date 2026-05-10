#!/usr/bin/env python3
"""MarkdownProcessor - convert generic Markdown to HTML and archive alongside Instapaper."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
from typing import Iterable, List

import config as cfg
import utils as U
from path_utils import unique_path
from title_ai import TitleAIUpdater, rename_markdown_pair
from openai_client import build_openai_client


class MarkdownProcessor:
    """Process Markdown files in Incoming/ that do not belong to other pipelines."""

    RESERVED_SOURCES = {"instapaper", "podcast", "tweet"}

    def __init__(
        self,
        incoming_dir: Path,
        destination_dir: Path,
        *,
        source_dirs: Iterable[Path] = (),
    ):
        self.incoming_dir = incoming_dir
        self.destination_dir = destination_dir
        self.source_dirs = [Path(path).expanduser() for path in source_dirs]
        openai_client = build_openai_client(cfg.OPENAI_KEY)
        self.title_updater = TitleAIUpdater(openai_client)

    def process_markdown(self) -> List[Path]:
        """Convert Markdown to HTML, apply margins, and move both files to the yearly destination."""
        self._import_source_markdown()
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
        )

    def _import_source_markdown(self) -> List[Path]:
        """Move generic Markdown from configured external folders into Incoming/."""
        imported: List[Path] = []
        self.incoming_dir.mkdir(parents=True, exist_ok=True)

        for source_dir in self.source_dirs:
            if not source_dir.is_dir():
                self._write_import_audit(f"source missing or not a directory: {source_dir}")
                continue
            try:
                same_dir = source_dir.resolve() == self.incoming_dir.resolve()
            except OSError:
                same_dir = False
            if same_dir:
                self._write_import_audit(f"source skipped because it is Incoming: {source_dir}")
                continue

            markdown_candidates = sorted(source_dir.glob("*.md"))
            placeholder_candidates = sorted(
                path
                for path in source_dir.glob("*.icloud")
                if ".md" in path.name.lower() or ".markdown" in path.name.lower()
            )
            has_activity = bool(markdown_candidates or placeholder_candidates)
            audit_events = [
                f"scanning {source_dir}: "
                f"{len(markdown_candidates)} markdown candidate(s), "
                f"{len(placeholder_candidates)} iCloud placeholder candidate(s)"
            ]
            for placeholder_path in placeholder_candidates:
                audit_events.append(f"placeholder not importable yet: {placeholder_path.name}")

            imported_from_source = 0
            ignored_from_source = 0
            for source_path in markdown_candidates:
                if not self._is_generic_markdown(source_path):
                    ignored_from_source += 1
                    source = self._front_matter_source(source_path) or "reserved/non-generic"
                    audit_events.append(f"ignored Markdown ({source}): {source_path.name}")
                    continue

                destination = unique_path(self.incoming_dir / source_path.name)
                try:
                    shutil.move(str(source_path), destination)
                except Exception as exc:
                    message = f"error importing Markdown from {source_path}: {exc}"
                    print(f"❌ Error importing Markdown from {source_path}: {exc}")
                    audit_events.append(message)
                    continue

                imported.append(destination)
                imported_from_source += 1
                print(f"📥 Imported Markdown from iCloud Downloads: {destination.name}")
                audit_events.append(f"imported Markdown: {source_path.name} -> {destination}")

            if has_activity:
                audit_events.append(
                    f"finished {source_dir}: imported {imported_from_source}, ignored {ignored_from_source}"
                )
                for event in audit_events:
                    self._write_import_audit(event)

        return imported

    def _write_import_audit(self, message: str) -> None:
        """Append an import audit entry and mirror it to stdout for cron logs."""
        timestamp = datetime.now().isoformat(timespec="seconds")
        line = f"{timestamp} markdown {message}"
        print(f"🧾 Markdown import audit: {message}")
        try:
            audit_path = self.incoming_dir / "import_audit.log"
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            with audit_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception as exc:
            print(f"⚠️ Could not write Markdown import audit: {exc}")

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
        )

    def _process_markdown_batch(
        self,
        markdown_files: List[Path],
        *,
        context: str,
    ) -> List[Path]:
        print(context)

        markdown_files = self._ensure_docflow_metadata(markdown_files)

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

        if moved_files:
            print(f"📝 {len(moved_files)} Markdown file(s) moved to {self.destination_dir}")

        return moved_files

    def _ensure_docflow_metadata(self, markdown_files: Iterable[Path]) -> List[Path]:
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
