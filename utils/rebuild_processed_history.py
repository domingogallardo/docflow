#!/usr/bin/env python3
"""
Rebuild Incoming/processed_history.txt from scratch.

• Include all .md in   Posts/Posts <year>/
• Include all .pdf in  Pdfs/Pdfs  <year>/
• Include all .md in   Podcasts/Podcasts <year>/
• Order: newest first, by creation time (st_ctime)
• Overwrite Incoming/processed_history.txt (creates a .bak backup)
"""

import sys
from pathlib import Path

# Add the parent directory to the path to import config.
sys.path.insert(0, str(Path(__file__).parent.parent))

import shutil
from datetime import datetime
import config as cfg  # BASE_DIR, PROCESSED_HISTORY

def collect_files():
    """Return a list of relevant .md and .pdf Paths."""
    files = []

    # Posts
    for year_dir in (cfg.BASE_DIR / "Posts").glob("Posts *"):
        files.extend(year_dir.glob("*.md"))

    # Pdfs
    for year_dir in (cfg.BASE_DIR / "Pdfs").glob("Pdfs *"):
        files.extend(year_dir.glob("*.pdf"))

    # Podcasts
    for year_dir in (cfg.BASE_DIR / "Podcasts").glob("Podcasts *"):
        files.extend(year_dir.glob("*.md"))

    return files

def get_creation_time(path: Path) -> float:
    """
    Return the creation time (st_ctime) for the file.
    On most Unix systems it is the metadata change time,
    but on macOS it is the actual creation time.
    """
    return path.stat().st_ctime

def main():
    all_files = collect_files()

    # Sort by creation time (newest first).
    all_files.sort(key=get_creation_time, reverse=True)

    # Format relative paths with "./" and include creation time.
    lines = []
    for f in all_files:
        creation_time = datetime.fromtimestamp(f.stat().st_ctime).strftime("%Y-%m-%d %H:%M:%S")
        line = "./" + f.relative_to(cfg.BASE_DIR).as_posix() + " - " + creation_time + "\n"
        lines.append(line)

    # Backup.
    if cfg.PROCESSED_HISTORY.exists():
        shutil.copy2(cfg.PROCESSED_HISTORY, cfg.PROCESSED_HISTORY.with_suffix(".bak"))

    # Overwrite processed_history.txt.
    cfg.PROCESSED_HISTORY.write_text("".join(lines), encoding="utf-8")

    print(f"processed_history reconstruido: {len(lines)} entradas (ordenadas por creación).")

if __name__ == "__main__":
    main()
