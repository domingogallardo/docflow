#!/usr/bin/env python3
"""Convert a public tweet into a self-contained Markdown file."""
from __future__ import annotations

import argparse
import re
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


def rebuild_urls_from_lines(text: str) -> str:
    """Rebuild URLs that X splits with line breaks and ellipses."""
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
            "Run utils/login_x.py to generate it."
        )
    return path


def _locate_tweet_article(page, *, timeout_ms: int = 15000):
    # X's login wall can hide the <article>; look for alternatives.
    try:
        page.wait_for_selector("article, div[data-testid='tweet']", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        return None
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


def fetch_tweet_markdown(
    url: str,
    *,
    wait_ms: int = 5000,
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
        page.wait_for_timeout(wait_ms)

        article = _locate_tweet_article(page)
        if article is None:
            raise RuntimeError(
                "Could not find the post <article>. "
                "It may require login or be unavailable."
            )

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
        quoted_tweet_url = _quoted_url_from_graphql_id(quoted_status["id"], url)
        if not quoted_tweet_url:
            quoted_tweet_url = _extract_quoted_tweet_url(article, url)
        has_quote_marker = _has_quote_marker(body_text)
        body_text = _insert_quote_separator(
            body_text,
            quoted_tweet_url if has_quote_marker and quoted_tweet_url else None,
        )

        image_urls_main: List[str] = []
        image_urls_quoted: List[str] = []
        seen: set[str] = set()
        external_link = _extract_primary_link(article, url)
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
                if has_quote_marker and _is_after_quote_marker(img, root_handle):
                    image_urls_quoted.append(candidate)
                else:
                    image_urls_main.append(candidate)

        title = _build_title(author_name, author_handle)
        filename = _build_filename(url, author_handle)

        avatar_url, media_urls = _split_image_urls(image_urls_main)
        _, quoted_media_urls = _split_image_urls(image_urls_quoted)
        main_media_lines = _media_markdown_lines(media_urls)
        quoted_media_lines = _media_markdown_lines(quoted_media_urls)
        if has_quote_marker and main_media_lines:
            body_text = _insert_media_before_quote(body_text, main_media_lines)
            main_media_lines = []

        front_matter = [
            "---",
            "source: tweet",
            f"tweet_url: {url}",
        ]
        if author_handle:
            front_matter.append(f'tweet_author: "{author_handle}"')
        if author_name:
            front_matter.append(f'tweet_author_name: "{author_name}"')
        front_matter.extend(["---", ""])

        md_lines = [*front_matter, f"# {title}", "", f"[View on X]({url})"]
        if avatar_url:
            md_lines.extend(["", f"![avatar]({avatar_url})"])

        if body_text:
            md_lines.extend(["", body_text])

        media_present = bool(media_urls or quoted_media_urls)
        trailing_media_lines = quoted_media_lines if has_quote_marker else main_media_lines
        if trailing_media_lines:
            md_lines.append("")
            md_lines.extend(trailing_media_lines)
            md_lines.append("")

        if external_link and media_present:
            md_lines.extend(["", f"Original link: {external_link}"])

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
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=5000,
        help="Additional wait time in milliseconds after loading the page.",
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
            wait_ms=args.wait_ms,
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
