#!/usr/bin/env python3
"""
Procesa el pipeline de documentos.

Uso:
    python process_documents.py [--year AAAA] [pdfs|podcasts|posts|images|md|all]

Notas:
- Los artículos HTML de Instapaper marcados como destacados se bumpean automáticamente
  (se ajusta su mtime al futuro) para que aparezcan arriba en listados por fecha.
- Para destacar en Instapaper: basta con añadir una estrella (⭐) al inicio del título.
"""
import argparse

from pipeline_manager import DocumentProcessor, PIPELINE_TARGETS
import config as cfg


def parse_args():
    p = argparse.ArgumentParser(
        description=(
            "Pipeline de documentos: podcasts, Instapaper, PDFs, imágenes y Markdown. "
            "Los HTML de Instapaper destacados se bumpean automáticamente."
        ),
        epilog=(
            "Para marcar un artículo como destacado en Instapaper, añade una estrella (⭐) "
            "al inicio del título. El pipeline lo detecta, propaga la marca a HTML/MD y "
            "bumpéa el HTML para priorizarlo en listados por fecha."
        ),
    )
    p.add_argument("--year", type=int,
                   help="Usa ese año en lugar del año por defecto (DOCPIPE_YEAR o año actual)")
    p.add_argument(
        "targets",
        nargs="+",
        choices=[*PIPELINE_TARGETS, "all"],
        help="Procesa solo los tipos indicados",
    )
    return p.parse_args()


def get_year_from_args_and_env(args) -> int:
    """Obtiene el año de los argumentos de línea de comandos o variables de entorno."""
    if args.year:
        return args.year
    return cfg.get_default_year()


def main():
    args = parse_args()
    year = get_year_from_args_and_env(args)
    
    # Crear procesador
    processor = DocumentProcessor(cfg.BASE_DIR, year)

    if "all" in args.targets:
        success = processor.process_all()
    else:
        success = processor.process_targets(args.targets)

    if not success:
        exit(1)


if __name__ == "__main__":
    main()
