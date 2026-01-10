#!/usr/bin/env python3
"""Utilities to collect X likes using Playwright."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Set, Tuple
from urllib.parse import urljoin, urlparse

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


@dataclass(frozen=True)
class LikeTweet:
    url: str
    author_handle: str | None = None
    author_name: str | None = None
    time_text: str | None = None
    time_datetime: str | None = None


def _log(message: str) -> None:
    print(message)


def _is_status_href(href: str | None) -> bool:
    return bool(href and "/status/" in href)


def _canonical_status_url(href: str | None) -> str | None:
    """Normalize a tweet URL by dropping suffixes (/photo, /analytics...)."""
    if not href or "/status/" not in href:
        return None
    absolute = _absolute_url(href)
    parsed = urlparse(absolute)
    segments = [seg for seg in parsed.path.split("/") if seg]
    if len(segments) >= 4 and segments[0] == "i" and segments[1] == "web" and segments[2] == "status":
        status_id = segments[3]
        if not status_id:
            return None
        return f"https://x.com/i/web/status/{status_id}"
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


def _normalize_stop_url(url: str | None) -> str | None:
    if not url:
        return None
    return _canonical_status_url(url.strip())

def _should_continue(collected: Sequence[object], max_tweets: int, stop_found: bool) -> bool:
    """Scroll continuation condition: stop on limit or stop_url."""
    return len(collected) < max_tweets and not stop_found


def _extract_tweet_urls(page, seen: Set[str]) -> List[str]:
    urls: List[str] = []
    articles = page.locator("article")
    for article in articles.element_handles():
        links = article.query_selector_all("a[href*='/status/']")
        for link in links:
            href = link.get_attribute("href")
            canonical = _canonical_status_url(href)
            if not canonical:
                continue
            if canonical in seen:
                continue
            seen.add(canonical)
            urls.append(canonical)
    return urls


def _extract_like_metadata(article) -> tuple[str | None, str | None, str | None, str | None]:
    author_name = None
    author_handle = None
    for span in article.query_selector_all("span"):
        try:
            text = (span.inner_text() or "").strip()
        except Exception:
            continue
        if not text:
            continue
        if text.startswith("@") and author_handle is None:
            author_handle = text
            continue
        if author_name is None and not text.startswith("@"):
            author_name = text
    time_el = article.query_selector("time")
    time_text = None
    time_datetime = None
    if time_el:
        try:
            time_text = (time_el.inner_text() or "").strip() or None
        except Exception:
            time_text = None
        time_datetime = time_el.get_attribute("datetime")
    return author_name, author_handle, time_text, time_datetime


def _extract_like_items(page, seen: Set[str]) -> List[LikeTweet]:
    items: List[LikeTweet] = []
    articles = page.locator("article")
    for article in articles.element_handles():
        link = article.query_selector("a:has(time)")
        href = link.get_attribute("href") if link else None
        canonical = _canonical_status_url(href)
        if not canonical:
            links = article.query_selector_all("a[href*='/status/']")
            for alt in links:
                alt_href = alt.get_attribute("href")
                canonical = _canonical_status_url(alt_href)
                if canonical:
                    break
        if not canonical:
            continue
        if canonical in seen:
            continue
        seen.add(canonical)
        author_name, author_handle, time_text, time_datetime = _extract_like_metadata(article)
        items.append(
            LikeTweet(
                url=canonical,
                author_handle=author_handle,
                author_name=author_name,
                time_text=time_text,
                time_datetime=time_datetime,
            )
        )
    return items


def collect_likes_from_page(
    page,
    likes_url: str,
    max_tweets: int = DEFAULT_MAX_TWEETS,
    stop_at_url: str | None = None,
) -> Tuple[bool, int, List[str], bool, str | None]:
    """Copy of the logic used by interactive scripts to extract likes."""
    _log(f"▶️  Trying to load {likes_url}…")
    page.goto(likes_url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector("article", timeout=15000)
    except PlaywrightTimeoutError:
        _log("   ⚠️  No articles detected; the session may not be active.")
        return False, 0, [], False, _normalize_stop_url(stop_at_url)

    collected: List[str] = []
    seen: Set[str] = set()
    max_scrolls = 20
    idle_scrolls = 0
    stop_absolute = _normalize_stop_url(stop_at_url)
    stop_found = False
    articles = page.locator("article")

    while _should_continue(collected, max_tweets, stop_found):
        for url in _extract_tweet_urls(page, seen):
            collected.append(url)
            if stop_absolute and url == stop_absolute:
                stop_found = True
                break
            if not _should_continue(collected, max_tweets, stop_found):
                break
        if not _should_continue(collected, max_tweets, stop_found):
            break

        before_articles = articles.count()
        page.mouse.wheel(0, 2000)
        page.wait_for_timeout(1500)
        after_articles = articles.count()
        if after_articles <= before_articles:
            idle_scrolls += 1
            if idle_scrolls >= max_scrolls:
                break
        else:
            idle_scrolls = 0

    total_articles = articles.count()
    summary = (
        f"   ✅ Likes loaded successfully. Visible articles: {total_articles}. "
        f"URLs collected: {len(collected)} (limit: {max_tweets})"
    )
    if stop_absolute:
        summary += f". Stop URL {'found' if stop_found else 'not found'}."
    _log(summary)

    if collected:
        _log("   🔗 URLs detected:")
        for idx, url in enumerate(collected, 1):
            _log(f"      {idx}. {url}")

    return True, total_articles, collected, stop_found, stop_absolute


def collect_like_items_from_page(
    page,
    likes_url: str,
    max_tweets: int = DEFAULT_MAX_TWEETS,
    stop_at_url: str | None = None,
) -> Tuple[bool, int, List[LikeTweet], bool, str | None]:
    """Load likes and return the liked tweets with metadata."""
    _log(f"▶️  Trying to load {likes_url}…")
    page.goto(likes_url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector("article", timeout=15000)
    except PlaywrightTimeoutError:
        _log("   ⚠️  No articles detected; the session may not be active.")
        return False, 0, [], False, _normalize_stop_url(stop_at_url)

    collected: List[LikeTweet] = []
    seen: Set[str] = set()
    max_scrolls = 20
    idle_scrolls = 0
    stop_absolute = _normalize_stop_url(stop_at_url)
    stop_found = False
    articles = page.locator("article")

    while _should_continue(collected, max_tweets, stop_found):
        for item in _extract_like_items(page, seen):
            collected.append(item)
            if stop_absolute and item.url == stop_absolute:
                stop_found = True
                break
            if not _should_continue(collected, max_tweets, stop_found):
                break
        if not _should_continue(collected, max_tweets, stop_found):
            break

        before_articles = articles.count()
        page.mouse.wheel(0, 2000)
        page.wait_for_timeout(1500)
        after_articles = articles.count()
        if after_articles <= before_articles:
            idle_scrolls += 1
            if idle_scrolls >= max_scrolls:
                break
        else:
            idle_scrolls = 0

    total_articles = articles.count()
    summary = (
        f"   ✅ Likes loaded successfully. Visible articles: {total_articles}. "
        f"URLs collected: {len(collected)} (limit: {max_tweets})"
    )
    if stop_absolute:
        summary += f". Stop URL {'found' if stop_found else 'not found'}."
    _log(summary)

    if collected:
        _log("   🔗 URLs detected:")
        for idx, item in enumerate(collected, 1):
            _log(f"      {idx}. {item.url}")

    return True, total_articles, collected, stop_found, stop_absolute


def fetch_likes_with_state(
    state_path: Path,
    *,
    likes_url: str = DEFAULT_LIKES_URL,
    max_tweets: int = DEFAULT_MAX_TWEETS,
    stop_at_url: str | None = None,
    headless: bool = True,
) -> Tuple[List[str], bool, int]:
    """Load likes with an existing storage_state and return (urls, stop_found, total_articles)."""
    path = state_path.expanduser()
    if not path.exists():
        raise FileNotFoundError(
            f"storage_state not found at {path}. Run utils/create_x_state.py to generate it."
        )

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=headless, channel="chrome")
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to launch Chrome in headless mode: {exc}") from exc

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
                raise RuntimeError("Could not retrieve articles on the likes page.")
            if stop_found and stop_absolute and stop_absolute in urls:
                idx = urls.index(stop_absolute)
                urls = urls[:idx]
            return urls, stop_found, total
        finally:
            context.close()
            browser.close()


def fetch_like_items_with_state(
    state_path: Path,
    *,
    likes_url: str = DEFAULT_LIKES_URL,
    max_tweets: int = DEFAULT_MAX_TWEETS,
    stop_at_url: str | None = None,
    headless: bool = True,
) -> Tuple[List[LikeTweet], bool, int]:
    """Load likes and return items with metadata (author + relative time)."""
    path = state_path.expanduser()
    if not path.exists():
        raise FileNotFoundError(
            f"storage_state not found at {path}. Run utils/create_x_state.py to generate it."
        )

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=headless, channel="chrome")
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to launch Chrome in headless mode: {exc}") from exc

        context = browser.new_context(storage_state=str(path))
        context.add_init_script(STEALTH_SNIPPET)
        page = context.new_page()
        try:
            success, total, items, stop_found, stop_absolute = collect_like_items_from_page(
                page,
                likes_url=likes_url,
                max_tweets=max_tweets,
                stop_at_url=stop_at_url,
            )
            if not success:
                raise RuntimeError("Could not retrieve articles on the likes page.")
            if stop_found and stop_absolute:
                for idx, item in enumerate(items):
                    if item.url == stop_absolute:
                        items = items[:idx]
                        break
            return items, stop_found, total
        finally:
            context.close()
            browser.close()
