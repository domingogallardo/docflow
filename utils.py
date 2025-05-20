from pathlib import Path
from config import BASE_DIR, INCOMING, HISTORIAL
import os, shutil, logging

def list_files(exts, root=INCOMING):
    return [p for p in Path(root).rglob("*") if p.suffix.lower() in exts]

def move_files(files, dest):
    dest.mkdir(parents=True, exist_ok=True)
    moved = []
    for f in files:
        new_path = dest / f.name
        shutil.move(str(f), new_path)
        moved.append(new_path)
    return moved

def register_paths(paths):
    if not paths:
        return
    lines_new = ["./" + p.relative_to(BASE_DIR).as_posix() + "\n" for p in paths]
    if HISTORIAL.exists():
        old_content = HISTORIAL.read_text(encoding="utf-8")
    else:
        old_content = ""
    HISTORIAL.write_text("".join(lines_new) + old_content, encoding="utf-8")

def setup_logging(level="INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )