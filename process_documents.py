#!/usr/bin/env python3
"""
Procesa el pipeline de documentos.

Uso:
    python process_documents.py [--year 2026] [tweets|pdfs|podcasts|posts|all]
"""
import argparse
from datetime import datetime
import os

from pipeline_manager import DocumentProcessor, DocumentProcessorConfig
import config as cfg


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int,
                   help="Usa ese año en lugar del actual")
    p.add_argument(
        "targets",
        nargs="+",
        choices=["tweets", "pdfs", "podcasts", "posts", "all"],
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
            "tweets": processor.process_tweets,
            "posts": processor.process_instapaper_posts,
            "pdfs": processor.process_pdfs,
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
