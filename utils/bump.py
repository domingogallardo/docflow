#!/usr/bin/env python3
"""
"bump": Sube archivos a la parte superior en Finder sin renombrar ni mover.

- No abre ni modifica el contenido; solo ajusta la fecha de modificación (mtime).
- Usa fechas futuras (>= 2100-01-01) y suma 1s entre archivos para mantener orden.
- Repetible: escanea la carpeta y continúa por encima del mayor mtime futuro ya existente.

Uso:
  python utils/bump.py <archivo1> [archivo2 ...]
"""

from __future__ import annotations

import datetime as _dt
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List


FUTURE_BASE = _dt.datetime(2100, 1, 1, tzinfo=_dt.timezone.utc)


def ensure_files(paths: Iterable[str]) -> List[Path]:
    files: List[Path] = []
    for p in paths:
        path = Path(p).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"No es un archivo regular: {path}")
        files.append(path)
    if not files:
        raise ValueError("Debe indicar al menos un archivo")
    return files


def group_by_folder(paths: Iterable[Path]) -> Dict[Path, List[Path]]:
    per_folder: Dict[Path, List[Path]] = {}
    for p in paths:
        per_folder.setdefault(p.parent, []).append(p)
    return per_folder


def next_epoch_start(folder: Path) -> float:
    base = FUTURE_BASE.timestamp()
    max_epoch = base
    try:
        for entry in folder.iterdir():
            try:
                t = entry.stat().st_mtime
                if t >= base and t > max_epoch:
                    max_epoch = t
            except FileNotFoundError:
                continue
    except PermissionError:
        pass
    return max_epoch


def bump(files: List[Path]) -> None:
    per_folder = group_by_folder(files)
    # Mantener el orden de invocación por carpeta
    order: Dict[Path, List[Path]] = {f: [] for f in per_folder}
    for p in files:
        order[p.parent].append(p)

    for folder, ordered_files in order.items():
        next_epoch = max(next_epoch_start(folder), FUTURE_BASE.timestamp())
        for f in ordered_files:
            next_epoch += 1.0
            os.utime(f, (next_epoch, next_epoch), follow_symlinks=False)
            when = _dt.datetime.fromtimestamp(next_epoch).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
            print(f"Bumped: {f} -> {when}")


def main(argv: List[str]) -> int:
    if not argv:
        print("Uso: python utils/bump.py <archivo1> [archivo2 ...]", file=sys.stderr)
        return 2
    try:
        files = ensure_files(argv)
        bump(files)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


