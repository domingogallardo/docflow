#!/usr/bin/env python3
"""
Process the documents pipeline.

Usage:
    python process_documents.py [--year YYYY] [pdfs|podcasts|posts|images|md|all]

Notes:
- Instapaper HTML articles marked as starred are auto-bumped (mtime set to the
  future) so they appear at the top of date-ordered listings.
- To mark as starred in Instapaper: add a star (⭐) at the start of the title.
"""
import argparse

from pipeline_manager import DocumentProcessor, PIPELINE_TARGETS
import config as cfg


def parse_args():
    p = argparse.ArgumentParser(
        description=(
            "Document pipeline: podcasts, Instapaper, PDFs, images, and Markdown. "
            "Starred Instapaper HTML is auto-bumped."
        ),
        epilog=(
            "To mark an article as starred in Instapaper, add a star (⭐) at the start "
            "of the title. The pipeline detects it, propagates the mark to HTML/MD, and "
            "bumps the HTML to prioritize it in date-ordered listings."
        ),
    )
    p.add_argument("--year", type=int,
                   help="Use this year instead of the default (DOCPIPE_YEAR or current year)")
    p.add_argument(
        "targets",
        nargs="+",
        choices=[*PIPELINE_TARGETS, "all"],
        help="Process only the specified types",
    )
    return p.parse_args()


def get_year_from_args_and_env(args) -> int:
    """Get the year from CLI arguments or environment variables."""
    if args.year:
        return args.year
    return cfg.get_default_year()


def main():
    args = parse_args()
    year = get_year_from_args_and_env(args)
    
    # Create processor.
    processor = DocumentProcessor(cfg.BASE_DIR, year)

    if "all" in args.targets:
        success = processor.process_all()
    else:
        success = processor.process_targets(args.targets)

    if not success:
        exit(1)


if __name__ == "__main__":
    main()
