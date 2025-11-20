#!/usr/bin/env python3
"""Utilidades para recopilar likes de X usando Playwright."""
from __future__ import annotations

from pathlib import Path
from typing import List, Set, Tuple
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

DEFAULT_LIKES_URL = "https://x.com/domingogallardo/likes"
DEFAULT_MAX_TWEETS = 100
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


def _log(message: str) -> None:
    print(message)


def _is_status_href(href: str | None) -> bool:
    return bool(href and "/status/" in href)


def _absolute_url(href: str) -> str:
    if href.startswith(("http://", "https://")):
        return href
    return urljoin("https://x.com", href)


def _normalize_stop_url(url: str | None) -> str | None:
    if not url:
        return None
    return _absolute_url(url.strip())


def _extract_tweet_urls(page, seen: Set[str]) -> List[str]:
    urls: List[str] = []
    for article in page.locator("article").element_handles():
        links = article.query_selector_all("a[href*='/status/']")
        for link in links:
            href = link.get_attribute("href")
            if not _is_status_href(href):
                continue
            absolute = _absolute_url(href)
            if absolute in seen:
                continue
            seen.add(absolute)
            urls.append(absolute)
    return urls


def collect_likes_from_page(
    page,
    likes_url: str,
    max_tweets: int = DEFAULT_MAX_TWEETS,
    stop_at_url: str | None = None,
) -> Tuple[bool, int, List[str], bool, str | None]:
    """Copia de la lógica usada por los scripts interactivos para extraer likes."""
    _log(f"▶️  Intentando cargar {likes_url}…")
    page.goto(likes_url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector("article", timeout=15000)
    except PlaywrightTimeoutError:
        _log("   ⚠️  No se detectaron artículos; puede que la sesión no esté activa.")
        return False, 0, [], False, _normalize_stop_url(stop_at_url)

    collected: List[str] = []
    seen: Set[str] = set()
    max_scrolls = 20
    idle_scrolls = 0
    stop_absolute = _normalize_stop_url(stop_at_url)
    stop_found = False

    while len(collected) < max_tweets and not stop_found:
        for url in _extract_tweet_urls(page, seen):
            collected.append(url)
            if stop_absolute and url == stop_absolute:
                stop_found = True
                break
            if len(collected) >= max_tweets:
                break
        if len(collected) >= max_tweets or stop_found:
            break

        before_articles = page.locator("article").count()
        page.mouse.wheel(0, 2000)
        page.wait_for_timeout(1500)
        after_articles = page.locator("article").count()
        if after_articles <= before_articles:
            idle_scrolls += 1
            if idle_scrolls >= max_scrolls:
                break
        else:
            idle_scrolls = 0

    total_articles = page.locator("article").count()
    summary = (
        f"   ✅ Likes cargados correctamente. Artículos visibles: {total_articles}. "
        f"URLs recopiladas: {len(collected)} (límite: {max_tweets})"
    )
    if stop_absolute:
        summary += f". Stop URL {'encontrada' if stop_found else 'no encontrada'}."
    _log(summary)

    if collected:
        _log("   🔗 URLs detectadas:")
        for idx, url in enumerate(collected, 1):
            _log(f"      {idx}. {url}")

    return True, total_articles, collected, stop_found, stop_absolute


def fetch_likes_with_state(
    state_path: Path,
    *,
    likes_url: str = DEFAULT_LIKES_URL,
    max_tweets: int = DEFAULT_MAX_TWEETS,
    stop_at_url: str | None = None,
    headless: bool = True,
) -> Tuple[List[str], bool, int]:
    """Carga los likes con un storage_state existente y devuelve (urls, stop_encontrada, total_artículos)."""
    path = state_path.expanduser()
    if not path.exists():
        raise FileNotFoundError(
            f"No se encontró el storage_state en {path}. Ejecuta utils/login_x.py para generarlo."
        )

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=headless, channel="chrome")
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(f"No se pudo lanzar Chrome en modo headless: {exc}") from exc

        context = browser.new_context(storage_state=str(path))
        context.add_init_script(STEALTH_SNIPPET)
        page = context.new_page()
        try:
            success, total, urls, stop_found, stop_absolute = collect_likes_from_page(
                page,
                likes_url=likes_url,
                max_tweets=max_tweets,
                stop_at_url=stop_at_url,
            )
            if not success:
                raise RuntimeError("No se pudieron obtener artículos en la página de likes.")
            if stop_found and stop_absolute and stop_absolute in urls:
                idx = urls.index(stop_absolute)
                urls = urls[:idx]
            return urls, stop_found, total
        finally:
            context.close()
            browser.close()
