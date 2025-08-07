#!/usr/bin/env python3
"""
"bump": Sube archivos a la parte superior en Finder sin renombrar ni mover.

- No abre ni modifica el contenido; solo ajusta la fecha de modificación (mtime).
- Base: ahora + 100 años y suma 1s entre archivos para mantener orden.
- Repetible: cada ejecución usa un tiempo base más reciente, por lo que los nuevos
  quedarán por encima de los anteriores.

Uso:
  python utils/bump.py <archivo1> [archivo2 ...]
"""

from __future__ import annotations

import datetime as _dt
import os
import sys
from pathlib import Path
from typing import Iterable, List


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


def group_by_folder(paths: Iterable[Path]):
    per_folder = {}
    for p in paths:
        per_folder.setdefault(p.parent, []).append(p)
    return per_folder


def add_years(dt: _dt.datetime, years: int) -> _dt.datetime:
    """Añade años de forma segura (maneja 29-feb)."""
    try:
        return dt.replace(year=dt.year + years)
    except ValueError:
        # Si es 29-feb, retrocede a 28-feb
        return dt.replace(month=2, day=28, year=dt.year + years)


def bump(files: List[Path]) -> None:
    # Base: ahora + 100 años, en zona local del sistema para parecerse al comportamiento de 'date -v+100y'
    now_local = _dt.datetime.now().astimezone()
    base_dt = add_years(now_local, 100)
    next_epoch = base_dt.timestamp()

    for f in files:
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


