"""Backfill post ingest timestamps from meaningful article file mtimes."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Support direct execution: `python utils/backfill_post_ingested_dates_from_mtime.py ...`
if __package__ in (None, ""):
    _REPO_ROOT = Path(__file__).resolve().parents[1]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from utils.markdown_utils import split_front_matter, update_html_meta_tags, upsert_front_matter
from utils.site_paths import library_roots, resolve_base_dir

DEFAULT_AFTER = "2025-03-20T23:59:59Z"


@dataclass(frozen=True)
class BackfillResult:
    scanned: int
    updated: int
    skipped_existing: int
    skipped_old_mtime: int


def _iter_post_markdown_paths(base_dir: Path) -> list[Path]:
    posts_root = library_roots(base_dir)["posts"]
    if not posts_root.is_dir():
        return []

    paths: list[Path] = []
    for path in posts_root.rglob("*.md"):
        if any(part.startswith(".") for part in path.relative_to(posts_root).parts):
            continue
        if path.name == "report.md":
            continue
        if path.is_file():
            paths.append(path)
    return sorted(paths)


def _parse_after(value: str) -> float:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _mtime_iso(path: Path) -> str:
    return (
        datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def backfill_post_ingested_dates_from_mtime(
    base_dir: Path,
    *,
    after: str = DEFAULT_AFTER,
    dry_run: bool = False,
    verbose: bool = False,
) -> BackfillResult:
    after_epoch = _parse_after(after)
    scanned = 0
    updated = 0
    skipped_existing = 0
    skipped_old_mtime = 0

    for md_path in _iter_post_markdown_paths(base_dir):
        scanned += 1
        original_stat = md_path.stat()
        if original_stat.st_mtime <= after_epoch:
            skipped_old_mtime += 1
            continue

        md_text = md_path.read_text(encoding="utf-8", errors="replace")
        meta, _ = split_front_matter(md_text)
        if str(meta.get("docflow_ingested_at", "")).strip():
            skipped_existing += 1
            continue

        ingested_at = _mtime_iso(md_path)
        if dry_run:
            updated += 1
            if verbose:
                print(f"would update: {md_path}: {ingested_at}")
            continue

        updated_md = upsert_front_matter(md_text, {"docflow_ingested_at": ingested_at})
        if updated_md != md_text:
            md_path.write_text(updated_md, encoding="utf-8")
            os.utime(md_path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

        html_path = md_path.with_suffix(".html")
        if html_path.is_file():
            html_stat = html_path.stat()
            updated_meta, _ = split_front_matter(updated_md)
            update_html_meta_tags(html_path, updated_meta)
            os.utime(html_path, ns=(html_stat.st_atime_ns, html_stat.st_mtime_ns))

        updated += 1
        if verbose:
            print(f"updated: {md_path}: {ingested_at}")

    return BackfillResult(
        scanned=scanned,
        updated=updated,
        skipped_existing=skipped_existing,
        skipped_old_mtime=skipped_old_mtime,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill missing post docflow_ingested_at values from file mtime.")
    parser.add_argument("--base-dir", help="BASE_DIR with Posts/")
    parser.add_argument(
        "--after",
        default=DEFAULT_AFTER,
        help=(
            "Only use article Markdown mtimes after this ISO timestamp. "
            f"Defaults to {DEFAULT_AFTER}, the end of the initial normalization window."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing Markdown")
    parser.add_argument("--verbose", action="store_true", help="Print every planned or applied update")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv[1:])
    base_dir = resolve_base_dir(args.base_dir)
    result = backfill_post_ingested_dates_from_mtime(
        base_dir,
        after=args.after,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
    mode = "would update" if args.dry_run else "updated"
    print(
        f"Post ingested dates from mtime: scanned {result.scanned}, "
        f"{result.updated} {mode}, {result.skipped_existing} skipped existing, "
        f"{result.skipped_old_mtime} skipped old mtime"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
