#!/usr/bin/env python3
"""Selecciona un artículo al azar y lo copia a Pulse dejando trazabilidad del origen."""

from __future__ import annotations

import random
import shutil
from datetime import datetime
from pathlib import Path

import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import BASE_DIR

POSTS_ROOT = BASE_DIR / "Posts"
PULSE_DIR = BASE_DIR / "Pulse"
def _rel(path: Path) -> str:
    try:
        return "./" + path.relative_to(BASE_DIR).as_posix()
    except ValueError:
        return str(path)


def _sanitize_for_dir(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else "_" for ch in name)
    collapsed = "_".join(cleaned.split())
    return collapsed or "selection"


def _load_candidates() -> list[tuple[Path, Path]]:
    html_files = list(POSTS_ROOT.rglob("*.html"))
    candidates: list[tuple[Path, Path]] = []
    for html_path in html_files:
        md_path = html_path.with_suffix(".md")
        if md_path.exists():
            candidates.append((html_path, md_path))
    return candidates


def _unique_name(base: Path, stem: str, suffix: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = base / f"{stem}_{timestamp}{suffix}"
    counter = 1
    while candidate.exists():
        candidate = base / f"{stem}_{timestamp}_{counter}{suffix}"
        counter += 1
    return candidate


def _copy_selection(html_path: Path, md_path: Path) -> Path:
    PULSE_DIR.mkdir(parents=True, exist_ok=True)
    safe_stem = _sanitize_for_dir(md_path.stem[:80])

    destination = _unique_name(PULSE_DIR, safe_stem, md_path.suffix)
    shutil.copy2(md_path, destination)

    url_stub = _unique_name(PULSE_DIR, safe_stem, ".url")
    url_stub.write_text(
        f"{_rel(md_path)}\n",
        encoding="utf-8",
    )

    print("📦 Copia creada en Pulse:")
    print(f"  - {destination}")
    print(f"📝 Referencia guardada en: {url_stub}")
    return destination.parent


def main() -> None:
    candidates = _load_candidates()
    if not candidates:
        print("⚠️ No se encontraron candidatos con pareja HTML/MD.")
        return

    html_path, md_path = random.choice(candidates)
    print(f"🎯 Seleccionado: {html_path.name}")
    _copy_selection(html_path, md_path)


if __name__ == "__main__":
    main()
