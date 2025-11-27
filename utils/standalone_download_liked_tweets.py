"""Descarga los tweets marcados como 'Me gusta' en X a Markdown, sin depender del resto del repo."""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

try:  # pragma: no cover - import opcional
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
except ImportError:  # pragma: no cover - entorno sin Playwright
    PlaywrightTimeoutError = RuntimeError  # type: ignore[misc,assignment]
    sync_playwright = None  # type: ignore[assignment]

DEFAULT_LIKES_URL = "https://x.com/domingogallardo/likes"
DEFAULT_MAX_TWEETS = 100
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
STEALTH_SNIPPET = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = window.chrome || { runtime: {} };
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
  parameters.name === 'notifications'
    ? Promise.resolve({ state: Notification.permission })
    : originalQuery(parameters)
);
"""


# --- Helpers de conversión a Markdown (adaptados de tweet_to_markdown.py) ---
STAT_KEYWORDS = (
    "retweet",
    "retuits",
    "retuit",
    "repost",
    "republicaciones",
    "quotes",
    "citas",
    "likes",
    "me gusta",
    "favoritos",
    "bookmarks",
    "marcadores",
    "views",
    "visualizaciones",
    "impresiones",
    "replies",
    "respuestas",
    "shares",
    "compartidos",
    "guardados",
    "read repl",
    "leer resp",
)
STAT_NUMBER_RE = re.compile(r"^\d[\d.,]*(?:\s?[kmbKMB])?$")
TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")


def rebuild_urls_from_lines(text: str) -> str:
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


def _collapse_blank_lines(lines: List[str]) -> List[str]:
    collapsed: List[str] = []
    previous_blank = True
    for line in lines:
        if not line:
            if previous_blank:
                continue
            collapsed.append("")
            previous_blank = True
            continue
        collapsed.append(line)
        previous_blank = False
    if collapsed and not collapsed[-1]:
        collapsed.pop()
    return collapsed


def _is_timestamp_line(line: str) -> bool:
    lower = line.lower()
    return bool(TIME_RE.search(line) and ("am" in lower or "pm" in lower))


def _is_keyword_stat(line: str) -> bool:
    lower = line.lower()
    return any(keyword in lower for keyword in STAT_KEYWORDS)


def _is_numeric_stat(line: str) -> bool:
    if line == "·":
        return True
    if STAT_NUMBER_RE.match(line):
        return True
    if line.lower().startswith("read ") and "repl" in line.lower():
        return True
    return False


def strip_tweet_stats(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    lines = _collapse_blank_lines(lines)

    while lines and not lines[-1]:
        lines.pop()

    while lines and (
        _is_timestamp_line(lines[-1])
        or _is_keyword_stat(lines[-1])
        or _is_numeric_stat(lines[-1])
    ):
        lines.pop()
        while lines and not lines[-1]:
            lines.pop()

    return "\n".join(lines).strip()


def _split_image_urls(image_urls: List[str]) -> Tuple[Optional[str], List[str]]:
    avatar = None
    media: List[str] = []
    for url in image_urls:
        if avatar is None and "profile_images" in url:
            avatar = url
            continue
        media.append(url)
    return avatar, media


def _strip_media_params(url: str) -> str:
    if "pbs.twimg.com/media" not in url:
        return url
    parsed = urlparse(url)
    params = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() == "format"
    ]
    clean_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=clean_query))


def _media_markdown_lines(media_urls: List[str]) -> List[str]:
    lines: List[str] = []
    for idx, image_url in enumerate(media_urls, start=1):
        if "abs-0.twimg.com/emoji" in image_url:
            lines.append(
                f'<img src="{image_url}" alt="emoji {idx}" '
                'style="width:32px;height:auto;vertical-align:middle;" />'
            )
        else:
            clean_url = _strip_media_params(image_url)
            lines.append(f"[![image {idx}]({clean_url})]({clean_url})")
    return lines


def _extract_primary_link(article, tweet_url: str) -> str | None:
    """Devuelve el primer enlace http(s) diferente al del propio tweet."""
    seen: set[str] = set()
    tweet_lower = tweet_url.rstrip("/").lower()
    for anchor in article.locator("a").all():
        href = (
            anchor.get_attribute("data-expanded-url")
            or anchor.get_attribute("data-full-url")
            or anchor.get_attribute("href")
            or ""
        ).strip()
        if not href or not href.startswith(("http://", "https://")):
            continue
        candidate = href.rstrip("/")
        lower = candidate.lower()
        if lower == tweet_lower or lower in seen:
            continue
        if "/status/" in lower:
            # Los tweets citados se capturan aparte
            continue
        seen.add(lower)
        return candidate
    return None


def _canonical_status_url(href: str | None) -> str | None:
    if not href or "/status/" not in href:
        return None
    absolute = _absolute_url(href)
    parsed = urlparse(absolute)
    segments = [seg for seg in parsed.path.split("/") if seg]
    if len(segments) < 3 or segments[1] != "status":
        return None
    user = segments[0]
    status_id = segments[2]
    if not user or not status_id:
        return None
    return f"https://x.com/{user}/status/{status_id}"


def _extract_quote_link(article, tweet_url: str) -> str | None:
    """Devuelve el primer tweet citado si existe."""
    current = (_canonical_status_url(tweet_url) or "").rstrip("/").lower()
    for anchor in article.locator("a").all():
        canonical = _canonical_status_url(anchor.get_attribute("href"))
        if not canonical:
            continue
        if canonical.rstrip("/").lower() == current:
            continue
        return canonical
    return None


def fetch_tweet_markdown(
    url: str,
    *,
    wait_ms: int = 5000,
    headless: bool = True,
) -> tuple[str, str]:
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
        body_text = strip_tweet_stats(rebuild_urls_from_lines(raw_text).strip())

        image_urls: List[str] = []
        seen: set[str] = set()
        external_link = _extract_primary_link(article, url)
        quote_link = _extract_quote_link(article, url)
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
        avatar_url, media_urls = _split_image_urls(image_urls)

        md_lines = [f"# {title}", "", f"[Ver en X]({url})"]

        if avatar_url:
            md_lines.extend(["", f"![avatar]({avatar_url})"])
        if body_text:
            md_lines.extend(["", body_text])
        if quote_link:
            md_lines.extend(["", f"Tweet citado: {quote_link}"])
        if media_urls:
            md_lines.append("")
            md_lines.extend(_media_markdown_lines(media_urls))
            md_lines.append("")

            if external_link:
                md_lines.extend(["", f"Enlace original: {external_link}"])

        markdown = "\n".join(md_lines).strip() + "\n"
        browser.close()
        return markdown, filename


# --- Helpers de scraping de likes (adaptados de x_likes_fetcher.py) ---
def _canonical_status_url(href: str | None) -> str | None:
    if not href or "/status/" not in href:
        return None
    absolute = _absolute_url(href)
    parsed = urlparse(absolute)
    segments = [seg for seg in parsed.path.split("/") if seg]
    if len(segments) < 3 or segments[1] != "status":
        return None
    user = segments[0]
    status_id = segments[2]
    if not user or not status_id:
        return None
    return f"https://x.com/{user}/status/{status_id}"


def _absolute_url(href: str) -> str:
    if href.startswith(("http://", "https://")):
        return href
    return urljoin("https://x.com", href)


def _extract_tweet_urls(page, seen: Set[str]) -> List[str]:
    urls: List[str] = []
    for article in page.locator("article").element_handles():
        links = article.query_selector_all("a[href*='/status/']")
        article_url: str | None = None
        for link in links:
            href = link.get_attribute("href")
            canonical = _canonical_status_url(href)
            if not canonical:
                continue
            article_url = canonical
            break
        if article_url and article_url not in seen:
            seen.add(article_url)
            urls.append(article_url)
    return urls


def fetch_likes_with_state(
    state_path: Path,
    *,
    likes_url: str = DEFAULT_LIKES_URL,
    max_tweets: int = DEFAULT_MAX_TWEETS,
    headless: bool = True,
) -> Tuple[List[str], int]:
    path = state_path.expanduser()
    if not path.exists():
        raise FileNotFoundError(
            f"No se encontró el storage_state en {path}. Ejecuta utils/login_x.py para generarlo."
        )

    if sync_playwright is None:
        raise RuntimeError("Instala playwright para usar esta utilidad.")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless, channel="chrome")
        context = browser.new_context(storage_state=str(path))
        context.add_init_script(STEALTH_SNIPPET)
        page = context.new_page()

        page.goto(likes_url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_selector("article", timeout=15000)
        except PlaywrightTimeoutError:
            raise RuntimeError("No se detectaron artículos; ¿sesión caducada?")

        collected: List[str] = []
        seen: Set[str] = set()
        max_scrolls = 20
        idle_scrolls = 0

        while len(collected) < max_tweets:
            for url in _extract_tweet_urls(page, seen):
                collected.append(url)
                if len(collected) >= max_tweets:
                    break
            if len(collected) >= max_tweets:
                break

            before = page.locator("article").count()
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(1500)
            after = page.locator("article").count()
            idle_scrolls = idle_scrolls + 1 if after <= before else 0
            if idle_scrolls >= max_scrolls:
                break

        total_articles = page.locator("article").count()

        context.close()
        browser.close()
        return collected, total_articles


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Descarga los tweets marcados como Me gusta a Markdown autocontenido en un directorio."
        )
    )
    parser.add_argument(
        "--likes-url",
        default=os.environ.get("TWEET_LIKES_URL", DEFAULT_LIKES_URL),
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
        default=Path(os.environ.get("TWEET_LIKES_DEST", Path("tweets_favoritos"))),
        help="Directorio donde guardar los Markdown",
    )
    parser.add_argument(
        "--max-tweets",
        type=int,
        required=True,
        help="Número de likes a capturar en esta ejecución",
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

    if args.max_tweets <= 0:
        raise SystemExit("--max-tweets debe ser un entero positivo")

    dest_dir: Path = args.dest_dir.expanduser()
    dest_dir.mkdir(parents=True, exist_ok=True)

    urls, total_articles = fetch_likes_with_state(
        state_path,
        likes_url=likes_url,
        max_tweets=args.max_tweets,
        headless=args.headless,
    )
    print(
        f"🔍 Likes encontrados: {len(urls)} (artículos visibles: {total_articles}). "
        f"Capturando hasta {args.max_tweets} tweets solicitados."
    )

    for url in urls:
        markdown, filename = fetch_tweet_markdown(
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
