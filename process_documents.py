#!/usr/bin/env python3
"""
Procesa el pipeline de documentos.

Uso:
    python process_documents.py [--year 2026] [pdfs|podcasts|posts|images|md|all]

Notas:
- Los artículos HTML de Instapaper marcados como destacados se bumpean automáticamente
  (se ajusta su mtime al futuro) para que aparezcan arriba en listados por fecha.
- Para destacar en Instapaper: basta con añadir una estrella (⭐) al inicio del título.
"""
import argparse
from datetime import datetime
import os

from pipeline_manager import DocumentProcessor, DocumentProcessorConfig
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
                   help="Usa ese año en lugar del actual")
    p.add_argument(
        "targets",
        nargs="+",
        choices=["pdfs", "podcasts", "posts", "images", "md", "all"],
        help="Procesa solo los tipos indicados",
    )
    return p.parse_args()


def get_year_from_args_and_env(args) -> int:
    """Obtiene el año de los argumentos de línea de comandos o variables de entorno."""
    if args.year:
        return args.year
    return int(os.getenv("DOCPIPE_YEAR", datetime.now().year))


def main():
    args = parse_args()
    year = get_year_from_args_and_env(args)
    
    # Crear configuración del procesador
    config = DocumentProcessorConfig(base_dir=cfg.BASE_DIR, year=year)
    
    # Crear procesador
    processor = DocumentProcessor(config)

    if "all" in args.targets:
        success = processor.process_all()
    else:
        mapping = {
            "podcasts": processor.process_podcasts,
            "posts": processor.process_instapaper_posts,
            "pdfs": processor.process_pdfs,
            "images": processor.process_images,
            "md": processor.process_markdown,
        }
        try:
            for target in args.targets:
                mapping[target]()
            processor.register_all_files()
            print("Pipeline completado ✅")
            success = True
        except Exception as e:
            print(f"❌ Error en el pipeline: {e}")
            success = False

    if not success:
        exit(1)


if __name__ == "__main__":
    main()
