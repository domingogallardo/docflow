#!/usr/bin/env python3
"""
Process the documents pipeline.

Usage:
    python process_documents.py [--year YYYY] [tweets|urls|pdfs|podcasts|images|md|all]
"""
import argparse

from pipeline_manager import DocumentProcessor, PIPELINE_TARGETS
import config as cfg


def parse_args():
    p = argparse.ArgumentParser(
        description=(
            "Document pipeline: URLs, tweets, podcasts, PDFs, images, and Markdown."
        ),
        epilog=None,
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
