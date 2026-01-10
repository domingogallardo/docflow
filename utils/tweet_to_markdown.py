#!/usr/bin/env python3
"""Convert a public tweet into a self-contained Markdown file."""
from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, parse_qsl, urlencode, urljoin, urlunparse
from typing import List, Optional, Tuple

try:  # pragma: no cover - optional import
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
except ImportError:  # pragma: no cover - environment without Playwright
    PlaywrightTimeoutError = RuntimeError  # type: ignore[misc,assignment]
    sync_playwright = None  # type: ignore[assignment]

import config as cfg

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
QUOTE_MARKERS = {"quote"}
QUOTE_MARKERS_JS = ", ".join(f'"{m}"' for m in sorted(QUOTE_MARKERS))
THREAD_MAX_MINUTES = 24 * 60
THREAD_MARKER_RE = re.compile(r"\bthread\b|\bhilo\b", re.IGNORECASE)
WAIT_MS = 1000
TWEET_DETAIL_WAIT_MS = 5000


@dataclass(frozen=True)
class TweetParts:
    author_name: str | None
    author_handle: str | None
    body_text: str
    avatar_url: str | None
    trailing_media_lines: List[str]
    media_present: bool
    external_link: str | None


def rebuild_urls_from_lines(text: str) -> str:
    """Rebuild URLs that X splits with line breaks and ellipses."""
    lines = text.splitlines()
    out: List[str] = []
    building_url = False

    for original_line in lines:
        stripped = original_line.strip()

        if stripped.startswith(("https://", "http://")):
            if "…" in stripped:
                before, _, after = stripped.partition("…")
                if before:
                    out.append(before)
                building_url = False
                remainder = after.lstrip()
                if remainder:
                    out.append(remainder)
            else:
                out.append(stripped)
                building_url = True
            continue

        if building_url:
            if not stripped or stripped.endswith(":"):
                out.append(original_line)
                building_url = False
                continue
            if "…" in stripped:
                before, _, after = stripped.partition("…")
                if before:
                    out[-1] = out[-1] + before
                building_url = False
                remainder = after.lstrip()
                if remainder:
                    out.append(remainder)
                continue
            out[-1] = out[-1] + stripped
        else:
            if stripped == "…":
                continue
            if stripped.startswith("…"):
                remainder = stripped.lstrip("…").lstrip()
                if remainder:
                    out.append(remainder)
                continue
            out.append(original_line)

    return "\n".join(out)


def _safe_filename(name: str) -> str:
    cleaned = "".join(ch for ch in name if ch not in '<>:"/\\|?*#').strip()
    cleaned = " ".join(cleaned.split())
    return cleaned[:200] or "Tweet"


def _build_title(author_name: str | None, author_handle: str | None, *, kind: str = "Tweet") -> str:
    base = kind
    if author_name or author_handle:
        base += " by "
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


def _format_wait_ms(wait_ms: int) -> str:
    seconds = wait_ms / 1000
    label = f"{seconds:.1f}".rstrip("0").rstrip(".")
    return f"{label}s"


def _wait_with_log(page, wait_ms: int, reason: str) -> None:
    if wait_ms <= 0:
        return
    print(f"⏳ Esperando {_format_wait_ms(wait_ms)} para {reason}...")
    page.wait_for_timeout(wait_ms)


def _wait_for_tweet_detail(page, timeout_ms: int) -> object | None:
    if timeout_ms <= 0:
        return None
    try:
        response = page.wait_for_response(
            lambda resp: "TweetDetail" in resp.url,
            timeout=timeout_ms,
        )
    except PlaywrightTimeoutError:
        return None
    try:
        return response.json()
    except Exception:
        return None


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _minutes_since(entry_time: str | None, anchor_time: str | None) -> float | None:
    entry_dt = _parse_iso_datetime(entry_time)
    anchor_dt = _parse_iso_datetime(anchor_time)
    if not entry_dt or not anchor_dt:
        return None
    return (anchor_dt - entry_dt).total_seconds() / 60


def _parse_twitter_created_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _minutes_between(entry_time: datetime | None, anchor_time: datetime | None) -> float | None:
    if not entry_time or not anchor_time:
        return None
    return (anchor_time - entry_time).total_seconds() / 60


