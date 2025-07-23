#!/usr/bin/env python3
"""
Procesa todo el pipeline de documentos.

Uso:
    python process_documents.py [--year 2026]
"""
import argparse
from datetime import datetime
import os

from document_processor import DocumentProcessor, DocumentProcessorConfig
import config as cfg


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int,
                   help="Usa ese año en lugar del actual")
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
    
    # Crear y ejecutar procesador
    processor = DocumentProcessor(config)
    success = processor.process_all()
    
    if not success:
        exit(1)


if __name__ == "__main__":
    main()