#!/usr/bin/env python3
"""Dump clipboard contents (HTML or text) to a file."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Tuple

# Allow running the script directly from the repo root.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clipboard_cleaner import _read_macos_html_clipboard, _run_command_capture  # type: ignore


def read_clipboard_raw() -> Tuple[str, str]:
    """Return clipboard content and the source used."""
    html = _read_macos_html_clipboard()
    if html:
        return html, "html"
    text = _run_command_capture(["pbpaste"])
    return text, "texto"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Guarda en disco el contenido del portapapeles, "
        "usando las mismas rutas de lectura que mdclip.",
    )
    parser.add_argument(
        "--output",
        default="tmp_clipboard_raw.txt",
        help="Ruta del archivo de salida (por defecto: %(default)s).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    content, source = read_clipboard_raw()
    if not content:
        parser.error("No se pudo leer contenido del portapapeles.")
        return 1

    output_path = Path(args.output)
    output_path.write_text(content, encoding="utf-8")
    print(f"Guardado {len(content)} bytes desde {source} en {output_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
