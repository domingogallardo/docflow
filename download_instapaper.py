#!/usr/bin/env python3
"""Comando standalone para descargar artículos de Instapaper.

Guarda todos los artículos disponibles en un directorio indicado tanto
como HTML como Markdown, sin ejecutar el pipeline completo.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from instapaper_processor import InstapaperProcessor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Descarga todos los artículos de Instapaper como HTML y Markdown "
            "en un directorio específico."
        )
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        help="Directorio donde se guardarán los artículos descargados.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Ignora el registro local (.instapaper_downloads.txt) y fuerza la "
            "descarga de todos los artículos."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    output_dir = args.output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    processor = InstapaperProcessor(output_dir, output_dir)
    exported_files = processor.download_instapaper_exports(
        force_download=args.force
    )

    if not exported_files:
        print(
            "⚠️  No se generaron archivos. Verifica las credenciales o si ya no "
            "hay artículos disponibles."
        )
        return

    print(f"✅ Descarga completada: {len(exported_files)} archivo(s) en {output_dir}")


if __name__ == "__main__":
    main()