def _extract_author_details(article) -> tuple[str | None, str | None]:
    author_name = None
    author_handle = None
    for txt in article.locator("span").all_text_contents():
        text = txt.strip()
        if not text:
            continue
        if text.startswith("@") and author_handle is None:
            author_handle = text
            continue
        if author_name is None and not text.startswith("@"):
            author_name = text
    return author_name, author_handle


def _extract_time_details(article) -> tuple[str | None, str | None]:
    time_el = article.locator("time").first
    if time_el.count() == 0:
        return None, None
    try:
        time_text = time_el.inner_text().strip()
    except Exception:
        time_text = ""
    time_datetime = time_el.get_attribute("datetime")
    return (time_text or None), time_datetime


def _extract_article_status_url(article, author_handle: str | None) -> str | None:
    hrefs = [
        anchor.get_attribute("href") or ""
        for anchor in article.locator("a[href*='/status/']").all()
    ]
    candidates = []
    for href in hrefs:
        canonical = _canonical_status_url(href)
        if canonical:
            candidates.append(canonical)
    if not candidates:
        return None
    if author_handle:
        handle = author_handle.lstrip("@")
        for candidate in candidates:
            if f"/{handle}/status/" in candidate:
                return candidate
    return candidates[0]


def _has_thread_marker(article) -> bool:
    try:
        link_texts = article.locator("a").all_text_contents()
    except Exception:
        return False
    for text in link_texts:
        if THREAD_MARKER_RE.search(text or ""):
            return True
    return False


def _select_thread_indices(
    entries: List[tuple[str | None, str | None, str | None]],
    target_idx: int | None,
    *,
    author_handle: str | None,
    time_text: str | None,
    anchor_time_datetime: str | None,
) -> List[int]:
    if target_idx is None or target_idx < 0 or target_idx >= len(entries):
        return []
    if not author_handle:
        return [target_idx]
    indices = [target_idx]
    idx = target_idx - 1
    while idx >= 0:
        handle, entry_time, entry_datetime = entries[idx]
        if handle != author_handle:
            break
        minutes = _minutes_since(entry_datetime, anchor_time_datetime)
        if minutes is not None:
            if 0 <= minutes <= THREAD_MAX_MINUTES:
                indices.append(idx)
                idx -= 1
                continue
            break
        if time_text and entry_time == time_text:
            indices.append(idx)
            idx -= 1
            continue
        break
    return sorted(indices)


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


def strip_tweet_stats(text: str) -> str:
    """Remove trailing blocks with metrics (views, likes, time, etc.)."""
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


def _insert_quote_separator(text: str, quoted_url: str | None = None) -> str:
    """Insert a Markdown horizontal rule before quote markers."""
    lines = text.splitlines()
    out: List[str] = []
    inserted_link = False

    for line in lines:
        stripped = line.strip()
        if stripped.lower() in QUOTE_MARKERS:
            if not out or out[-1].strip() != "---":
                if out and out[-1].strip():
                    out.append("")
                out.append("---")
            if quoted_url and not inserted_link:
                out.append(f"[View quoted tweet]({quoted_url})")
                inserted_link = True
            out.append(line)
            continue
        out.append(line)

    return "\n".join(out)


def _insert_media_before_quote(text: str, media_lines: List[str]) -> str:
    if not media_lines:
        return text
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if line.strip().lower() in QUOTE_MARKERS:
            insert_at = idx
            for j in range(idx - 1, -1, -1):
                if lines[j].strip() == "---":
                    insert_at = j
                    break
            block: List[str] = []
            if insert_at > 0 and lines[insert_at - 1].strip():
                block.append("")
            block.extend(media_lines)
            block.append("")
            lines = lines[:insert_at] + block + lines[insert_at:]
            return "\n".join(lines)
    return text


