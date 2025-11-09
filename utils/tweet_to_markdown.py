#!/usr/bin/env python3
"""Convierte un tweet público en un archivo Markdown autocontenido."""
from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlparse
from typing import List

try:  # pragma: no cover - import opcional
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
except ImportError:  # pragma: no cover - entorno sin Playwright
    PlaywrightTimeoutError = RuntimeError  # type: ignore[misc,assignment]
    sync_playwright = None  # type: ignore[assignment]

import config as cfg

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)


def rebuild_urls_from_lines(text: str) -> str:
    """Reconstruye URLs que X corta con saltos de línea y puntos suspensivos."""
    lines = text.splitlines()
    out: List[str] = []
    building_url = False

    for original_line in lines:
        stripped = original_line.strip()

        if stripped == "…":
            building_url = False
            continue

        if stripped.startswith(("https://", "http://")):
            out.append(stripped)
            building_url = True
            continue

        if building_url:
            if not stripped or stripped.endswith(":"):
                out.append(original_line)
                building_url = False
            else:
                out[-1] = out[-1] + stripped
        else:
            out.append(original_line)

    return "\n".join(out)


def _safe_filename(name: str) -> str:
    cleaned = "".join(ch for ch in name if ch not in '<>:"/\\|?*#').strip()
    cleaned = " ".join(cleaned.split())
    return cleaned[:200] or "Tweet"


def _build_title(author_name: str | None, author_handle: str | None) -> str:
    base = "Tweet"
    if author_name or author_handle:
        base += " de "
        if author_name:
            base += author_name
        if author_handle:
            base += f" ({author_handle})"
    return base


def _build_filename(url: str, author_handle: str | None) -> str:
    tweet_id = Path(urlparse(url).path).name or "tweet"
    handle = (author_handle or "tweet").lstrip("@") or "tweet"
    base = f"Tweet - {handle}-{tweet_id}"
    return f"{_safe_filename(base)}.md"


def fetch_tweet_markdown(
    url: str,
    *,
    wait_ms: int = 5000,
    headless: bool = True,
) -> tuple[str, str]:
    """Devuelve (markdown, filename) para el tweet indicado."""
    if sync_playwright is None:
        raise RuntimeError(
            "playwright no está instalado. Ejecuta 'pip install playwright' y "
            "'playwright install chromium' para usar esta utilidad."
        )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(wait_ms)

        article = page.locator("article")
        if article.count() == 0:
            raise RuntimeError("No se encontró el <article> del post.")
        article = article.first

        author_name = None
        author_handle = None
        for txt in article.locator("span").all_text_contents():
            text = txt.strip()
            if not text:
                continue
            if text.startswith("@") and author_handle is None:
                author_handle = text
            elif author_name is None and not text.startswith("@"):
                author_name = text

        raw_text = article.inner_text()
        body_text = rebuild_urls_from_lines(raw_text).strip()

        image_urls: List[str] = []
        seen: set[str] = set()
        for img in article.locator("img").all():
            src = img.get_attribute("src")
            candidate = None
            if src and "twimg.com" in src:
                candidate = src
            else:
                srcset = img.get_attribute("srcset")
                if srcset and "twimg.com" in srcset:
                    parts = [p.strip() for p in srcset.split(",") if p.strip()]
                    if parts:
                        candidate = parts[-1].split(" ")[0]
            if candidate and candidate not in seen:
                seen.add(candidate)
                image_urls.append(candidate)

        title = _build_title(author_name, author_handle)
        filename = _build_filename(url, author_handle)

        md_lines = [f"# {title}", "", f"[Ver en X]({url})"]

        if body_text:
            md_lines.extend(["", body_text, ""])

        for idx, image_url in enumerate(image_urls, start=1):
            md_lines.append(f"![image {idx}]({image_url})")
        if image_urls:
            md_lines.append("")

        markdown = "\n".join(md_lines).strip() + "\n"

        browser.close()
        return markdown, filename


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Descarga un tweet público y lo guarda como Markdown listo para el pipeline.",
    )
    parser.add_argument("url", help="URL del tweet en https://x.com/...")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=cfg.INCOMING,
        help=f"Directorio donde guardar el Markdown (por defecto: {cfg.INCOMING})",
    )
    parser.add_argument(
        "--filename",
        help="Nombre de archivo a usar (sobrescribe el generado automáticamente).",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=5000,
        help="Tiempo adicional en milisegundos para esperar tras cargar la página.",
    )
    headless_group = parser.add_mutually_exclusive_group()
    headless_group.add_argument(
        "--headless",
        dest="headless",
        action="store_true",
        default=True,
        help="Ejecuta Chromium en modo headless (por defecto).",
    )
    headless_group.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Abre Chromium con UI (útil para depurar).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir: Path = args.output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        markdown, auto_filename = fetch_tweet_markdown(
            args.url,
            wait_ms=args.wait_ms,
            headless=args.headless,
        )
    except PlaywrightTimeoutError as exc:
        raise SystemExit(f"❌ Timeout cargando el tweet: {exc}") from exc
    except Exception as exc:  # pragma: no cover - salida controlada CLI
        raise SystemExit(f"❌ Error extrayendo el tweet: {exc}") from exc

    filename = args.filename or auto_filename
    destination = output_dir / filename
    destination.write_text(markdown, encoding="utf-8")
    print(f"🐦 Tweet guardado en {destination}")


if __name__ == "__main__":
    main()
