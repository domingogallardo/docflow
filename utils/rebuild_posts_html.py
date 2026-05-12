#!/usr/bin/env python3
"""Rebuild HTML files from Markdown files under BASE_DIR/Posts."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config as cfg
import utils as U


@dataclass(frozen=True)
class FileTimes:
    atime: float
    mtime: float


def _file_times(path: Path) -> FileTimes:
    stat = path.stat()
    return FileTimes(atime=stat.st_atime, mtime=stat.st_mtime)


def _restore_times(path: Path, times: FileTimes) -> None:
    os.utime(path, (times.atime, times.mtime))


def _posts_year_dirs(posts_root: Path, year: str | None) -> list[Path]:
    if year:
        target = posts_root / f"Posts {year}"
        return [target] if target.is_dir() else []
    return sorted(path for path in posts_root.glob("Posts *") if path.is_dir())


def _collect_markdown_files(posts_root: Path, year: str | None) -> list[Path]:
    files: list[Path] = []
    for year_dir in _posts_year_dirs(posts_root, year):
        files.extend(sorted(year_dir.glob("*.md")))
    return files


def rebuild_posts_html(
    *,
    year: str | None = None,
    dry_run: bool = False,
    limit: int | None = None,
) -> int:
    posts_root = cfg.BASE_DIR / "Posts"
    md_files = _collect_markdown_files(posts_root, year)
    if limit is not None:
        md_files = md_files[:limit]

    if not md_files:
        scope = f"Posts {year}" if year else "Posts"
        print(f"No Markdown files found under {scope}.")
        return 0

    print(f"Found {len(md_files)} Markdown file(s) under {posts_root}.")
    if dry_run:
        for md_path in md_files[:20]:
            print(f"Would rebuild: {md_path.relative_to(cfg.BASE_DIR)}")
        if len(md_files) > 20:
            print(f"... and {len(md_files) - 20} more.")
        return 0

    original_times: dict[Path, FileTimes] = {}
    touched_html_by_dir: dict[Path, set[Path]] = {}
    errors: list[tuple[Path, Exception]] = []

    try:
        for index, md_path in enumerate(md_files, start=1):
            html_path = md_path.with_suffix(".html")
            try:
                original_times[md_path] = _file_times(md_path)
                html_existed = html_path.exists()
                if html_existed:
                    original_times[html_path] = _file_times(html_path)

                md_text = md_path.read_text(encoding="utf-8", errors="replace")
                html_path.write_text(U.markdown_to_html(md_text, title=md_path.stem), encoding="utf-8")
                if not html_existed:
                    original_times[html_path] = original_times[md_path]

                touched_html_by_dir.setdefault(html_path.parent, set()).add(html_path.resolve())
                if index % 250 == 0 or index == len(md_files):
                    print(f"Converted {index}/{len(md_files)}")
            except Exception as exc:
                errors.append((md_path, exc))
                print(f"Error converting {md_path.relative_to(cfg.BASE_DIR)}: {exc}")

        for directory, touched_paths in touched_html_by_dir.items():
            U.add_margins_to_html_files(
                directory,
                file_filter=lambda path, touched=touched_paths: path.resolve() in touched,
            )
    finally:
        for path, times in original_times.items():
            if path.exists():
                _restore_times(path, times)

    rebuilt = len(md_files) - len(errors)
    print(f"Rebuilt {rebuilt} HTML file(s).")
    print(f"Preserved mtimes for {len(original_times)} content file(s).")
    if errors:
        print(f"Finished with {len(errors)} error(s).")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild HTML files from Markdown files under DOCFLOW_BASE_DIR/Posts."
    )
    parser.add_argument("--year", help="Only rebuild files under Posts <YEAR>, e.g. 2026.")
    parser.add_argument("--dry-run", action="store_true", help="List what would be rebuilt without writing files.")
    parser.add_argument("--limit", type=int, help="Rebuild at most this many Markdown files.")
    args = parser.parse_args()

    return rebuild_posts_html(year=args.year, dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
