"""Descarga los tweets marcados como "Me gusta" en X como Markdown listos para el pipeline.

Requisitos previos:
- `pip install playwright requests beautifulsoup4 markdownify markdown` (dependencias mínimas)
- `playwright install chromium`
- Un `storage_state` autenticado obtenido con `python utils/login_x.py --export-state x_state.json`
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import config as cfg
from utils import tweet_to_markdown as tm
from utils import x_likes_fetcher as xl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Descarga los tweets marcados como Me gusta a Markdown autocontenido en un directorio."
        )
    )
    parser.add_argument(
        "--likes-url",
        default=os.environ.get("TWEET_LIKES_URL", xl.DEFAULT_LIKES_URL),
        help="URL de likes de X (p.ej. https://x.com/USUARIO/likes)",
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=Path(os.environ.get("TWEET_LIKES_STATE", "x_state.json")),
        help="Ruta al storage_state exportado tras iniciar sesión en X",
    )
    parser.add_argument(
        "--dest-dir",
        type=Path,
        default=Path(os.environ.get("TWEET_LIKES_DEST", cfg.INCOMING / "tweets_favoritos")),
        help="Directorio donde guardar los Markdown",
    )
    parser.add_argument(
        "--max-tweets",
        type=int,
        default=int(os.environ.get("TWEET_LIKES_MAX", xl.DEFAULT_MAX_TWEETS)),
        help="Límite de likes a capturar en esta ejecución",
    )
    parser.add_argument(
        "--stop-at-url",
        default=os.environ.get("TWEET_LIKES_STOP"),
        help=(
            "URL de tweet a partir del cual dejar de capturar (para evitar duplicados entre ejecuciones)."
        ),
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=int(os.environ.get("TWEET_LIKES_WAIT_MS", 5000)),
        help="Tiempo adicional en milisegundos tras cargar cada tweet",
    )
    headless_group = parser.add_mutually_exclusive_group()
    headless_group.add_argument(
        "--headless",
        dest="headless",
        action="store_true",
        default=True,
        help="Ejecuta Chromium en modo headless (por defecto)",
    )
    headless_group.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Abre Chromium con UI (útil para depurar)",
    )
    return parser.parse_args()


def download_likes(args: argparse.Namespace) -> None:
    likes_url = args.likes_url
    if not likes_url:
        raise SystemExit("--likes-url es obligatorio (ejemplo: https://x.com/USUARIO/likes)")

    state_path: Path = args.state_path.expanduser()
    if not state_path.exists():
        raise SystemExit(f"No se encontró el storage_state: {state_path}")

    dest_dir: Path = args.dest_dir.expanduser()
    dest_dir.mkdir(parents=True, exist_ok=True)

    urls, stop_found, total_articles = xl.fetch_likes_with_state(
        state_path,
        likes_url=likes_url,
        max_tweets=args.max_tweets,
        stop_at_url=args.stop_at_url,
        headless=args.headless,
    )
    print(
        f"🔍 Likes encontrados: {len(urls)} (artículos visibles: {total_articles}). "
        f"Stop URL {'encontrada' if stop_found else 'no encontrada' if args.stop_at_url else 'no usada'}."
    )

    for url in urls:
        markdown, filename = tm.fetch_tweet_markdown(
            url, wait_ms=args.wait_ms, headless=args.headless
        )
        output = dest_dir / filename
        output.write_text(markdown, encoding="utf-8")
        print(f"✅ Guardado: {output}")


def main() -> None:
    args = parse_args()
    download_likes(args)


if __name__ == "__main__":
    main()
