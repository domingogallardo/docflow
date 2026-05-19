"""Backfill Markdown sidecars for PDFs in the local library."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

# Support direct execution: `python utils/backfill_pdf_sidecars.py ...`
if __package__ in (None, ""):
    _REPO_ROOT = Path(__file__).resolve().parents[1]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from utils.markdown_utils import ensure_pdf_sidecar_markdown, split_front_matter
from utils.site_paths import library_roots, resolve_base_dir


@dataclass(frozen=True)
class BackfillResult:
    total_pdfs: int
    created: int
    updated: int
    unchanged: int


def _iter_pdf_paths(base_dir: Path) -> list[Path]:
    pdf_root = library_roots(base_dir)["pdfs"]
    if not pdf_root.is_dir():
        return []

    pdfs: list[Path] = []
    for path in pdf_root.rglob("*.pdf"):
        if any(part.startswith(".") for part in path.relative_to(pdf_root).parts):
            continue
        if path.is_file():
            pdfs.append(path)
    return sorted(pdfs)


def _sidecar_needs_update(pdf_path: Path, *, base_dir: Path) -> bool:
    md_path = pdf_path.with_suffix(".md")
    if not md_path.is_file():
        return True

    meta, _ = split_front_matter(md_path.read_text(encoding="utf-8", errors="replace"))
    try:
        pdf_rel = pdf_path.resolve().relative_to(base_dir.resolve()).as_posix()
        md_rel = md_path.resolve().relative_to(base_dir.resolve()).as_posix()
    except ValueError:
        pdf_rel = pdf_path.as_posix()
        md_rel = md_path.as_posix()

    required = {
        "docflow_pdf_path": pdf_rel,
        "docflow_markdown_path": md_rel,
        "docflow_render_status": "markdown_only",
        "docflow_source_type": "pdf",
    }
    return any(str(meta.get(key, "")).strip() != value for key, value in required.items())


def backfill_pdf_sidecars(base_dir: Path, *, dry_run: bool = False) -> BackfillResult:
    pdfs = _iter_pdf_paths(base_dir)
    created = 0
    updated = 0
    unchanged = 0

    for pdf_path in pdfs:
        md_path = pdf_path.with_suffix(".md")
        existed = md_path.exists()
        needs_update = _sidecar_needs_update(pdf_path, base_dir=base_dir)

        if not needs_update:
            unchanged += 1
            continue

        if not dry_run:
            ensure_pdf_sidecar_markdown(pdf_path, base_dir=base_dir)

        if existed:
            updated += 1
        else:
            created += 1

    return BackfillResult(
        total_pdfs=len(pdfs),
        created=created,
        updated=updated,
        unchanged=unchanged,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or complete Markdown sidecars for library PDFs.")
    parser.add_argument("--base-dir", help="BASE_DIR with Pdfs/ and state/")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing sidecars")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv[1:])
    base_dir = resolve_base_dir(args.base_dir)
    result = backfill_pdf_sidecars(base_dir, dry_run=args.dry_run)
    mode = "would update" if args.dry_run else "updated"
    print(
        f"PDF sidecars: {result.total_pdfs} PDF(s), "
        f"{result.created} created, {result.updated} {mode}, {result.unchanged} unchanged"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
