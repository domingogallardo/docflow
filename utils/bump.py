#!/usr/bin/env python3
"""
"bump-simple": Igual que la opción 2 (AppleScript):
- mtime := (ahora + 100 años) + i segundos, manteniendo el orden de entrada
- No modifica la fecha de creación
- Preserva atime (como 'touch -mt')
- Repetible: cada ejecución usa una base más reciente

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


def add_years(dt: _dt.datetime, years: int) -> _dt.datetime:
    """Añade años de forma segura (maneja 29-feb)."""
    try:
        return dt.replace(year=dt.year + years)
    except ValueError:
        # Si es 29-feb, retrocede a 28-feb
        return dt.replace(month=2, day=28, year=dt.year + years)


def bump(files: List[Path]) -> None:
    # Base: ahora (zona local) + 100 años, truncado a segundos (igual a 'date -v+100y +%s')
    now_local = _dt.datetime.now().astimezone()
    base_dt = add_years(now_local, 100).replace(microsecond=0)
    base_epoch = int(base_dt.timestamp())

    counter = 0
    for f in files:
        counter += 1
        new_mtime = base_epoch + counter

        # Conservar atime (como hace 'touch -mt', que no lo cambia)
        st = f.stat()  # sigue enlaces simbólicos (igual que AppleScript)
        os.utime(f, (st.st_atime, new_mtime))  # follow_symlinks=True por defecto

        # Mensaje informativo (opcional)
        when_local = _dt.datetime.fromtimestamp(new_mtime).astimezone()
        print(f"Bumped: {f} -> {when_local:%Y-%m-%d %H:%M:%S %Z}")


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
