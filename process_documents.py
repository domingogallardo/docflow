#!/usr/bin/env python3
"""
Procesa todo el pipeline de documentos.

Uso:
    python process_documents.py [--year 2026]
"""
import argparse
import subprocess
import sys

import config as cfg
import utils  as U


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int,
                   help="Usa ese año en lugar del actual")
    return p.parse_args()


def run_py(script: str):
    subprocess.run([sys.executable, script], check=True)


def main():
    args = parse_args()

    # Ajustar año si se indica
    if args.year:
        cfg.YEAR        = args.year
        cfg.POSTS_DEST  = cfg.BASE_DIR / "Posts" / f"Posts {cfg.YEAR}"
        cfg.PDFS_DEST   = cfg.BASE_DIR / "Pdfs"  / f"Pdfs {cfg.YEAR}"
        cfg.PODCASTS_DEST = cfg.BASE_DIR / "Podcasts" / f"Podcasts {cfg.YEAR}"

    # 0. Detectar y procesar podcasts PRIMERO (antes que html2md)
    podcasts = U.list_podcast_files(cfg.INCOMING)
    if podcasts:
        print(f"📻 Procesando {len(podcasts)} archivo(s) de podcast...")
        # Pipeline específico para podcasts: clean_snip -> md2html -> add_margin
        subprocess.run([sys.executable, "clean_snip.py", "--dir", str(cfg.INCOMING)], check=True)
        subprocess.run([sys.executable, "md2html.py", "--dir", str(cfg.INCOMING)], check=True)
        subprocess.run([sys.executable, "add_margin_html.py", "--dir", str(cfg.INCOMING)], check=True)
        
        # Renombrar podcasts con títulos extraídos de metadatos
        renamed_podcast_files = U.rename_podcast_files(podcasts)
        
        # Mover podcasts INMEDIATAMENTE para separarlos del flujo normal
        moved_podcasts = U.move_files(renamed_podcast_files, cfg.PODCASTS_DEST)
        print(f"📻 {len(moved_podcasts)} archivo(s) de podcast movidos a {cfg.PODCASTS_DEST}")
    else:
        moved_podcasts = []

    # 1-4. Sub-scripts de procesamiento para posts normales
    run_py("scrape.py")
    run_py("html2md.py")
    for step in ("fix_html_encoding.py",
                 "reduce_images_width.py",
                 "add_margin_html.py"):
        run_py(step)
    run_py("update_titles.py")

    # 5. Mover archivos restantes (posts regulares) y registrar
    posts = U.list_files({".html", ".htm", ".md"}, root=cfg.INCOMING)
    pdfs  = U.list_files({".pdf"},                 root=cfg.INCOMING)

    moved_posts = U.move_files(posts, cfg.POSTS_DEST)
    moved_pdfs  = U.move_files(pdfs,  cfg.PDFS_DEST)
    
    # Registrar todos los archivos procesados (posts, PDFs y podcasts)
    U.register_paths(moved_posts + moved_pdfs + moved_podcasts)
    
    print("Pipeline completado ✅")


if __name__ == "__main__":
    main()