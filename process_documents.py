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

    # 1-4. Sub-scripts de procesamiento
    run_py("scrape.py")
    run_py("html2md.py")
    for step in ("fix_html_encoding.py",
                 "reduce_images_width.py",
                 "add_margin_html.py"):
        run_py(step)
    run_py("update_titles.py")

    # 5. Mover archivos y registrar
    posts = U.list_files({".html", ".htm", ".md"}, root=cfg.INCOMING)
    pdfs  = U.list_files({".pdf"},                 root=cfg.INCOMING)

    moved_posts = U.move_files(posts, cfg.POSTS_DEST)
    moved_pdfs  = U.move_files(pdfs,  cfg.PDFS_DEST)
    U.register_paths(moved_posts + moved_pdfs)


if __name__ == "__main__":
    main()