def _is_after_quote_marker(img, root) -> bool:
    if root is None:
        return False
    try:
        return bool(
            img.evaluate(
                f"""
                (el, root) => {{
                    const markers = new Set([{QUOTE_MARKERS_JS}]);
                    const walker = document.createTreeWalker(
                        root,
                        NodeFilter.SHOW_TEXT
                    );
                    let quoteEl = null;
                    while (walker.nextNode()) {{
                        const value = walker.currentNode.nodeValue || "";
                        const text = value.trim().toLowerCase();
                        if (markers.has(text)) {{
                            quoteEl = walker.currentNode.parentElement;
                            break;
                        }}
                    }}
                    if (!quoteEl) return false;
                    const pos = el.compareDocumentPosition(quoteEl);
                    return !!(pos & Node.DOCUMENT_POSITION_PRECEDING);
                }}
                """,
                root,
            )
        )
    except Exception:
        return False

def _canonical_status_url(href: str | None) -> str | None:
    """Normalize a tweet URL by dropping suffixes (/photo, /analytics...)."""
    if not href or "/status/" not in href:
        return None
    absolute = href
    if not href.startswith(("http://", "https://")):
        absolute = urljoin("https://x.com", href)
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


def _status_id_from_url(url: str | None) -> str | None:
    if not url or "/status/" not in url:
        return None
    parsed = urlparse(url)
    segments = [seg for seg in parsed.path.split("/") if seg]
    if len(segments) >= 4 and segments[0] == "i" and segments[1] == "web" and segments[2] == "status":
        return segments[3] or None
    if len(segments) >= 3 and segments[1] == "status":
        return segments[2] or None
    return None


def _find_rest_id(payload: object) -> str | None:
    if isinstance(payload, dict):
        if "rest_id" in payload and payload["rest_id"]:
            return str(payload["rest_id"])
        for value in payload.values():
            found = _find_rest_id(value)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_rest_id(item)
            if found:
                return found
    return None


def _find_quoted_status_id(payload: object) -> str | None:
    if isinstance(payload, dict):
        if payload.get("quoted_status_id_str"):
            return str(payload["quoted_status_id_str"])
        if payload.get("quoted_status_id"):
            return str(payload["quoted_status_id"])
        if "quoted_status_result" in payload:
            found = _find_rest_id(payload["quoted_status_result"])
            if found:
                return found
        for value in payload.values():
            found = _find_quoted_status_id(value)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_quoted_status_id(item)
            if found:
                return found
    return None


def _quoted_url_from_graphql_id(quoted_id: str | None, tweet_url: str) -> str | None:
    if not quoted_id:
        return None
    tweet_id = _status_id_from_url(tweet_url)
    if tweet_id and quoted_id == tweet_id:
        return None
    return f"https://x.com/i/web/status/{quoted_id}"


def _pick_quoted_tweet_url(hrefs: List[str], tweet_url: str) -> str | None:
    tweet_canonical = _canonical_status_url(tweet_url) or tweet_url.rstrip("/")
    seen = {tweet_canonical.lower()}
    for href in hrefs:
        canonical = _canonical_status_url(href)
        if not canonical:
            continue
        lower = canonical.lower()
        if lower in seen:
            continue
        return canonical
    return None


def _extract_quoted_tweet_url(article, tweet_url: str) -> str | None:
    hrefs = [
        anchor.get_attribute("href") or ""
        for anchor in article.locator("a[href*='/status/']").all()
    ]
    return _pick_quoted_tweet_url(hrefs, tweet_url)


def _has_quote_marker(text: str) -> bool:
    return any(line.strip().lower() in QUOTE_MARKERS for line in text.splitlines())


def _attach_quoted_status_listener(page) -> dict[str, str | None]:
    quoted: dict[str, str | None] = {"id": None}

    def handle_response(response) -> None:
        if quoted["id"]:
            return
        url = response.url
        if "TweetResultByRestId" not in url and "TweetDetail" not in url:
            return
        try:
            payload = response.json()
        except Exception:
            return
        found = _find_quoted_status_id(payload)
        if found:
            quoted["id"] = found

    page.on("response", handle_response)
    return quoted


def _attach_tweet_detail_listener(page) -> dict[str, object | None]:
    detail: dict[str, object | None] = {"payload": None}

    def handle_response(response) -> None:
        if detail["payload"] is not None:
            return
        url = response.url
        if "TweetDetail" not in url:
            return
        try:
            payload = response.json()
        except Exception:
            return
        detail["payload"] = payload

    page.on("response", handle_response)
    return detail


