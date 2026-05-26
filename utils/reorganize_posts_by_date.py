"""Move post Markdown/HTML pairs to the folder implied by docflow dates."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Support direct execution: `python utils/reorganize_posts_by_date.py ...`
if __package__ in (None, ""):
    _REPO_ROOT = Path(__file__).resolve().parents[1]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from utils.markdown_utils import (
    split_front_matter,
    sync_markdown_html_pair_metadata,
    sync_markdown_only_metadata,
)
from utils.site_paths import library_roots, resolve_base_dir

POSTS_FOLDER_RE = re.compile(r"^Posts (\d{4})$")


@dataclass(frozen=True)
class MovePlan:
    md_path: Path
    target_dir: Path
    reason: str
    effective_year: int
    html_path: Path | None


@dataclass(frozen=True)
class ReorganizeResult:
    scanned: int
    planned: int
    moved: int
    unchanged: int
    skipped_no_year: int
    conflicts: int


def _iter_post_markdown_paths(base_dir: Path) -> list[Path]:
    posts_root = library_roots(base_dir)["posts"]
    if not posts_root.is_dir():
        return []

    paths: list[Path] = []
    for path in posts_root.rglob("*.md"):
        if any(part.startswith(".") for part in path.relative_to(posts_root).parts):
            continue
        if path.is_file():
            paths.append(path)
    return sorted(paths)


def _folder_year(path: Path) -> int | None:
    for parent in path.parents:
        match = POSTS_FOLDER_RE.match(parent.name)
        if match:
            return int(match.group(1))
    return None


def _date_year(value: str | None) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.year


def effective_post_year(meta: dict[str, str], current_folder_year: int | None = None) -> tuple[int | None, str]:
    """Return the folder year implied by docflow date metadata.

    Rule:
    - Prefer the real ingest year when `docflow_ingested_at` exists.
    - Otherwise use the original publication year when available.
    - Otherwise keep the current folder year.
    """
    ingested_year = _date_year(meta.get("docflow_ingested_at"))
    if ingested_year is not None:
        return ingested_year, "docflow_ingested_at"

    original_year = _date_year(meta.get("docflow_original_published_at"))
    if original_year is not None:
        return original_year, "docflow_original_published_at"

    if current_folder_year is not None:
        return current_folder_year, "current_folder"
    return None, "missing"


def _move_file_preserving_stat(src: Path, dest: Path, stat_result: os.stat_result) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), dest)
    os.utime(dest, ns=(stat_result.st_atime_ns, stat_result.st_mtime_ns))
    return dest


def _has_conflict(plan: MovePlan) -> bool:
    target_md = plan.target_dir / plan.md_path.name
    if target_md.exists() and target_md.resolve() != plan.md_path.resolve():
        return True

    if plan.html_path is not None:
        target_html = plan.target_dir / plan.html_path.name
        if target_html.exists() and target_html.resolve() != plan.html_path.resolve():
            return True
    return False


def build_move_plans(base_dir: Path) -> tuple[list[MovePlan], int, int, int]:
    scanned = 0
    unchanged = 0
    skipped_no_year = 0
    plans: list[MovePlan] = []
    posts_root = library_roots(base_dir)["posts"]

    for md_path in _iter_post_markdown_paths(base_dir):
        scanned += 1
        folder_year = _folder_year(md_path)
        meta, _ = split_front_matter(md_path.read_text(encoding="utf-8", errors="replace"))
        effective_year, reason = effective_post_year(meta, folder_year)
        if effective_year is None:
            skipped_no_year += 1
            continue

        target_dir = posts_root / f"Posts {effective_year}"
        if md_path.parent == target_dir:
            unchanged += 1
            continue

        html_path = md_path.with_suffix(".html")
        plans.append(
            MovePlan(
                md_path=md_path,
                target_dir=target_dir,
                reason=reason,
                effective_year=effective_year,
                html_path=html_path if html_path.is_file() else None,
            )
        )

    return plans, scanned, unchanged, skipped_no_year


def reorganize_posts_by_date(base_dir: Path, *, dry_run: bool = False, verbose: bool = False) -> ReorganizeResult:
    plans, scanned, unchanged, skipped_no_year = build_move_plans(base_dir)
    conflicts = 0
    moved = 0

    for plan in plans:
        if _has_conflict(plan):
            conflicts += 1
            if verbose:
                print(f"conflict: {plan.md_path} -> {plan.target_dir}")
            continue

        if dry_run:
            if verbose:
                print(f"would move: {plan.md_path.name} -> {plan.target_dir.name} ({plan.reason})")
            continue

        md_stat = plan.md_path.stat()
        html_stat = plan.html_path.stat() if plan.html_path is not None else None
        new_md = _move_file_preserving_stat(plan.md_path, plan.target_dir / plan.md_path.name, md_stat)
        new_html = None
        if plan.html_path is not None and html_stat is not None:
            new_html = _move_file_preserving_stat(plan.html_path, plan.target_dir / plan.html_path.name, html_stat)

        if new_html is not None:
            sync_markdown_html_pair_metadata(new_md, new_html, base_dir=base_dir)
            os.utime(new_md, ns=(md_stat.st_atime_ns, md_stat.st_mtime_ns))
            os.utime(new_html, ns=(html_stat.st_atime_ns, html_stat.st_mtime_ns))
        else:
            sync_markdown_only_metadata(new_md, base_dir=base_dir)
            os.utime(new_md, ns=(md_stat.st_atime_ns, md_stat.st_mtime_ns))
        moved += 1

    return ReorganizeResult(
        scanned=scanned,
        planned=len(plans),
        moved=moved,
        unchanged=unchanged,
        skipped_no_year=skipped_no_year,
        conflicts=conflicts,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Move Posts markdown/html pairs to folders implied by date metadata.")
    parser.add_argument("--base-dir", help="BASE_DIR with Posts/")
    parser.add_argument("--dry-run", action="store_true", help="Report moves without changing files")
    parser.add_argument("--verbose", action="store_true", help="Print every planned move or conflict")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv[1:])
    base_dir = resolve_base_dir(args.base_dir)
    result = reorganize_posts_by_date(base_dir, dry_run=args.dry_run, verbose=args.verbose)
    move_count = result.planned - result.conflicts if args.dry_run else result.moved
    mode = "would move" if args.dry_run else "moved"
    print(
        f"Post reorganization: scanned {result.scanned}, "
        f"{result.planned} planned, {move_count} {mode}, "
        f"{result.unchanged} unchanged, {result.skipped_no_year} without year, "
        f"{result.conflicts} conflicts"
    )
    return 1 if result.conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
