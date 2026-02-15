"""Sync consolidated tweet HTML files from the library into the public read site.

Copies files from:
  BASE_DIR/Tweets/Tweets <YEAR>/Consolidado Tweets *.html

To:
  web/public/read/tweets/<YEAR>/Consolidado Tweets *.html

The sync removes stale consolidated files in the destination and preserves source
mtime using copy2.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from utils import build_tweets_index as tweets_index
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from utils import build_tweets_index as tweets_index


@dataclass(frozen=True)
class SyncStats:
    copied: int = 0
    skipped: int = 0
    removed_files: int = 0
    removed_dirs: int = 0


def _is_consolidated_html(path: Path) -> bool:
    if not path.is_file():
        return False
    if not path.name.startswith("Consolidado Tweets "):
        return False
    return path.suffix.lower() in (".html", ".htm")


def _copy_if_needed(src: Path, dst: Path) -> bool:
    if dst.exists():
        src_st = src.stat()
        dst_st = dst.stat()
        if src_st.st_size == dst_st.st_size and src_st.st_mtime_ns == dst_st.st_mtime_ns:
            return False
    shutil.copy2(src, dst)
    return True


def sync_consolidated_tweets(base_dir: Path, output_dir: Path) -> SyncStats:
    index = tweets_index.discover_consolidated_by_year(base_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    removed_files = 0
    removed_dirs = 0

    expected_years = {str(year) for year in index}
    for child in output_dir.iterdir():
        if child.is_dir() and child.name.isdigit() and len(child.name) == 4 and child.name not in expected_years:
            shutil.rmtree(child)
            removed_dirs += 1

    # Remove legacy flat consolidated files from the tweets root.
    for child in output_dir.iterdir():
        if _is_consolidated_html(child):
            child.unlink()
            removed_files += 1

    for year, files in index.items():
        year_dir = output_dir / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)

        src_year_dir = base_dir / "Tweets" / f"Tweets {year}"
        keep_names: set[str] = set()

        for item in files:
            src_path = src_year_dir / item.name
            if not src_path.is_file():
                continue
            keep_names.add(item.name)
            dst_path = year_dir / item.name
            if _copy_if_needed(src_path, dst_path):
                copied += 1
            else:
                skipped += 1

        for child in year_dir.iterdir():
            if _is_consolidated_html(child) and child.name not in keep_names:
                child.unlink()
                removed_files += 1

    return SyncStats(copied=copied, skipped=skipped, removed_files=removed_files, removed_dirs=removed_dirs)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync consolidated tweet HTML files into web/public/read/tweets.")
    parser.add_argument("--base-dir", help="Base directory that contains Tweets/Tweets <YEAR> folders.")
    parser.add_argument(
        "--output-dir",
        default=str(Path("web") / "public" / "read" / "tweets"),
        help="Output directory for public tweet consolidated files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_dir = tweets_index.resolve_base_dir(args.base_dir)
    if base_dir is None:
        print("❌ Could not resolve BASE_DIR for tweet sync.")
        return 1

    output_dir = Path(args.output_dir)
    stats = sync_consolidated_tweets(base_dir, output_dir)
    print(
        "✓ Synced tweet consolidated files in "
        f"{output_dir} (copied={stats.copied}, skipped={stats.skipped}, "
        f"removed_files={stats.removed_files}, removed_dirs={stats.removed_dirs})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