def _extract_thread_ids_from_payload(
    payload: object | None,
    *,
    author_handle: str | None,
    anchor_time_datetime: str | None,
) -> List[str]:
    if not payload or not author_handle:
        return []
    handle = author_handle.lstrip("@").lower()
    anchor_dt = _parse_iso_datetime(anchor_time_datetime)
    if isinstance(payload, dict):
        data = payload.get("data") or {}
        convo = data.get("threaded_conversation_with_injections_v2") or {}
        instructions = convo.get("instructions") or []
    else:
        return []

    entries = []
    for inst in instructions:
        if isinstance(inst, dict) and inst.get("type") == "TimelineAddEntries":
            entries = inst.get("entries") or []
            break

    thread_ids: List[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        content = entry.get("content") or {}
        item = content.get("itemContent") or {}
        tweet_result = item.get("tweet_results", {}).get("result", {})
        if not isinstance(tweet_result, dict) or tweet_result.get("__typename") != "Tweet":
            continue
        user = tweet_result.get("core", {}).get("user_results", {}).get("result", {})
        user_core = (user.get("core") or {}) if isinstance(user, dict) else {}
        screen_name = user_core.get("screen_name")
        if not screen_name or screen_name.lower() != handle:
            continue
        created_at = tweet_result.get("legacy", {}).get("created_at")
        created_dt = _parse_twitter_created_at(created_at)
        minutes = _minutes_between(created_dt, anchor_dt)
        if minutes is not None and (minutes < 0 or minutes > THREAD_MAX_MINUTES):
            continue
        rest_id = tweet_result.get("rest_id")
        if rest_id:
            thread_ids.append(str(rest_id))
    return thread_ids


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


def _resolve_storage_state(storage_state: Path | None) -> Path | None:
    # The storage_state avoids X's login wall when opening the tweet.
    if storage_state is None:
        return None
    path = storage_state.expanduser()
    if not path.exists():
        raise FileNotFoundError(
            f"storage_state not found at {path}. "
            "Run utils/create_x_state.py to generate it."
        )
    return path


def _locate_tweet_article(page, tweet_url: str | None = None, *, timeout_ms: int = 15000):
    # X's login wall can hide the <article>; look for alternatives.
    tweet_id = _status_id_from_url(tweet_url) if tweet_url else None
    target_selector = f"a[href*='/status/{tweet_id}']" if tweet_id else None
    try:
        if target_selector:
            page.wait_for_selector(
                f"article {target_selector}, div[data-testid='tweet'] {target_selector}",
                timeout=timeout_ms,
            )
        else:
            page.wait_for_selector("article, div[data-testid='tweet']", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        return None
    if target_selector:
        # Prefer the tweet matching the requested status ID (threads show replies first).
        article = page.locator("article").filter(has=page.locator(target_selector))
        if article.count() > 0:
            return article.first
        tweet = page.locator("div[data-testid='tweet']").filter(
            has=page.locator(target_selector)
        )
        if tweet.count() > 0:
            return tweet.first
    article = page.locator("article")
    if article.count() > 0:
        return article.first
    tweet = page.locator("div[data-testid='tweet']")
    if tweet.count() > 0:
        return tweet.first
    return None


def _extract_primary_link(article, tweet_url: str) -> str | None:
    """Returns the first external link (expanded/full/href) pointing to http(s), excluding the tweet itself."""
    seen: set[str] = set()
    tweet_lower = tweet_url.rstrip("/").lower()
    for anchor in article.locator("a").all():
        href = anchor.get_attribute("href") or ""
        expanded = (
            anchor.get_attribute("data-expanded-url")
            or anchor.get_attribute("data-full-url")
            or href
        )
        href = (expanded or "").strip()
        if not href:
            continue
        # Keep only http(s) links
        if not href.startswith(("http://", "https://")):
            continue
        candidate = href.rstrip("/")
        lower = candidate.lower()
        if lower == tweet_lower or lower in seen:
            continue
        seen.add(lower)
        return candidate
    return None


def _extract_tweet_parts(
    article,
    tweet_url: str,
    *,
    quoted_status_id: str | None = None,
) -> TweetParts:
    author_name, author_handle = _extract_author_details(article)

    raw_text = article.inner_text()
    body_text = strip_tweet_stats(rebuild_urls_from_lines(raw_text).strip())

    quoted_tweet_url = None
    if quoted_status_id:
        quoted_tweet_url = _quoted_url_from_graphql_id(quoted_status_id, tweet_url)
    if not quoted_tweet_url:
        quoted_tweet_url = _extract_quoted_tweet_url(article, tweet_url)

    has_quote_marker = _has_quote_marker(body_text)
    body_text = _insert_quote_separator(
        body_text,
        quoted_tweet_url if has_quote_marker and quoted_tweet_url else None,
    )

    image_urls_main: List[str] = []
    image_urls_quoted: List[str] = []
    seen: set[str] = set()
    external_link = _extract_primary_link(article, tweet_url)
    root_handle = article.element_handle()
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
            if has_quote_marker and root_handle and _is_after_quote_marker(img, root_handle):
                image_urls_quoted.append(candidate)
            else:
                image_urls_main.append(candidate)

    avatar_url, media_urls = _split_image_urls(image_urls_main)
    _, quoted_media_urls = _split_image_urls(image_urls_quoted)
    main_media_lines = _media_markdown_lines(media_urls)
    quoted_media_lines = _media_markdown_lines(quoted_media_urls)
    if has_quote_marker and main_media_lines:
        body_text = _insert_media_before_quote(body_text, main_media_lines)
        main_media_lines = []

    media_present = bool(media_urls or quoted_media_urls)
    trailing_media_lines = quoted_media_lines if has_quote_marker else main_media_lines

    return TweetParts(
        author_name=author_name,
        author_handle=author_handle,
        body_text=body_text,
        avatar_url=avatar_url,
        trailing_media_lines=trailing_media_lines,
        media_present=media_present,
        external_link=external_link,
    )


def _build_single_tweet_markdown(parts: TweetParts, tweet_url: str) -> str:
    title = _build_title(parts.author_name, parts.author_handle)
    front_matter = [
        "---",
        "source: tweet",
        f"tweet_url: {tweet_url}",
    ]
    if parts.author_handle:
        front_matter.append(f'tweet_author: "{parts.author_handle}"')
    if parts.author_name:
        front_matter.append(f'tweet_author_name: "{parts.author_name}"')
    front_matter.extend(["---", ""])

    md_lines = [*front_matter, f"# {title}", "", f"[View on X]({tweet_url})"]
    if parts.avatar_url:
        md_lines.extend(["", f"![avatar]({parts.avatar_url})"])

    if parts.body_text:
        md_lines.extend(["", parts.body_text])

    if parts.trailing_media_lines:
        md_lines.append("")
        md_lines.extend(parts.trailing_media_lines)
        md_lines.append("")

    if parts.external_link and parts.media_present:
        md_lines.extend(["", f"Original link: {parts.external_link}"])

    return "\n".join(md_lines).strip() + "\n"


def fetch_tweet_markdown(
    url: str,
    *,
    headless: bool = True,
    storage_state: Path | None = None,
) -> tuple[str, str]:
    """Return (markdown, filename) for the given tweet."""
    if sync_playwright is None:
        raise RuntimeError(
            "playwright is not installed. Run 'pip install playwright' and "
            "'playwright install chromium' to use this tool."
        )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        state_path = _resolve_storage_state(storage_state)
        context_kwargs = {"user_agent": USER_AGENT}
        if state_path:
            # Use an authenticated session to avoid X's login wall.
            context_kwargs["storage_state"] = str(state_path)
        context = browser.new_context(**context_kwargs)
        if state_path:
            # Reinforce the context against X's login wall.
            context.add_init_script(STEALTH_SNIPPET)
        page = context.new_page()
        quoted_status = _attach_quoted_status_listener(page)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        _wait_with_log(page, WAIT_MS, "cargar el tweet")

        article = _locate_tweet_article(page, url)
        if article is None:
            raise RuntimeError(
                "Could not find the post <article>. "
                "It may require login or be unavailable."
            )

        parts = _extract_tweet_parts(article, url, quoted_status_id=quoted_status["id"])
        filename = _build_filename(url, parts.author_handle)
        markdown = _build_single_tweet_markdown(parts, url)

        browser.close()
        return markdown, filename


def fetch_tweet_thread_markdown(
    url: str,
    *,
    headless: bool = True,
    storage_state: Path | None = None,
    like_author_handle: str | None = None,
    like_time_text: str | None = None,
    like_time_datetime: str | None = None,
) -> tuple[str, str]:
    """Return (markdown, filename) for a tweet, expanding threads when possible."""
    if sync_playwright is None:
        raise RuntimeError(
            "playwright is not installed. Run 'pip install playwright' and "
            "'playwright install chromium' to use this tool."
        )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        state_path = _resolve_storage_state(storage_state)
        context_kwargs = {"user_agent": USER_AGENT}
        if state_path:
            context_kwargs["storage_state"] = str(state_path)
        context = browser.new_context(**context_kwargs)
        if state_path:
            context.add_init_script(STEALTH_SNIPPET)
        page = context.new_page()
        quoted_status = _attach_quoted_status_listener(page)
        tweet_detail = _attach_tweet_detail_listener(page)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        _wait_with_log(page, WAIT_MS, "cargar el tweet")

        article = _locate_tweet_article(page, url)
        if article is None:
            raise RuntimeError(
                "Could not find the post <article>. "
                "It may require login or be unavailable."
            )

        target_parts = _extract_tweet_parts(article, url, quoted_status_id=quoted_status["id"])
        _, target_time_datetime = _extract_time_details(article)
        filename = _build_filename(url, target_parts.author_handle)

        if not (like_author_handle and like_time_text):
            browser.close()
            return _build_single_tweet_markdown(target_parts, url), filename

        thread_payload = tweet_detail.get("payload")
        if thread_payload is None:
            thread_payload = _wait_for_tweet_detail(page, TWEET_DETAIL_WAIT_MS)
            if thread_payload is not None:
                tweet_detail["payload"] = thread_payload
        thread_marker = _has_thread_marker(article)
        thread_ids = _extract_thread_ids_from_payload(
            thread_payload,
            author_handle=like_author_handle or target_parts.author_handle,
            anchor_time_datetime=target_time_datetime or like_time_datetime,
        )

        articles = page.locator("article")
        total = articles.count()
        if total <= 1 and (not thread_ids or len(thread_ids) <= 1):
            if thread_payload is None and thread_marker:
                _wait_with_log(page, WAIT_MS, "cargar el hilo")
                thread_payload = tweet_detail.get("payload")
                thread_marker = _has_thread_marker(article)
                thread_ids = _extract_thread_ids_from_payload(
                    thread_payload,
                    author_handle=like_author_handle or target_parts.author_handle,
                    anchor_time_datetime=target_time_datetime or like_time_datetime,
                )
                articles = page.locator("article")
                total = articles.count()
            if total <= 1 and (not thread_ids or len(thread_ids) <= 1):
                browser.close()
                return _build_single_tweet_markdown(target_parts, url), filename

        target_id = _status_id_from_url(url)
        target_idx = None
        if target_id:
            selector = f"a[href*='/status/{target_id}']"
            for idx in range(total):
                if articles.nth(idx).locator(selector).count() > 0:
                    target_idx = idx
                    break

        entries: List[tuple[str | None, str | None, str | None]] = []
        for idx in range(total):
            article_handle = articles.nth(idx)
            _, author_handle = _extract_author_details(article_handle)
            time_text, time_datetime = _extract_time_details(article_handle)
            entries.append((author_handle, time_text, time_datetime))

        selected_indices = _select_thread_indices(
            entries,
            target_idx,
            author_handle=like_author_handle,
            time_text=like_time_text,
            anchor_time_datetime=target_time_datetime or like_time_datetime,
        )

        if thread_ids and target_id:
            if target_id in thread_ids:
                target_idx = thread_ids.index(target_id)
        if thread_ids and len(thread_ids) > len(selected_indices):
            primary_handle = target_parts.author_handle or like_author_handle
            handle_slug = (primary_handle or "").lstrip("@")
            thread_parts: List[tuple[str | None, TweetParts]] = []
            for rest_id in thread_ids:
                section_url = (
                    f"https://x.com/{handle_slug}/status/{rest_id}"
                    if handle_slug
                    else f"https://x.com/i/web/status/{rest_id}"
                )
                if target_id and rest_id == target_id:
                    thread_parts.append((section_url, target_parts))
                    continue
                page.goto(section_url, wait_until="domcontentloaded", timeout=60000)
                _wait_with_log(page, WAIT_MS, "cargar un tweet del hilo")
                art = _locate_tweet_article(page, section_url)
                if art is None:
                    continue
                parts = _extract_tweet_parts(art, section_url)
                thread_parts.append((section_url, parts))
        else:
            if len(selected_indices) <= 1:
                browser.close()
                return _build_single_tweet_markdown(target_parts, url), filename

            primary_handle = target_parts.author_handle or like_author_handle
            thread_parts = []
            for idx in selected_indices:
                art = articles.nth(idx)
                section_url = url if idx == target_idx else _extract_article_status_url(art, primary_handle)
                extract_url = section_url or url
                parts = target_parts if idx == target_idx else _extract_tweet_parts(art, extract_url)
                thread_parts.append((section_url, parts))

        if len(thread_parts) <= 1:
            browser.close()
            return _build_single_tweet_markdown(target_parts, url), filename

        print(f"🧵 Hilo descargado ({len(thread_parts)} tweets).")
        author_handle = target_parts.author_handle or like_author_handle
        title = _build_title(target_parts.author_name, author_handle, kind="Thread")
        count = len(thread_parts)
        front_matter = [
            "---",
            "source: tweet",
            f"tweet_url: {url}",
            "tweet_thread: true",
            f"tweet_thread_count: {count}",
        ]
        if author_handle:
            front_matter.append(f'tweet_author: "{author_handle}"')
        if target_parts.author_name:
            front_matter.append(f'tweet_author_name: "{target_parts.author_name}"')
        front_matter.extend(["---", ""])

        md_lines = [*front_matter, f"# {title}"]
        if target_parts.avatar_url:
            md_lines.extend(["", f"![avatar]({target_parts.avatar_url})"])

        for section_url, parts in thread_parts:
            link_url = section_url or url
            md_lines.extend(["", "---", f"[View on X]({link_url})"])
            if parts.body_text:
                md_lines.extend(["", parts.body_text])
            if parts.trailing_media_lines:
                md_lines.append("")
                md_lines.extend(parts.trailing_media_lines)
                md_lines.append("")
            if parts.external_link and parts.media_present:
                md_lines.extend(["", f"Original link: {parts.external_link}"])

        markdown = "\n".join(md_lines).strip() + "\n"
        browser.close()
        return markdown, filename


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a public tweet and save it as pipeline-ready Markdown.",
    )
    parser.add_argument("url", help="URL del tweet en https://x.com/...")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=cfg.INCOMING,
        help=f"Directory to save the Markdown (default: {cfg.INCOMING})",
    )
    parser.add_argument(
        "--filename",
        help="Filename to use (overrides the auto-generated one).",
    )
    headless_group = parser.add_mutually_exclusive_group()
    headless_group.add_argument(
        "--headless",
        dest="headless",
        action="store_true",
        default=True,
        help="Run Chromium in headless mode (default).",
    )
    headless_group.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Open Chromium with UI (useful for debugging).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir: Path = args.output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        markdown, auto_filename = fetch_tweet_markdown(
            args.url,
            headless=args.headless,
        )
    except PlaywrightTimeoutError as exc:
        raise SystemExit(f"❌ Timeout loading the tweet: {exc}") from exc
    except Exception as exc:  # pragma: no cover - controlled CLI output
        raise SystemExit(f"❌ Error extracting the tweet: {exc}") from exc

    filename = args.filename or auto_filename
    destination = output_dir / filename
    destination.write_text(markdown, encoding="utf-8")
    print(f"🐦 Tweet saved to {destination}")


if __name__ == "__main__":
    main()
