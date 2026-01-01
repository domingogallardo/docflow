#!/usr/bin/env python3
"""Standalone command to convert Markdown to HTML using the main pipeline transforms."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List

import config as cfg
import utils as U
from openai_client import build_openai_client
from title_ai import TitleAIUpdater, rename_markdown_pair


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert Markdown files to HTML using the same transformations "
            "as the main pipeline."
        )
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="File paths or directories with Markdown to convert",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        help="Destination directory for processed Markdown/HTML (default: in place)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite HTML files if they already exist",
    )
    return parser.parse_args(argv)


def collect_markdown_files(raw_paths: Iterable[str]) -> List[Path]:
    markdown_files: List[Path] = []
    for raw_path in raw_paths:
        path = Path(raw_path)
        if path.is_dir():
            markdown_files.extend(sorted(path.glob("*.md")))
            continue
        if path.suffix.lower() == ".md":
            markdown_files.append(path)
        else:
            print(f"⚠️  Ignoring non-Markdown path: {path}")
    return markdown_files


def _convert_markdown_files(markdown_files: Iterable[Path], *, force: bool) -> List[Path]:
    generated_html: List[Path] = []
    for md_file in markdown_files:
        if not md_file.exists():
            print(f"⚠️  File not found: {md_file}")
            continue

        html_path = md_file.with_suffix(".html")
        if html_path.exists() and not force:
            print(f"⏭️  Skipping conversion (HTML already exists): {html_path.name}")
            continue

        try:
            md_text = md_file.read_text(encoding="utf-8", errors="replace")
            full_html = U.markdown_to_html(md_text, title=md_file.stem)
            html_path.write_text(full_html, encoding="utf-8")
            generated_html.append(html_path)
            print(f"✅ HTML generated: {html_path}")
        except Exception as exc:
            print(f"❌ Error converting {md_file.name}: {exc}")

    return generated_html


def _apply_margins_to_generated_html(generated_html: Iterable[Path]) -> None:
    targets = {path.resolve() for path in generated_html if path.exists()}
    if not targets:
        return

    def _filter(html_path: Path) -> bool:
        return html_path.resolve() in targets

    parents = {path.parent for path in targets}
    for parent in parents:
        U.add_margins_to_html_files(parent, file_filter=_filter)


def _apply_ai_titles(markdown_files: Iterable[Path]) -> List[Path]:
    openai_client = build_openai_client(cfg.OPENAI_KEY)
    title_updater = TitleAIUpdater(openai_client)
    tracked_paths: List[Path] = []

    def _rename(md_path: Path, new_title: str) -> Path:
        new_path = rename_markdown_pair(md_path, new_title)
        tracked_paths.append(new_path)
        return new_path

    title_updater.update_titles(markdown_files, _rename)

    if tracked_paths:
        return tracked_paths
    return [path for path in markdown_files if path.exists()]


def _collect_move_candidates(markdown_files: Iterable[Path]) -> List[Path]:
    candidates: List[Path] = []
    for md_file in markdown_files:
        if not md_file.exists():
            continue
        candidates.append(md_file)
        html_file = md_file.with_suffix(".html")
        if html_file.exists():
            candidates.append(html_file)
    return candidates


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    markdown_files = collect_markdown_files(args.paths)

    if not markdown_files:
        print("📝 No Markdown files found to convert")
        return 0

    generated_html = _convert_markdown_files(markdown_files, force=args.force)
    _apply_margins_to_generated_html(generated_html)

    markdown_files = _apply_ai_titles(markdown_files)

    if args.output_dir:
        moved_files = U.move_files_with_replacement(
            _collect_move_candidates(markdown_files),
            args.output_dir.expanduser(),
        )
        if moved_files:
            print(f"📝 {len(moved_files)} Markdown file(s) moved to {args.output_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
