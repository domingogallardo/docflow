from pathlib import Path
from datetime import datetime
from typing import Iterable, List
import os
import shutil

from config import BASE_DIR, INCOMING, PROCESSED_HISTORY


def list_files(exts, root=None):
    root = INCOMING if root is None else root
    return [p for p in Path(root).rglob("*") if p.suffix.lower() in exts]


def _move_files_common(
    files: Iterable[Path],
    dest: Path,
    *,
    replace_existing: bool,
    skip_missing: bool,
) -> List[Path]:
    """Centralized move with replace options and tolerance for missing files."""
    dest.mkdir(parents=True, exist_ok=True)
    moved: List[Path] = []

    for src in files:
        if skip_missing and not src.exists():
            continue
        new_path = dest / src.name
        if replace_existing and new_path.exists():
            print(f"🔄 Replacing existing file: {new_path.name}")
            new_path.unlink()
        shutil.move(str(src), new_path)
        moved.append(new_path)

    return moved


def move_files(files, dest):
    return _move_files_common(files, dest, replace_existing=False, skip_missing=False)


def move_files_with_replacement(files: Iterable[Path], dest: Path) -> List[Path]:
    """Move files, replacing prior versions when present."""
    return _move_files_common(files, dest, replace_existing=True, skip_missing=True)


def iter_html_files(directory: Path, file_filter=None):
    """Common iterator for HTML files ('.html' or '.htm')."""
    for dirpath, _, filenames in os.walk(directory):
        for filename in filenames:
            if filename.lower().endswith(('.html', '.htm')):
                file_path = Path(dirpath) / filename
                if file_filter is None or file_filter(file_path):
                    yield file_path


def _add_years(dt: datetime, years: int) -> datetime:
    """Add calendar years. If it lands on Feb-29 in a non-leap year, use Feb-28."""
    try:
        return dt.replace(year=dt.year + years)
    except ValueError:
        # Feb-29 → Feb-28 in a non-leap year.
        return dt.replace(month=2, day=28, year=dt.year + years)


def bump_files(files, years: int = 100):
    """Set file mtime to (now + years) + i seconds."""
    if not files:
        return
    base_time = _add_years(datetime.now().replace(microsecond=0), years)
    base_ts = int(base_time.timestamp())
    for i, f in enumerate(files, start=1):
        ts = base_ts + i
        os.utime(f, (ts, ts))  # atime, mtime


def register_paths(paths, base_dir: Path = None, historial_path: Path = None):
    """Register processed paths in the main log. Params overridable for tests."""
    if not paths:
        return

    if base_dir is None:
        base_dir = BASE_DIR
    if historial_path is None:
        historial_path = PROCESSED_HISTORY

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines_new = ["./" + p.relative_to(base_dir).as_posix() + " - " + timestamp + "\n" for p in paths]
    if historial_path.exists():
        old_content = historial_path.read_text(encoding="utf-8")
    else:
        old_content = ""
    historial_path.write_text("".join(lines_new) + old_content, encoding="utf-8")
