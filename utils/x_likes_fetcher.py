#!/usr/bin/env python3
"""Utilities to collect X timeline tweets using Playwright."""
from __future__ import annotations

import re
import unicodedata
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Set, Tuple
from urllib.parse import urljoin, urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

DEFAULT_LIKES_URL = "https://x.com/domingogallardo/likes"
DEFAULT_MAX_TWEETS = 100
LOGIN_WALL_HINTS = (
    "/i/flow/login",
    "/login",
    "/i/flow/signup",
    "/account/access",
)
PINNED_BADGES = {"pinned", "fijado"}
REPOST_CONTEXT_TERMS = (
    "reposted",
    "retweeted",
    "reposteo",
    "republico",
    "retuiteo",
    "retwitteo",
    "reposteaste",
    "republicaste",
    "retuiteaste",
    "retwitteaste",
    "retuiteado",
    "retwitteado",
    "republicado",
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


@dataclass(frozen=True)
class TimelineTweet:
    url: str
    author_handle: str | None = None
    author_name: str | None = None
    time_text: str | None = None
    time_datetime: str | None = None
    posted_kind: str | None = None
    reply_to_url: str | None = None


LikeTweet = TimelineTweet


def _log(message: str) -> None:
    print(message)


def _normalize_handle(handle: str | None) -> str | None:
    if not handle:
        return None
    cleaned = handle.strip().strip("/")
    if not cleaned:
        return None
    if cleaned.startswith("@"):
        cleaned = cleaned[1:]
    cleaned = cleaned.strip()
    if not cleaned:
        return None
    return f"@{cleaned.lower()}"


def _normalize_text_for_match(text: str | None) -> str:
    if not text:
        return ""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip().lower()


def _looks_like_repost_context(text: str | None) -> bool:
    normalized = _normalize_text_for_match(text)
    return any(term in normalized for term in REPOST_CONTEXT_TERMS)


def _wait_for_timeline_articles(page, *, timeline_url: str, retries: int = 1) -> bool:
    for attempt in range(retries + 1):
        try:
            page.wait_for_selector("article", timeout=15000)
            return True
        except PlaywrightTimeoutError:
            current_url = page.url or ""
            if any(hint in current_url for hint in LOGIN_WALL_HINTS):
                _log("   ⚠️  Login wall detected; the session may be expired.")
                return False
            if attempt < retries:
                _log("   🔁 No articles yet; retrying timeline page load...")
                with suppress(Exception):
                    page.goto(timeline_url, wait_until="domcontentloaded", timeout=60000)
                continue
            _log("   ⚠️  No articles detected; the session may not be active.")
            return False
    return False


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


def _handle_from_status_url(url: str | None) -> str | None:
    canonical = _canonical_status_url(url)
    if not canonical:
        return None
    parsed = urlparse(canonical)
    segments = [seg for seg in parsed.path.split("/") if seg]
    if len(segments) >= 4 and segments[0] == "i" and segments[1] == "web":
        return None
    if len(segments) < 3:
        return None
    return _normalize_handle(segments[0])


def _expected_handle_from_timeline_url(timeline_url: str | None) -> str | None:
    if not timeline_url:
        return None
    parsed = urlparse(_absolute_url(timeline_url))
    segments = [seg for seg in parsed.path.split("/") if seg]
    if not segments:
        return None
    if segments[0] == "i":
        return None
    return _normalize_handle(segments[0])


def _should_continue(collected: Sequence[object], max_tweets: int, stop_found: bool) -> bool:
    """Scroll continuation condition: stop on limit or stop_url."""
    return len(collected) < max_tweets and not stop_found


def _extract_tweet_metadata(article) -> tuple[str | None, str | None, str | None, str | None]:
    author_name = None
    author_handle = None
    for span in article.query_selector_all("span"):
        try:
            text = (span.inner_text() or "").strip()
        except Exception:
            continue
        if not text:
            continue
        if _looks_like_repost_context(text):
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


def _is_pinned_article(article) -> bool:
    for span in article.query_selector_all("span"):
        try:
            text = (span.inner_text() or "").strip().lower()
        except Exception:
            continue
        if text in PINNED_BADGES:
            return True
    return False


def _matches_expected_author(
    canonical_url: str,
    author_handle: str | None,
    expected_author_handle: str | None,
) -> bool:
    expected = _normalize_handle(expected_author_handle)
    if not expected:
        return True
    url_handle = _handle_from_status_url(canonical_url)
    article_handle = _normalize_handle(author_handle)
    if url_handle == expected:
        return True
    return article_handle == expected


def _profile_handle_from_href(href: str | None) -> str | None:
    if not href:
        return None
    absolute = _absolute_url(href)
    parsed = urlparse(absolute)
    segments = [seg for seg in parsed.path.split("/") if seg]
    if not segments or segments[0] in {"i", "search", "hashtag"}:
        return None
    if len(segments) > 1 and segments[1] == "status":
        return None
    return _normalize_handle(segments[0])


def _links_to_expected_handle(element, expected_author_handle: str | None) -> bool | None:
    expected = _normalize_handle(expected_author_handle)
    if not expected:
        return None
    profile_handles: List[str] = []
    try:
        links = element.query_selector_all("a[href]")
    except Exception:
        return None
    for link in links:
        try:
            handle = _profile_handle_from_href(link.get_attribute("href"))
        except Exception:
            continue
        if handle:
            profile_handles.append(handle)
    if not profile_handles:
        return None
    return expected in profile_handles


def _article_reposted_by_expected_author(article, expected_author_handle: str | None) -> bool:
    if not _normalize_handle(expected_author_handle):
        return False

    try:
        social_contexts = article.query_selector_all("[data-testid='socialContext']")
    except Exception:
        social_contexts = []
    for context in social_contexts:
        try:
            text = (context.inner_text() or "").strip()
        except Exception:
            continue
        if not _looks_like_repost_context(text):
            continue
        expected_link_match = _links_to_expected_handle(context, expected_author_handle)
        if expected_link_match is False:
            continue
        return True

    if social_contexts:
        return False

    try:
        spans = article.query_selector_all("span")
    except Exception:
        return False
    for span in spans:
        try:
            text = (span.inner_text() or "").strip()
        except Exception:
            continue
        if text.startswith("@"):
            break
        if _looks_like_repost_context(text):
            return True
    return False


def _extract_timeline_items(
    page,
    seen: Set[str],
    *,
    expected_author_handle: str | None = None,
    exclude_pinned: bool = False,
    include_reposts: bool = False,
) -> List[TimelineTweet]:
    items: List[TimelineTweet] = []
    articles = page.locator("article")
    for article in articles.element_handles():
        if exclude_pinned and _is_pinned_article(article):
            continue

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

        author_name, author_handle, time_text, time_datetime = _extract_tweet_metadata(article)
        matches_author = _matches_expected_author(canonical, author_handle, expected_author_handle)
        matches_repost = include_reposts and _article_reposted_by_expected_author(
            article,
            expected_author_handle,
        )
        if not (matches_author or matches_repost):
            continue
        if canonical in seen:
            continue
        seen.add(canonical)
        posted_kind = None
        if expected_author_handle:
            posted_kind = "repost" if matches_repost else "post"
        items.append(
            TimelineTweet(
                url=canonical,
                author_handle=author_handle,
                author_name=author_name,
                time_text=time_text,
                time_datetime=time_datetime,
                posted_kind=posted_kind,
            )
        )
    return items


def _iter_tweet_results(payload: object):
    if isinstance(payload, dict):
        if payload.get("__typename") == "Tweet" and payload.get("rest_id"):
            yield payload
        for value in payload.values():
            yield from _iter_tweet_results(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _iter_tweet_results(item)


def _tweet_user_core(tweet_result: dict) -> dict:
    user = tweet_result.get("core", {}).get("user_results", {}).get("result", {})
    if not isinstance(user, dict):
        return {}
    core = user.get("core") or {}
    return core if isinstance(core, dict) else {}


def _reply_parent_url_from_legacy(legacy: dict) -> str | None:
    parent_id = legacy.get("in_reply_to_status_id_str") or legacy.get("in_reply_to_status_id")
    if not parent_id:
        return None
    parent_id = str(parent_id)
    parent_screen_name = legacy.get("in_reply_to_screen_name")
    if parent_screen_name:
        return f"https://x.com/{parent_screen_name}/status/{parent_id}"
    return f"https://x.com/i/web/status/{parent_id}"


def _reply_items_from_payload(
    payload: object,
    *,
    expected_author_handle: str,
) -> List[TimelineTweet]:
    expected = _normalize_handle(expected_author_handle)
    if not expected:
        return []

    items: List[TimelineTweet] = []
    seen: set[str] = set()
    for tweet in _iter_tweet_results(payload):
        if not isinstance(tweet, dict):
            continue
        user_core = _tweet_user_core(tweet)
        screen_name = user_core.get("screen_name")
        if not screen_name or _normalize_handle(str(screen_name)) != expected:
            continue

        legacy = tweet.get("legacy") or {}
        if not isinstance(legacy, dict):
            continue
        reply_to_url = _reply_parent_url_from_legacy(legacy)
        if not reply_to_url:
            continue

        rest_id = tweet.get("rest_id")
        if not rest_id:
            continue
        url = f"https://x.com/{screen_name}/status/{rest_id}"
        if url in seen:
            continue
        seen.add(url)
        items.append(
            TimelineTweet(
                url=url,
                author_handle=f"@{screen_name}",
                author_name=user_core.get("name"),
                posted_kind="reply",
                reply_to_url=reply_to_url,
            )
        )
    return items


def _merge_timeline_items(existing: List[TimelineTweet], fresh: Sequence[TimelineTweet]) -> List[TimelineTweet]:
    seen = {item.url for item in existing}
    for item in fresh:
        if item.url in seen:
            continue
        seen.add(item.url)
        existing.append(item)
    return existing


def collect_reply_items_from_page(
    page,
    replies_url: str,
    *,
    expected_author_handle: str,
    max_tweets: int = DEFAULT_MAX_TWEETS,
    stop_at_url: str | None = None,
) -> Tuple[bool, int, List[TimelineTweet], bool, str | None]:
    """Load a with_replies timeline and return only replies by the expected author."""
    payloads: List[object] = []

    def handle_response(response) -> None:
        if "UserTweetsAndReplies" not in response.url:
            return
        try:
            payloads.append(response.json())
        except Exception:
            return

    page.on("response", handle_response)
    _log(f"▶️  Trying to load {replies_url}…")
    page.goto(replies_url, wait_until="domcontentloaded", timeout=60000)
    if not _wait_for_timeline_articles(page, timeline_url=replies_url):
        return False, 0, [], False, _normalize_stop_url(stop_at_url)

    collected: List[TimelineTweet] = []
    stop_absolute = _normalize_stop_url(stop_at_url)
    stop_found = False
    articles = page.locator("article")
    max_scrolls = 20
    idle_scrolls = 0
    parsed_payload_count = 0

    while _should_continue(collected, max_tweets, stop_found):
        while parsed_payload_count < len(payloads):
            payload = payloads[parsed_payload_count]
            parsed_payload_count += 1
            before = len(collected)
            _merge_timeline_items(
                collected,
                _reply_items_from_payload(payload, expected_author_handle=expected_author_handle),
            )
            if len(collected) == before:
                continue
            if stop_absolute:
                for idx, item in enumerate(collected):
                    if item.url == stop_absolute:
                        collected = collected[:idx]
                        stop_found = True
                        break
            if len(collected) > max_tweets:
                collected = collected[:max_tweets]
            if not _should_continue(collected, max_tweets, stop_found):
                break
        if not _should_continue(collected, max_tweets, stop_found):
            break

        before_articles = articles.count()
        page.mouse.wheel(0, 2000)
        page.wait_for_timeout(1500)
        after_articles = articles.count()
        if after_articles <= before_articles and parsed_payload_count >= len(payloads):
            idle_scrolls += 1
            if idle_scrolls >= max_scrolls:
                break
        else:
            idle_scrolls = 0

    total_articles = articles.count()
    summary = (
        f"   ✅ Replies loaded successfully. Visible articles: {total_articles}. "
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


def collect_timeline_items_from_page(
    page,
    timeline_url: str,
    *,
    max_tweets: int = DEFAULT_MAX_TWEETS,
    stop_at_url: str | None = None,
    expected_author_handle: str | None = None,
    exclude_pinned: bool = False,
    include_reposts: bool = False,
    timeline_label: str = "Timeline",
) -> Tuple[bool, int, List[TimelineTweet], bool, str | None]:
    """Load a timeline and return tweets with metadata."""
    _log(f"▶️  Trying to load {timeline_url}…")
    page.goto(timeline_url, wait_until="domcontentloaded", timeout=60000)
    if not _wait_for_timeline_articles(page, timeline_url=timeline_url):
        return False, 0, [], False, _normalize_stop_url(stop_at_url)

    collected: List[TimelineTweet] = []
    seen: Set[str] = set()
    max_scrolls = 20
    idle_scrolls = 0
    stop_absolute = _normalize_stop_url(stop_at_url)
    stop_found = False
    articles = page.locator("article")

    while _should_continue(collected, max_tweets, stop_found):
        for item in _extract_timeline_items(
            page,
            seen,
            expected_author_handle=expected_author_handle,
            exclude_pinned=exclude_pinned,
            include_reposts=include_reposts,
        ):
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
        f"   ✅ {timeline_label} loaded successfully. Visible articles: {total_articles}. "
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


def fetch_timeline_items_with_state(
    state_path: Path,
    *,
    timeline_url: str,
    max_tweets: int = DEFAULT_MAX_TWEETS,
    stop_at_url: str | None = None,
    headless: bool = True,
    expected_author_handle: str | None = None,
    exclude_pinned: bool = False,
    include_reposts: bool = False,
    timeline_label: str = "Timeline",
) -> Tuple[List[TimelineTweet], bool, int]:
    """Load a timeline and return tweets with metadata (author + relative time)."""
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
            success, total, items, stop_found, stop_absolute = collect_timeline_items_from_page(
                page,
                timeline_url,
                max_tweets=max_tweets,
                stop_at_url=stop_at_url,
                expected_author_handle=expected_author_handle,
                exclude_pinned=exclude_pinned,
                include_reposts=include_reposts,
                timeline_label=timeline_label,
            )
            if not success:
                raise RuntimeError("Could not retrieve articles on the timeline page.")
            if stop_found and stop_absolute:
                for idx, item in enumerate(items):
                    if item.url == stop_absolute:
                        items = items[:idx]
                        break
            return items, stop_found, total
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
    return fetch_timeline_items_with_state(
        state_path,
        timeline_url=likes_url,
        max_tweets=max_tweets,
        stop_at_url=stop_at_url,
        headless=headless,
        timeline_label="Likes",
    )


def fetch_post_items_with_state(
    state_path: Path,
    *,
    posts_url: str,
    max_tweets: int = DEFAULT_MAX_TWEETS,
    stop_at_url: str | None = None,
    headless: bool = True,
    expected_author_handle: str | None = None,
) -> Tuple[List[TimelineTweet], bool, int]:
    """Load a user timeline and return that author's published and reposted tweets."""
    expected = _normalize_handle(expected_author_handle) or _expected_handle_from_timeline_url(posts_url)
    if not expected:
        raise RuntimeError(
            "Could not determine the author handle for TWEET_POSTS_URL. "
            "Use a profile URL like https://x.com/<user>."
        )
    return fetch_timeline_items_with_state(
        state_path,
        timeline_url=posts_url,
        max_tweets=max_tweets,
        stop_at_url=stop_at_url,
        headless=headless,
        expected_author_handle=expected,
        exclude_pinned=True,
        include_reposts=True,
        timeline_label="Posts",
    )


def fetch_reply_items_with_state(
    state_path: Path,
    *,
    replies_url: str,
    max_tweets: int = DEFAULT_MAX_TWEETS,
    stop_at_url: str | None = None,
    headless: bool = True,
    expected_author_handle: str | None = None,
) -> Tuple[List[TimelineTweet], bool, int]:
    """Load a user's with_replies timeline and return that author's replies."""
    expected = _normalize_handle(expected_author_handle) or _expected_handle_from_timeline_url(replies_url)
    if not expected:
        raise RuntimeError(
            "Could not determine the author handle for TWEET_REPLIES_URL. "
            "Use a profile URL like https://x.com/<user>/with_replies."
        )

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
            success, total, items, stop_found, _ = collect_reply_items_from_page(
                page,
                replies_url,
                expected_author_handle=expected,
                max_tweets=max_tweets,
                stop_at_url=stop_at_url,
            )
            if not success:
                raise RuntimeError("Could not retrieve articles on the replies page.")
            return items, stop_found, total
        finally:
            context.close()
            browser.close()
