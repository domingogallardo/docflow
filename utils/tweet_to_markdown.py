#!/usr/bin/env python3
"""Convert a public tweet into a self-contained Markdown file."""
from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, parse_qsl, urlencode, urljoin, urlunparse
from typing import List, Optional, Sequence, Tuple

try:  # pragma: no cover - optional import
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
except ImportError:  # pragma: no cover - environment without Playwright
    PlaywrightTimeoutError = RuntimeError  # type: ignore[misc,assignment]
    sync_playwright = None  # type: ignore[assignment]

import config as cfg
from utils.markdown_utils import enrich_markdown_metadata, front_matter_block

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
METRIC_TOKEN_RE = re.compile(r"[0-9]+(?:[.,][0-9]+)?[kmb]?|[a-záéíóúñü]+", re.IGNORECASE)
METRIC_NUMBER_TOKEN_RE = re.compile(r"^\d+(?:[.,]\d+)?[kmb]?$", re.IGNORECASE)
HANDLE_ONLY_RE = re.compile(r"^@[A-Za-z0-9_]+$")
INLINE_AUTHOR_HANDLE_ONLY_RE = re.compile(
    r"^(?P<name>(?![#>\[])[^@\n]{1,80}?)(?P<handle>@[A-Za-z0-9_]{1,20})$"
)
INLINE_AUTHOR_HANDLE_TIME_RE = re.compile(
    r"^(?P<name>(?![#>\[])[^@\n]{1,80}?)(?P<handle>@[A-Za-z0-9_]{1,20})"
    r"(?P<rest>·.*)$"
)
INLINE_AUTHOR_TIME_RE = re.compile(
    r"^(?P<time>·\s*(?:\d+\s?[smhd]|[A-Z][a-z]{2,8}\s+\d{1,2}(?:,\s*20\d{2})?))"
    r"(?P<body>\S.*)$"
)
LINK_CARD_SOURCE_RE = re.compile(
    r"(?<![\s\n])(?P<source>(?:From|De) [A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,})\b"
)
LINK_CARD_TITLE_BOUNDARY_RE = re.compile(
    r"(?<=[.!?…\)])"
    r"(?=(?:[A-ZÁÉÍÓÚÜÑ0-9]|GitHub -|Release |Releases )"
    r"[^\n]{1,180}\n(?:From|De) [A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,}\b)"
)
LEADING_POSSESSIVE_RE = re.compile(r"^[\'’]")
SENTENCE_END_RE = re.compile(r"[.!?…:;](?:[\"')\]”’]+)?$")
QUOTE_MARKERS = {"quote"}
QUOTED_TWEET_HEADING = "#### Tweet citado"
INLINE_QUOTED_TWEET_RE = re.compile(
    r"Quote(?=[A-ZÁÉÍÓÚÜÑ][^@\n]{1,80}@[A-Za-z0-9_]{1,20}(?:·|\b))"
)
QUOTE_MARKERS_JS = ", ".join(f'"{m}"' for m in sorted(QUOTE_MARKERS))
SHOW_MORE_LABELS = (
    "Show more",
    "Mostrar más",
    "Mostrar mais",
    "Ver más",
    "Ver mais",
    "Read more",
    "Leer más",
)
SHOW_MORE_LABELS_NORMALIZED = {
    "show more",
    "mostrar más",
    "mostrar mas",
    "mostrar mais",
    "ver más",
    "ver mas",
    "ver mais",
    "read more",
    "leer más",
    "leer mas",
}
TRANSLATION_PROMPT_LABELS_NORMALIZED = {
    "show translation",
    "see translation",
    "mostrar traducción",
    "mostrar traduccion",
    "ver traducción",
    "ver traduccion",
}
ARTICLE_PROMPT_LABELS_NORMALIZED = {
    "want to publish your own article",
    "upgrade to premium",
    "upgrade to premium+",
}
SUBSCRIBE_PROMPT_LABELS_NORMALIZED = {
    "subscribe",
    "click to subscribe",
}
PLATFORM_UI_PROMPT_LABELS_NORMALIZED = {
    "last edited",
    "opens edit history",
    "view activity",
}
TRANSLATION_PROMPT_INLINE_RE = re.compile(
    "|".join(
        re.escape(label)
        for label in sorted(TRANSLATION_PROMPT_LABELS_NORMALIZED, key=len, reverse=True)
    ),
    re.IGNORECASE,
)
ARTICLE_PROMPT_INLINE_RE = re.compile(
    r"Want\s+to\s+publish\s+your\s+own\s+Article\?\s*Upgrade\s+to\s+Premium\+?",
    re.IGNORECASE,
)
SUBSCRIBE_PROMPT_WITH_HANDLE_RE = re.compile(
    r"@(?P<handle>[A-Za-z0-9_]{1,20})"
    r"Subscribe\s*Click\s*to\s*Subscribe\s*to\s*(?P=handle)",
    re.IGNORECASE,
)
SUBSCRIBE_PROMPT_LINE_RE = re.compile(
    r"^Subscribe\s*Click\s*to\s*Subscribe\s*to\s*@?[A-Za-z0-9_]{1,20}$",
    re.IGNORECASE,
)
PLATFORM_UI_PROMPT_INLINE_RE = re.compile(
    r"(Last edited|Opens edit history|View activity)",
    re.IGNORECASE,
)
COMPACT_ARTICLE_METRIC_PREAMBLE_RE = re.compile(
    r"^(?P<prefix>.+?)(?P<metrics>\d[\d.,]*(?:[kmbKMB])?(?:\d[\d.,]*(?:[kmbKMB])?){3,})"
    r"(?P<body>[A-ZÁÉÍÓÚÜÑ][^\n]*)$"
)
EMBEDDED_TWEET_DATE_RE = re.compile(
    r"^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|"
    r"Ene|Feb|Mar|Abr|May|Jun|Jul|Ago|Sep|Oct|Nov|Dic)\s+\d{1,2}$",
    re.IGNORECASE,
)
COMPACT_TIMESTAMP_TAIL_RE = re.compile(
    r"\d{1,2}:\d{2}\s*(?:AM|PM)\s*·\s*"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+"
    r"\d{1,2},\s+20\d{2}(?P<tail>.*)$",
    re.IGNORECASE,
)
COMPACT_METRIC_TAIL_HINTS = (
    "view",
    "views",
    "visualizaciones",
    "impresiones",
    "relevant",
    "relevante",
    "quote",
    "quotes",
    "reply",
    "replies",
    "retweet",
    "retweets",
    "repost",
    "likes",
    "bookmarks",
    "access your post analytics",
    "unlock advanced analytics",
    "unlock advanced anlytics",
    "learn more",
)
POLL_METADATA_RE = re.compile(
    r"(?P<count>\d[\d,.]*)\s+(?P<label>votes|votos)\s*·\s*"
    r"(?P<remaining>\d+\s+[^·\n]*?(?:left|restantes?))",
    re.IGNORECASE,
)
POLL_OPTION_RESULT_RE = re.compile(
    r"(?P<label>.+?)(?P<percent>\d{1,3}(?:[.,]\d+)?%)"
)
TWIMG_EMOJI_PATH_RE = re.compile(r"/emoji/v\d+/(?:svg|72x72)/([0-9a-fA-F-]+)\.[a-z0-9]+$")
VALID_CAPTURE_SOURCES = {"liked", "posted"}
VALID_POSTED_KINDS = {"post", "repost", "reply"}
PLATFORM_PROMO_STRONG_PHRASES = (
    "access your post analytics",
    "unlock advanced analytics with premium",
    "unlock advanced analytics with x premium",
    "unlock advanced anlytics with premium",
    "unlock advanced anlytics with x premium",
)
PLATFORM_PROMO_WEAK_PHRASES = {"learn more"}
PLATFORM_PROMO_ALL_PHRASES = (
    *PLATFORM_PROMO_STRONG_PHRASES,
    *sorted(PLATFORM_PROMO_WEAK_PHRASES),
)
METRIC_TAIL_MARKERS = {
    "relevant",
    "relevante",
    "view quote",
    "view quotes",
    "view reply",
    "view replies",
    "view post engagements",
    "there's a new version of this post",
    "there’s a new version of this post",
    "see the latest post",
}
REPLY_CONTROL_PROMPTS = {
    "who can reply",
    "you can reply to this post",
    "you can reply to this reply",
}
METRIC_WORD_TOKENS = {
    "am",
    "pm",
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
    "ene",
    "abr",
    "ago",
    "dic",
    "retweet",
    "retweets",
    "retuit",
    "retuits",
    "repost",
    "reposts",
    "republicaciones",
    "quote",
    "quotes",
    "citas",
    "likes",
    "me",
    "gusta",
    "favoritos",
    "bookmarks",
    "marcadores",
    "views",
    "view",
    "visualizaciones",
    "impresiones",
    "replies",
    "reply",
    "respuestas",
    "shares",
    "compartidos",
    "guardados",
    "read",
    "repl",
    "leer",
    "resp",
    "relevant",
    "relevante",
}
THREAD_MAX_MINUTES = 24 * 60
THREAD_MARKER_RE = re.compile(r"\bthread\b|\bhilo\b", re.IGNORECASE)
WAIT_MS = 1000
TWEET_DETAIL_WAIT_MS = 5000
MAX_CONVERSATION_PARENTS = 20
SHOW_MORE_WAIT_MS = 600
LOGIN_URL_HINTS = ("/login", "/i/flow/login", "/i/flow/signup")
LOGIN_SELECTORS = (
    "input[name='text']",
    "input[type='password']",
    "[data-testid='loginButton']",
    "[data-testid='LoginForm_Login_Button']",
)
LOGIN_TEXT_HINTS = (
    "Sign in to X",
    "Inicia sesion",
    "Inicia sesión",
    "Iniciar sesion",
    "Iniciar sesión",
)
ARTICLE_TEXT_WITH_EMOJI_SCRIPT = """el => {
  const root = el.closest('article, div[data-testid="tweet"]') || el;
  const clone = root.cloneNode(true);
  const decodeEmoji = (url) => {
    try {
      const pathname = new URL(url, window.location.href).pathname;
      const match = pathname.match(/\\/emoji\\/v\\d+\\/(?:svg|72x72)\\/([0-9a-fA-F-]+)\\.[a-z0-9]+$/);
      if (!match) return null;
      const codepoints = match[1]
        .split('-')
        .map((part) => Number.parseInt(part, 16));
      if (!codepoints.length || codepoints.some((value) => Number.isNaN(value))) {
        return null;
      }
      return String.fromCodePoint(...codepoints);
    } catch (error) {
      return null;
    }
  };

  clone.querySelectorAll('img').forEach((img) => {
    const src = img.getAttribute('src') || '';
    const emoji = decodeEmoji(src);
    if (!emoji) {
      return;
    }
    img.replaceWith(document.createTextNode(emoji));
  });

  return clone.innerText;
}"""
UNAVAILABLE_TEXT_HINTS = (
    "This Post is unavailable",
    "This post is unavailable",
    "You're unable to view this Post",
    "You are unable to view this Post",
    "This Post is from a suspended account",
    "This Post is from an account you blocked",
    "This post was deleted",
    "Esta publicacion no esta disponible",
    "Esta publicación no está disponible",
    "Este post no esta disponible",
    "Este post no está disponible",
    "No se puede ver este post",
    "No puedes ver este post",
)


@dataclass(frozen=True)
class TweetParts:
    author_name: str | None
    author_handle: str | None
    body_text: str
    avatar_url: str | None
    trailing_media_lines: List[str]
    media_present: bool
    external_link: str | None


@dataclass(frozen=True)
class ReplyParentContext:
    url: str
    parts: TweetParts | None = None


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


def normalize_inline_mention_breaks(text: str) -> str:
    """Collapse line breaks introduced around inline @mentions and possessives."""
    lines = text.splitlines()
    normalized: List[str] = []

    for idx, original_line in enumerate(lines):
        stripped = original_line.strip()
        next_line = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
        if not stripped:
            normalized.append("")
            continue
        if (
            normalized
            and HANDLE_ONLY_RE.match(normalized[-1])
            and LEADING_POSSESSIVE_RE.match(stripped)
        ):
            normalized[-1] = normalized[-1] + stripped
            continue
        if normalized and LEADING_POSSESSIVE_RE.match(stripped):
            normalized[-1] = normalized[-1] + stripped
            continue
        if (
            normalized
            and HANDLE_ONLY_RE.match(stripped)
            and next_line
            and LEADING_POSSESSIVE_RE.match(next_line)
            and normalized[-1]
            and not SENTENCE_END_RE.search(normalized[-1].rstrip())
        ):
            normalized[-1] = normalized[-1].rstrip() + " " + stripped
            continue
        normalized.append(stripped)

    return "\n".join(normalized)


def _split_known_author_handle_line(
    line: str,
    *,
    author_name: str | None,
    author_handle: str | None,
) -> List[str] | None:
    if not author_handle:
        return None
    handle = author_handle.strip().strip('"')
    if not handle:
        return None
    if not handle.startswith("@"):
        handle = f"@{handle}"

    expected_name = (author_name or "").strip().strip('"')
    if expected_name:
        compact_prefix = f"{expected_name}{handle}"
        spaced_prefix = f"{expected_name} {handle}"
        if line.startswith(compact_prefix):
            name = expected_name
            rest = line[len(compact_prefix) :].lstrip()
        elif line.startswith(spaced_prefix):
            name = expected_name
            rest = line[len(spaced_prefix) :].lstrip()
        else:
            idx = line.find(handle)
            if idx <= 0:
                return None
            name = line[:idx].rstrip()
            if not name.startswith(expected_name):
                return None
            display_suffix = name[len(expected_name) :].strip()
            if (
                len(display_suffix) > 24
                or re.search(r"[\w@/#]", display_suffix, flags=re.UNICODE)
            ):
                return None
            rest = line[idx + len(handle) :].lstrip()
    else:
        idx = line.find(handle)
        if idx <= 0:
            return None
        name = line[:idx].rstrip()
        rest = line[idx + len(handle) :].lstrip()

    if not name or name.startswith(("#", ">", "[")):
        return None
    author = f"{name} {handle}"
    if not rest:
        return [author]
    if rest.startswith((".", ":", "/")):
        return None

    time_match = INLINE_AUTHOR_TIME_RE.match(rest)
    if time_match:
        return [f"{author}{time_match.group('time').rstrip()}", time_match.group("body").lstrip()]
    return [author, rest]


def normalize_glued_author_body_breaks(
    text: str,
    *,
    author_name: str | None = None,
    author_handle: str | None = None,
) -> str:
    """Separate X's glued top author/handle label from the tweet body."""
    normalized: List[str] = []
    for original_line in text.splitlines():
        stripped = original_line.strip()
        if not stripped:
            normalized.append("")
            continue

        known_split = _split_known_author_handle_line(
            stripped,
            author_name=author_name,
            author_handle=author_handle,
        )
        if known_split is not None:
            normalized.extend(known_split)
            continue

        match = INLINE_AUTHOR_HANDLE_ONLY_RE.match(stripped) or INLINE_AUTHOR_HANDLE_TIME_RE.match(stripped)
        if not match:
            normalized.append(stripped)
            continue

        author = f"{match.group('name').rstrip()} {match.group('handle')}"
        rest = (match.groupdict().get("rest") or "").lstrip()
        if not rest:
            normalized.append(author)
            continue
        # Avoid turning email addresses or URL-like text into fake author lines.
        if rest.startswith((".", ":", "/")):
            normalized.append(stripped)
            continue

        time_match = INLINE_AUTHOR_TIME_RE.match(rest)
        if time_match:
            normalized.append(f"{author}{time_match.group('time').rstrip()}")
            normalized.append(time_match.group("body").lstrip())
            continue

        normalized.append(author)
        normalized.append(rest)

    return "\n".join(normalized)


def normalize_glued_link_card_breaks(text: str) -> str:
    """Separate compact X link-card title/source text from the tweet body."""
    text = LINK_CARD_SOURCE_RE.sub(r"\n\g<source>", text)
    return LINK_CARD_TITLE_BOUNDARY_RE.sub("\n", text)


def strip_platform_inline_prompts(
    text: str,
    *,
    author_name: str | None = None,
    author_handle: str | None = None,
) -> str:
    """Remove standalone platform UI prompts embedded in tweet text."""
    def is_prompt_line(line: str) -> bool:
        probe = re.sub(r"(?i)<br\s*/?>", "", line).strip()
        probe = re.sub(r"(?i)^<p>\s*", "", probe)
        probe = re.sub(r"(?i)\s*</p>$", "", probe)
        normalized = _normalize_platform_text(probe)
        return (
            normalized in TRANSLATION_PROMPT_LABELS_NORMALIZED
            or normalized in ARTICLE_PROMPT_LABELS_NORMALIZED
            or normalized in SUBSCRIBE_PROMPT_LABELS_NORMALIZED
            or normalized in PLATFORM_UI_PROMPT_LABELS_NORMALIZED
            or bool(SUBSCRIBE_PROMPT_LINE_RE.match(probe))
        )

    def strip_subscribe_prompt(line: str) -> str:
        return SUBSCRIBE_PROMPT_WITH_HANDLE_RE.sub(
            lambda match: f"@{match.group('handle')}\n",
            line,
        )

    def strip_glued_prompt(line: str) -> str:
        def repl(match: re.Match[str]) -> str:
            start, end = match.span()
            previous = line[start - 1] if start > 0 else ""
            following = line[end] if end < len(line) else ""
            previous_dense = bool(previous and not previous.isspace() and previous not in '<>/"\'([{')
            following_dense = bool(following and not following.isspace() and following not in '<>/"\')]},.;:!?')
            if previous_dense and following_dense:
                return "\n"
            if previous_dense or following_dense:
                return " "
            return match.group(0)

        return TRANSLATION_PROMPT_INLINE_RE.sub(repl, line)

    def strip_article_prompt_tail(line: str) -> str:
        match = ARTICLE_PROMPT_INLINE_RE.search(line)
        if not match:
            return line
        before = line[: match.start()].rstrip()
        after = line[match.end() :].lstrip()
        if before and after:
            return f"{before}\n{after}"
        return before or after

    def strip_platform_ui_prompts(line: str) -> str:
        parts: List[str] = []
        cursor = 0
        for match in PLATFORM_UI_PROMPT_INLINE_RE.finditer(line):
            before = line[cursor : match.start()].strip()
            if before:
                parts.append(before)
            cursor = match.end()
        after = line[cursor:].strip()
        if after:
            parts.append(after)
        return "\n".join(parts)

    filtered: List[str] = []
    for line in text.splitlines():
        if not line.strip():
            filtered.append("")
            continue
        if is_prompt_line(line):
            continue
        cleaned = normalize_glued_link_card_breaks(
            strip_platform_ui_prompts(
                strip_glued_prompt(strip_subscribe_prompt(strip_article_prompt_tail(line)))
            )
        )
        for cleaned_line in cleaned.splitlines():
            if is_prompt_line(cleaned_line):
                continue
            for normalized_line in normalize_glued_author_body_breaks(
                cleaned_line,
                author_name=author_name,
                author_handle=author_handle,
            ).splitlines():
                filtered.append(normalized_line.strip())
    return "\n".join(_collapse_blank_lines(filtered))


def strip_article_metric_preamble(
    text: str,
    *,
    author_handle: str | None = None,
) -> str:
    """Remove X Article metric counters around article and embedded-tweet text."""
    lines = text.splitlines()
    if len(lines) < 3:
        return text

    handle = (author_handle or "").strip().strip('"')
    if handle and not handle.startswith("@"):
        handle = f"@{handle}"
    search_limit = min(len(lines), 10)
    cleaned_text: str | None = None

    if len(lines) >= 6:
        for idx in range(2, search_limit):
            stripped = lines[idx].strip()
            if not _is_numeric_stat(stripped):
                continue

            before = [line.strip() for line in lines[:idx] if line.strip()]
            if len(before) < 2:
                continue
            if before[-1].endswith(":"):
                continue
            if handle:
                has_author_handle = any(line == handle or handle in line for line in before[:3])
            else:
                has_author_handle = any(HANDLE_ONLY_RE.match(line) for line in before[:3])
            if not has_author_handle:
                continue

            end = idx
            while end < len(lines) and _is_numeric_stat(lines[end].strip()):
                end += 1
            if end - idx < 4:
                continue

            next_text = ""
            for candidate in lines[end:]:
                next_text = candidate.strip()
                if next_text:
                    break
            if not next_text or _is_metric_only_line(next_text):
                continue

            cleaned_text = "\n".join([*lines[:idx], *lines[end:]])
            break

    if cleaned_text is None:
        compact = _strip_compact_article_metric_preamble(lines, handle=handle)
        cleaned_text = compact if compact is not None else text

    embedded = _strip_embedded_article_metric_blocks(cleaned_text.splitlines())
    return embedded if embedded is not None else cleaned_text


def _strip_compact_article_metric_preamble(lines: List[str], *, handle: str) -> str | None:
    search_limit = min(len(lines), 10)
    for idx in range(2, search_limit):
        stripped = lines[idx].strip()
        match = COMPACT_ARTICLE_METRIC_PREAMBLE_RE.match(stripped)
        if not match:
            continue

        before = [line.strip() for line in lines[:idx] if line.strip()]
        if len(before) < 2:
            continue
        if handle:
            has_author_handle = any(line == handle or handle in line for line in before[:3])
        else:
            has_author_handle = any(HANDLE_ONLY_RE.match(line) for line in before[:3])
        if not has_author_handle:
            continue

        metrics = match.group("metrics")
        compact_metrics = re.sub(r"[.,\s]", "", metrics).lower()
        if not re.search(r"\d[kmb]$", compact_metrics) or len(re.findall(r"\d", compact_metrics)) < 4:
            continue

        prefix = match.group("prefix").rstrip()
        body = match.group("body").lstrip()
        if not prefix or not body or _is_metric_only_line(body):
            continue

        return "\n".join([*lines[:idx], prefix, body, *lines[idx + 1 :]])
    return None


def _strip_embedded_article_metric_blocks(lines: List[str]) -> str | None:
    cleaned: List[str] = []
    idx = 0
    changed = False
    while idx < len(lines):
        stripped = lines[idx].strip()
        if not _is_numeric_stat(stripped):
            cleaned.append(lines[idx])
            idx += 1
            continue

        end = idx
        while end < len(lines) and _is_numeric_stat(lines[end].strip()):
            end += 1
        if end - idx >= 4 and _has_embedded_tweet_chrome(lines, idx):
            next_text = next((line.strip() for line in lines[end:] if line.strip()), "")
            if next_text and not _is_metric_only_line(next_text):
                changed = True
                idx = end
                continue

        cleaned.extend(lines[idx:end])
        idx = end

    return "\n".join(cleaned) if changed else None


def _has_embedded_tweet_chrome(lines: List[str], metric_idx: int) -> bool:
    previous = [line.strip() for line in lines[max(0, metric_idx - 12) : metric_idx] if line.strip()]
    if not any(HANDLE_ONLY_RE.match(line) for line in previous):
        return False
    return any(line == "·" or EMBEDDED_TWEET_DATE_RE.match(line) for line in previous)


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


def _normalize_capture_source(capture_source: str | None) -> str:
    normalized = (capture_source or "liked").strip().lower()
    if normalized not in VALID_CAPTURE_SOURCES:
        raise ValueError(
            f"Unsupported capture_source '{capture_source}'. "
            f"Use one of: {', '.join(sorted(VALID_CAPTURE_SOURCES))}."
        )
    return normalized


def _normalize_posted_kind(posted_kind: str | None) -> str | None:
    if not posted_kind:
        return None
    normalized = posted_kind.strip().lower()
    if normalized not in VALID_POSTED_KINDS:
        raise ValueError(
            f"Unsupported posted_kind '{posted_kind}'. "
            f"Use one of: {', '.join(sorted(VALID_POSTED_KINDS))}."
        )
    return normalized


def _build_filename(url: str, author_handle: str | None, *, capture_source: str = "liked") -> str:
    tweet_id = Path(urlparse(url).path).name or "tweet"
    handle = (author_handle or "tweet").lstrip("@") or "tweet"
    source = _normalize_capture_source(capture_source)
    prefix = "Tweet posted" if source == "posted" else "Tweet"
    base = f"{prefix} - {handle}-{tweet_id}"
    return f"{_safe_filename(base)}.md"


def _format_wait_ms(wait_ms: int) -> str:
    seconds = wait_ms / 1000
    label = f"{seconds:.1f}".rstrip("0").rstrip(".")
    return f"{label}s"


def _wait_with_log(page, wait_ms: int, reason: str) -> None:
    if wait_ms <= 0:
        return
    print(f"⏳ Waiting {_format_wait_ms(wait_ms)} to {reason}...")
    page.wait_for_timeout(wait_ms)


def _wait_for_tweet_detail(page, timeout_ms: int) -> object | None:
    if timeout_ms <= 0:
        return None
    try:
        with page.expect_response(
            lambda resp: "TweetDetail" in resp.url,
            timeout=timeout_ms,
        ) as response_info:
            pass
    except PlaywrightTimeoutError:
        return None
    try:
        return response_info.value.json()
    except Exception:
        return None


def _has_any_selector(page, selectors: tuple[str, ...]) -> bool:
    for selector in selectors:
        try:
            if page.locator(selector).count() > 0:
                return True
        except Exception:
            continue
    return False


def _has_any_text(page, texts: tuple[str, ...]) -> bool:
    for text in texts:
        try:
            if page.locator(f"text={text}").count() > 0:
                return True
        except Exception:
            continue
    return False


def _detect_access_issue(page) -> str | None:
    if page is None:
        return None
    try:
        current_url = page.url or ""
    except Exception:
        current_url = ""
    if current_url and any(fragment in current_url for fragment in LOGIN_URL_HINTS):
        return "X requires login (login wall)."
    if _has_any_selector(page, LOGIN_SELECTORS) or _has_any_text(page, LOGIN_TEXT_HINTS):
        return "X requires login (login wall)."
    if _has_any_text(page, UNAVAILABLE_TEXT_HINTS):
        return "Tweet unavailable (deleted, protected, or restricted)."
    return None


def _raise_if_access_issue(page) -> None:
    issue = _detect_access_issue(page)
    if issue:
        raise RuntimeError(issue)


def _expand_show_more(article, page, *, wait_ms: int = SHOW_MORE_WAIT_MS) -> None:
    """Click inline "Show more" buttons to expand truncated tweet text."""
    if article is None or page is None:
        return
    for label in SHOW_MORE_LABELS:
        try:
            buttons = article.get_by_role("button", name=label, exact=True)
        except Exception:
            continue
        try:
            count = buttons.count()
        except Exception:
            continue
        for idx in range(count):
            try:
                buttons.nth(idx).click(timeout=2000)
                if wait_ms > 0:
                    page.wait_for_timeout(wait_ms)
            except Exception:
                continue


def _read_article_text(
    article,
    tweet_url: str,
    *,
    page=None,
    anchor_handle=None,
    timeout_ms: int = 15000,
) -> str:
    tweet_id = _status_id_from_url(tweet_url)
    current = article
    last_exc: PlaywrightTimeoutError | None = None

    for _ in range(3):
        best_text: str | None = None
        if page is not None and tweet_id:
            evaluated = _evaluate_article_text(page, tweet_id)
            best_text = _prefer_richer_text(best_text, evaluated)
        if anchor_handle is not None:
            try:
                text = anchor_handle.evaluate(ARTICLE_TEXT_WITH_EMOJI_SCRIPT)
                best_text = _prefer_richer_text(best_text, text)
            except Exception:
                pass
        if best_text and "\n" not in best_text:
            try:
                refined = current.evaluate(ARTICLE_TEXT_WITH_EMOJI_SCRIPT)
                best_text = _prefer_richer_text(best_text, refined)
            except Exception:
                pass
        try:
            text = current.inner_text(timeout=timeout_ms)
            best_text = _prefer_richer_text(best_text, text)
        except PlaywrightTimeoutError as exc:
            last_exc = exc
            try:
                content = current.text_content(timeout=5000)
            except PlaywrightTimeoutError:
                content = None
            if content:
                best_text = _prefer_richer_text(best_text, content)
        if best_text:
            return best_text
        if page is None:
            break
        _wait_with_log(page, WAIT_MS, "retry tweet text")
        refreshed = _locate_tweet_article(page, tweet_url, timeout_ms=timeout_ms)
        if refreshed is None:
            break
        _expand_show_more(refreshed, page)
        current = refreshed

    if current is not None:
        try:
            return current.evaluate(ARTICLE_TEXT_WITH_EMOJI_SCRIPT)
        except Exception:
            pass
    if last_exc:
        raise last_exc
    raise RuntimeError("Could not read tweet text.")


def _anchor_handle_for_tweet(page, tweet_url: str):
    if page is None:
        return None
    tweet_id = _status_id_from_url(tweet_url)
    if not tweet_id:
        return None
    selector = f"a[href*='/status/{tweet_id}']"
    try:
        return page.locator(selector).first.element_handle()
    except Exception:
        return None


def _evaluate_article_text(page, tweet_id: str) -> str | None:
    if page is None or not tweet_id:
        return None
    try:
        selector = f"a[href*='/status/{tweet_id}']"
        return page.locator(selector).first.evaluate(ARTICLE_TEXT_WITH_EMOJI_SCRIPT)
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


def _resolve_thread_context(
    context_author_handle: str | None,
    context_time_text: str | None,
    context_time_datetime: str | None,
    target_author_handle: str | None,
    target_time_text: str | None,
    target_time_datetime: str | None,
) -> tuple[str | None, str | None, str | None]:
    return (
        context_author_handle or target_author_handle,
        context_time_text or target_time_text,
        context_time_datetime or target_time_datetime,
    )


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
    return any(THREAD_MARKER_RE.search(text or "") for text in link_texts)


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
    if not TIME_RE.search(line):
        return False
    if not ("am" in lower or "pm" in lower or "·" in line or re.search(r"\b20\d{2}\b", lower)):
        return False
    return _is_metric_only_line(line)


def _is_keyword_stat(line: str) -> bool:
    lower = line.lower()
    if not _is_metric_only_line(line):
        return False
    return any(keyword in lower for keyword in STAT_KEYWORDS)


def _is_numeric_stat(line: str) -> bool:
    if line == "·":
        return True
    if STAT_NUMBER_RE.match(line):
        return True
    lower = line.lower()
    return lower.startswith("read ") and "repl" in lower


def _is_show_more_line(line: str) -> bool:
    return line.strip().lower() in SHOW_MORE_LABELS_NORMALIZED


def _previous_nonblank_line(lines: List[str], idx: int) -> str | None:
    for prev_idx in range(idx - 1, -1, -1):
        candidate = lines[prev_idx].strip()
        if candidate:
            return lines[prev_idx]
    return None


def _normalize_platform_text(text: str) -> str:
    return " ".join(text.strip().lower().split()).rstrip(" .!?:;")


def _is_strong_platform_boilerplate_line(line: str) -> bool:
    normalized = _normalize_platform_text(line)
    return any(phrase in normalized for phrase in PLATFORM_PROMO_STRONG_PHRASES) and _is_platform_promo_sequence(
        normalized
    )


def _is_platform_boilerplate_line(lines: List[str], idx: int) -> bool:
    normalized = _normalize_platform_text(lines[idx])
    if not normalized:
        return False
    if _is_strong_platform_boilerplate_line(lines[idx]):
        return True
    if normalized not in PLATFORM_PROMO_WEAK_PHRASES:
        return False

    for previous in reversed(lines[:idx]):
        if not previous:
            continue
        return _is_strong_platform_boilerplate_line(previous)
    return False


def _is_metric_tail_context_line(line: str | None) -> bool:
    if not line:
        return False
    normalized = _normalize_platform_text(line)
    stripped = line.strip()
    return (
        _is_timestamp_line(line)
        or _is_keyword_stat(line)
        or _is_numeric_stat(line)
        or normalized in METRIC_TAIL_MARKERS
        or normalized in REPLY_CONTROL_PROMPTS
        or normalized == "accounts"
        or normalized.endswith("can reply")
        or bool(HANDLE_ONLY_RE.match(stripped))
    )


def _is_contextual_platform_tail_line(lines: List[str], idx: int) -> bool:
    stripped = lines[idx].strip()
    normalized = _normalize_platform_text(stripped)
    if not normalized:
        return False

    previous = _previous_nonblank_line(lines, idx)
    previous_normalized = _normalize_platform_text(previous) if previous else ""

    if normalized in METRIC_TAIL_MARKERS:
        return _is_metric_tail_context_line(previous)
    if normalized in REPLY_CONTROL_PROMPTS:
        return _is_metric_tail_context_line(previous)
    if normalized.endswith("can reply"):
        return _is_metric_tail_context_line(previous)
    if HANDLE_ONLY_RE.match(stripped):
        return previous_normalized == "accounts"
    if normalized == "accounts":
        return previous_normalized in REPLY_CONTROL_PROMPTS
    return False


def _is_platform_promo_sequence(text: str) -> bool:
    normalized = _normalize_platform_text(text)
    if not normalized:
        return False

    while normalized:
        matched = False
        for phrase in PLATFORM_PROMO_ALL_PHRASES:
            if normalized == phrase:
                return True
            if normalized.startswith(f"{phrase} "):
                normalized = normalized[len(phrase) + 1 :].lstrip()
                matched = True
                break
        if not matched:
            return False

    return True


def _strip_platform_boilerplate_tail(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""

    lowered = stripped.lower()
    for phrase in PLATFORM_PROMO_STRONG_PHRASES:
        search_from = len(lowered)
        while True:
            start = lowered.rfind(phrase, 0, search_from)
            if start < 0:
                break
            prefix = stripped[:start].rstrip()
            if prefix and prefix[-1] not in ".!?\n":
                search_from = start
                continue
            suffix = stripped[start:]
            if _is_platform_promo_sequence(suffix):
                return prefix
            search_from = start

    return stripped


def _strip_compact_metric_tail_line(line: str) -> str:
    match = COMPACT_TIMESTAMP_TAIL_RE.search(line)
    if not match:
        return line

    tail = match.group("tail")
    if not tail.strip():
        return line[: match.start()].rstrip()

    probe = tail.replace("·", " ").lower()
    if any(hint in probe for hint in COMPACT_METRIC_TAIL_HINTS):
        return line[: match.start()].rstrip()
    return line


def _format_compact_poll_line(line: str) -> str:
    poll_match = POLL_METADATA_RE.search(line)
    if not poll_match:
        return line

    before_poll_meta = line[: poll_match.start()].rstrip()
    question_idx = before_poll_meta.rfind("?")
    if question_idx < 0:
        return line

    intro = before_poll_meta[: question_idx + 1].rstrip()
    options_blob = before_poll_meta[question_idx + 1 :].strip()
    option_matches = list(POLL_OPTION_RESULT_RE.finditer(options_blob))
    if len(option_matches) < 2:
        return line

    options: List[tuple[str, str]] = []
    for option_match in option_matches:
        label = option_match.group("label").strip(" \t-–—:;")
        percent = option_match.group("percent")
        if not label:
            return line
        options.append((label, percent))

    metadata = (
        f"{poll_match.group('count')} "
        f"{poll_match.group('label').lower()} · "
        f"{poll_match.group('remaining').strip()}"
    )

    return "\n".join(
        [
            intro,
            "",
            *(f"- {label}: {percent}" for label, percent in options),
            "",
            metadata,
        ]
    )


def _normalize_compact_poll_results(text: str) -> str:
    lines: List[str] = []
    changed = False
    for line in text.splitlines():
        formatted = _format_compact_poll_line(line)
        if formatted != line:
            changed = True
        lines.extend(formatted.splitlines())
    if not changed:
        return text
    return "\n".join(_collapse_blank_lines(lines))


def _is_metric_only_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    if "http://" in lowered or "https://" in lowered:
        return False
    tokens = [token.lower() for token in METRIC_TOKEN_RE.findall(lowered)]
    if not tokens:
        return False

    has_word = False
    for token in tokens:
        if METRIC_NUMBER_TOKEN_RE.match(token):
            continue
        if token in METRIC_WORD_TOKENS:
            has_word = True
            continue
        return False

    return has_word or all(METRIC_NUMBER_TOKEN_RE.match(token) for token in tokens)


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
        or _is_show_more_line(lines[-1])
        or _is_platform_boilerplate_line(lines, len(lines) - 1)
        or _is_contextual_platform_tail_line(lines, len(lines) - 1)
    ):
        lines.pop()
        while lines and not lines[-1]:
            lines.pop()

    cleaned = _strip_platform_boilerplate_tail("\n".join(lines)).strip()
    cleaned = "\n".join(
        _strip_compact_metric_tail_line(line).rstrip()
        for line in cleaned.splitlines()
    )
    return _normalize_compact_poll_results(cleaned).strip()


def _text_quality(text: str) -> tuple[int, int]:
    return (text.count("\n"), len(text))


def _prefer_richer_text(current: str | None, candidate: str | None) -> str | None:
    if not candidate:
        return current
    if not current:
        return candidate
    if _text_quality(candidate) > _text_quality(current):
        return candidate
    return current


def _insert_quote_separator(text: str, quoted_url: str | None = None) -> str:
    """Insert a Markdown horizontal rule before quote markers."""
    lines = text.splitlines()
    out: List[str] = []
    inserted_link = False
    in_inline_quote = False

    def append_quote_heading() -> None:
        nonlocal inserted_link
        if not out or out[-1].strip() != "---":
            if out and out[-1].strip():
                out.append("")
            out.append("---")
        if quoted_url and not inserted_link:
            out.append(f"[View quoted tweet]({quoted_url})")
            inserted_link = True
        if out and out[-1].strip():
            out.append("")
        out.append(QUOTED_TWEET_HEADING)

    for line in lines:
        stripped = line.strip()
        if in_inline_quote:
            if not stripped:
                out.append("")
                in_inline_quote = False
                continue
            if stripped.startswith("[![") or stripped.startswith("!["):
                in_inline_quote = False
                out.append(line)
                continue
            if stripped.startswith("> "):
                out.append(stripped[2:].strip())
                continue
            out.append(stripped)
            continue

        inline_match = INLINE_QUOTED_TWEET_RE.search(line)
        if inline_match is not None:
            before = line[: inline_match.start()].rstrip()
            quoted = line[inline_match.end() :].strip()
            if before:
                out.append(before)
            append_quote_heading()
            if quoted:
                out.append("")
                out.append(quoted)
                in_inline_quote = True
            continue

        if stripped.lower() in QUOTE_MARKERS:
            append_quote_heading()
            continue
        out.append(line)

    return "\n".join(out)


def _insert_media_before_quote(text: str, media_lines: List[str]) -> str:
    if not media_lines:
        return text
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lower() in QUOTE_MARKERS or stripped == QUOTED_TWEET_HEADING:
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


def _handle_from_status_url(url: str | None) -> str | None:
    canonical = _canonical_status_url(url)
    if not canonical:
        return None
    parsed = urlparse(canonical)
    segments = [seg for seg in parsed.path.split("/") if seg]
    if len(segments) >= 4 and segments[0] == "i" and segments[1] == "web":
        return None
    if len(segments) < 3 or segments[1] != "status":
        return None
    handle = segments[0].strip().lstrip("@")
    return f"@{handle.lower()}" if handle else None


def _normalize_handle_for_match(handle: str | None) -> str | None:
    if not handle:
        return None
    cleaned = handle.strip().lstrip("@")
    return f"@{cleaned.lower()}" if cleaned else None


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


def _find_tweet_result_by_rest_id(payload: object, rest_id: str | None) -> dict | None:
    if not rest_id:
        return None
    if isinstance(payload, dict):
        if payload.get("__typename") == "Tweet" and str(payload.get("rest_id") or "") == rest_id:
            return payload
        for value in payload.values():
            found = _find_tweet_result_by_rest_id(value, rest_id)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_tweet_result_by_rest_id(item, rest_id)
            if found:
                return found
    return None


def _reply_parent_url_from_payload(payload: object | None, tweet_url: str) -> str | None:
    if payload is None:
        return None
    tweet_id = _status_id_from_url(tweet_url)
    tweet_result = _find_tweet_result_by_rest_id(payload, tweet_id)
    if not tweet_result:
        return None
    legacy = tweet_result.get("legacy") or {}
    if not isinstance(legacy, dict):
        return None
    parent_id = legacy.get("in_reply_to_status_id_str") or legacy.get("in_reply_to_status_id")
    if not parent_id:
        return None
    parent_id = str(parent_id)
    if tweet_id and parent_id == tweet_id:
        return None
    parent_screen_name = legacy.get("in_reply_to_screen_name")
    if parent_screen_name:
        return f"https://x.com/{parent_screen_name}/status/{parent_id}"
    return f"https://x.com/i/web/status/{parent_id}"


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
    return any(line.strip().lower() in QUOTE_MARKERS for line in text.splitlines()) or bool(
        INLINE_QUOTED_TWEET_RE.search(text)
    )


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


def _emoji_from_twimg_url(url: str) -> str | None:
    match = TWIMG_EMOJI_PATH_RE.search(urlparse(url).path)
    if not match:
        return None

    codepoints = []
    for part in match.group(1).split("-"):
        try:
            codepoints.append(int(part, 16))
        except ValueError:
            return None
    if not codepoints:
        return None
    return "".join(chr(codepoint) for codepoint in codepoints)


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
        emoji = _emoji_from_twimg_url(image_url)
        if emoji:
            lines.append(emoji)
            continue
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
    page=None,
    quoted_status_id: str | None = None,
) -> TweetParts:
    anchor_handle = _anchor_handle_for_tweet(page, tweet_url) if page is not None else None
    author_name, author_handle = _extract_author_details(article)
    external_link = _extract_primary_link(article, tweet_url)

    quoted_tweet_url = None
    if quoted_status_id:
        quoted_tweet_url = _quoted_url_from_graphql_id(quoted_status_id, tweet_url)
    if not quoted_tweet_url:
        quoted_tweet_url = _extract_quoted_tweet_url(article, tweet_url)

    root_handle = None
    try:
        root_handle = article.element_handle()
    except PlaywrightTimeoutError:
        root_handle = None

    image_candidates: List[tuple[object, str]] = []
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
        if candidate and _emoji_from_twimg_url(candidate):
            continue
        if candidate and candidate not in seen:
            seen.add(candidate)
            image_candidates.append((img, candidate))

    if page is not None:
        _expand_show_more(article, page)

    raw_text = _read_article_text(
        article,
        tweet_url,
        page=page,
        anchor_handle=anchor_handle,
    )
    body_text = strip_tweet_stats(
        strip_article_metric_preamble(
            strip_platform_inline_prompts(
                normalize_inline_mention_breaks(rebuild_urls_from_lines(raw_text).strip()),
                author_name=author_name,
                author_handle=author_handle,
            ),
            author_handle=author_handle,
        )
    )

    has_quote_marker = _has_quote_marker(body_text)
    body_text = _insert_quote_separator(
        body_text,
        quoted_tweet_url if has_quote_marker and quoted_tweet_url else None,
    )

    image_urls_main: List[str] = []
    image_urls_quoted: List[str] = []
    for img, candidate in image_candidates:
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


def _author_label_from_parts(parts: TweetParts) -> str:
    bits: List[str] = []
    if parts.author_name:
        bits.append(parts.author_name)
    if parts.author_handle:
        bits.append(parts.author_handle)
    return " ".join(bits) if bits else "Autor desconocido"


def _strip_leading_author_label(text: str, parts: TweetParts) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)

    author_name = (parts.author_name or "").strip()
    author_handle = (parts.author_handle or "").strip()
    while lines:
        first = lines[0].strip()
        if author_name and first == author_name:
            lines.pop(0)
            continue
        if author_handle and first == author_handle:
            lines.pop(0)
            continue
        if author_name and author_handle and first.startswith(author_name) and author_handle in first:
            lines.pop(0)
            continue
        break
    return "\n".join(lines).strip()


def _append_tweet_content_lines(lines: List[str], parts: TweetParts, *, strip_author: bool = False) -> None:
    body_text = _strip_leading_author_label(parts.body_text, parts) if strip_author else parts.body_text
    if body_text:
        lines.extend(["", body_text])
    if parts.trailing_media_lines:
        lines.append("")
        lines.extend(parts.trailing_media_lines)
        lines.append("")
    if _should_append_external_link(body_text, parts.external_link):
        lines.extend(["", f"Original link: {parts.external_link}"])


def _reply_parent_markdown_lines(parent_context: ReplyParentContext | None) -> List[str]:
    if parent_context is None:
        return []
    return _reply_parent_contexts_markdown_lines([parent_context])


def _reply_parent_contexts_markdown_lines(parent_contexts: Sequence[ReplyParentContext]) -> List[str]:
    if not parent_contexts:
        return []
    lines = ["", "#### En respuesta a"]
    for idx, parent_context in enumerate(parent_contexts):
        if idx > 0:
            lines.extend(["", "---"])
        link_label = "Ver tweet padre en X" if idx == len(parent_contexts) - 1 else "Ver tweet anterior en X"
        lines.extend(["", f"[{link_label}]({parent_context.url})"])
        if parent_context.parts is not None:
            lines.extend(["", f"**{_author_label_from_parts(parent_context.parts)}**"])
            _append_tweet_content_lines(lines, parent_context.parts, strip_author=True)
    return lines


def _find_article_index_for_status(articles, status_url: str | None) -> int | None:
    status_id = _status_id_from_url(status_url)
    if not status_id:
        return None
    selector = f"a[href*='/status/{status_id}']"
    total = articles.count()
    for idx in range(total):
        if articles.nth(idx).locator(selector).count() > 0:
            return idx
    return None


def _extract_reply_parent_context(
    page,
    articles,
    *,
    target_idx: int | None,
    parent_url: str | None,
) -> ReplyParentContext | None:
    if page is None:
        return ReplyParentContext(parent_url) if parent_url else None

    candidate_url = parent_url
    candidate_article = None
    parent_idx = _find_article_index_for_status(articles, parent_url)
    if parent_idx is not None and parent_idx != target_idx:
        candidate_article = articles.nth(parent_idx)

    if candidate_article is None and target_idx is not None and target_idx > 0:
        candidate_article = articles.nth(target_idx - 1)
        candidate_url = _extract_article_status_url(candidate_article, None) or candidate_url

    if candidate_url:
        try:
            page.goto(candidate_url, wait_until="domcontentloaded", timeout=60000)
            _wait_with_log(page, WAIT_MS, "load the parent tweet")
            parent_article = _locate_tweet_article(page, candidate_url)
            if parent_article is not None:
                return ReplyParentContext(
                    url=candidate_url,
                    parts=_extract_tweet_parts(parent_article, candidate_url, page=page),
                )
        except Exception:
            pass
    if candidate_article is not None and candidate_url:
        try:
            return ReplyParentContext(
                url=candidate_url,
                parts=_extract_tweet_parts(candidate_article, candidate_url, page=page),
            )
        except Exception:
            return ReplyParentContext(candidate_url)

    if candidate_url:
        return ReplyParentContext(candidate_url)

    return None


def _load_tweet_detail_page(page, tweet_url: str) -> tuple[object | None, object | None]:
    detail = _attach_tweet_detail_listener(page)
    try:
        page.goto(tweet_url, wait_until="domcontentloaded", timeout=60000)
    except Exception:
        return None, None
    _wait_with_log(page, WAIT_MS, "load the conversation tweet")
    try:
        _raise_if_access_issue(page)
    except Exception:
        return None, detail.get("payload")
    article = _locate_tweet_article(page, tweet_url)
    payload = detail.get("payload")
    if payload is None:
        payload = _wait_for_tweet_detail(page, TWEET_DETAIL_WAIT_MS)
    return article, payload


def _extract_reply_parent_chain(
    page,
    *,
    tweet_url: str,
    first_parent_url: str | None,
    first_payload: object | None,
    max_depth: int = MAX_CONVERSATION_PARENTS,
) -> List[ReplyParentContext]:
    parent_url = first_parent_url or _reply_parent_url_from_payload(first_payload, tweet_url)
    if not parent_url:
        return []

    contexts: List[ReplyParentContext] = []
    seen_ids = {_status_id_from_url(tweet_url)}
    while parent_url and len(contexts) < max_depth:
        canonical_url = _canonical_status_url(parent_url) or parent_url
        parent_id = _status_id_from_url(canonical_url)
        if parent_id:
            if parent_id in seen_ids:
                break
            seen_ids.add(parent_id)

        article, payload = _load_tweet_detail_page(page, canonical_url)
        if article is None:
            contexts.append(ReplyParentContext(canonical_url))
            break

        try:
            parts = _extract_tweet_parts(article, canonical_url, page=page)
        except Exception:
            contexts.append(ReplyParentContext(canonical_url))
            break

        contexts.append(ReplyParentContext(canonical_url, parts=parts))
        next_parent_url = _reply_parent_url_from_payload(payload, canonical_url)
        if _is_self_thread_parent(parts, next_parent_url):
            break
        parent_url = next_parent_url

    contexts.reverse()
    return contexts


def _should_download_reply_chain(
    *,
    capture_source: str,
    posted_kind: str | None,
    parent_url: str | None,
    target_author_handle: str | None,
) -> bool:
    if not parent_url:
        return False
    if posted_kind == "reply":
        return True
    if capture_source != "liked":
        return False
    parent_handle = _handle_from_status_url(parent_url)
    target_handle = _normalize_handle_for_match(target_author_handle)
    if parent_handle and target_handle and parent_handle == target_handle:
        return False
    return True


def _is_self_thread_parent(parts: TweetParts, parent_url: str | None) -> bool:
    parent_handle = _handle_from_status_url(parent_url)
    current_handle = _normalize_handle_for_match(parts.author_handle)
    return bool(parent_handle and current_handle and parent_handle == current_handle)


def _normalize_link_for_match(url: str) -> str:
    return url.strip().rstrip("/").lower()


def _should_append_external_link(body_text: str, external_link: str | None) -> bool:
    if not external_link:
        return False
    if not body_text:
        return True
    normalized = _normalize_link_for_match(external_link)
    return normalized not in body_text.lower()


def _build_single_tweet_markdown(
    parts: TweetParts,
    tweet_url: str,
    *,
    capture_source: str = "liked",
    posted_kind: str | None = None,
    reply_parent_context: ReplyParentContext | None = None,
    reply_parent_contexts: Sequence[ReplyParentContext] | None = None,
    reply_parent_url: str | None = None,
) -> str:
    source = _normalize_capture_source(capture_source)
    kind = _normalize_posted_kind(posted_kind) if source == "posted" else None
    parent_contexts = list(reply_parent_contexts or [])
    if not parent_contexts and reply_parent_context is not None:
        parent_contexts = [reply_parent_context]
    if source != "liked" and kind != "reply":
        parent_contexts = []
        reply_parent_context = None
        reply_parent_url = None
    if parent_contexts:
        reply_parent_url = parent_contexts[-1].url
    title = _build_title(parts.author_name, parts.author_handle)
    front_matter: dict[str, object] = {
        "source": "tweet",
        "tweet_url": tweet_url,
        "tweet_capture_source": source,
    }
    if kind:
        front_matter["tweet_posted_kind"] = kind
    if reply_parent_url:
        front_matter["tweet_reply_to_url"] = reply_parent_url
        front_matter["tweet_reply_context_included"] = any(
            context.parts is not None for context in parent_contexts
        )
    if parent_contexts:
        front_matter["tweet_conversation_count"] = len(parent_contexts) + 1
    if parts.author_handle:
        front_matter["tweet_author"] = parts.author_handle
    if parts.author_name:
        front_matter["tweet_author_name"] = parts.author_name

    md_lines = [
        *front_matter_block(front_matter).splitlines(),
        f"# {title}",
        "",
        f"[View on X]({tweet_url})",
    ]
    if parts.avatar_url:
        md_lines.extend(["", f"![avatar]({parts.avatar_url})"])

    parent_lines = _reply_parent_contexts_markdown_lines(parent_contexts)
    if parent_lines:
        md_lines.extend(parent_lines)
        response_heading = "Mi respuesta" if source == "posted" and kind == "reply" else "Tweet favorito"
        md_lines.extend(["", "---", "", f"#### {response_heading}"])

    _append_tweet_content_lines(md_lines, parts, strip_author=bool(parent_lines))

    markdown = "\n".join(md_lines).strip() + "\n"
    return enrich_markdown_metadata(
        markdown,
        source_url=tweet_url,
        title=title,
        extra={"tweet_id": _status_id_from_url(tweet_url) or ""},
    )


def _build_thread_markdown(
    thread_parts: List[tuple[str | None, TweetParts]],
    tweet_url: str,
    target_parts: TweetParts,
    *,
    author_handle: str | None,
    capture_source: str = "liked",
    posted_kind: str | None = None,
) -> str:
    normalized_capture_source = _normalize_capture_source(capture_source)
    normalized_posted_kind = (
        _normalize_posted_kind(posted_kind) if normalized_capture_source == "posted" else None
    )
    title = _build_title(target_parts.author_name, author_handle, kind="Thread")
    front_matter: dict[str, object] = {
        "source": "tweet",
        "tweet_url": tweet_url,
        "tweet_capture_source": normalized_capture_source,
        "tweet_thread": True,
        "tweet_thread_count": len(thread_parts),
    }
    if normalized_posted_kind:
        front_matter["tweet_posted_kind"] = normalized_posted_kind
    if author_handle:
        front_matter["tweet_author"] = author_handle
    if target_parts.author_name:
        front_matter["tweet_author_name"] = target_parts.author_name

    md_lines = [*front_matter_block(front_matter).splitlines(), f"# {title}"]
    if target_parts.avatar_url:
        md_lines.extend(["", f"![avatar]({target_parts.avatar_url})"])

    for section_url, parts in thread_parts:
        link_url = section_url or tweet_url
        md_lines.extend(["", "---", f"[View on X]({link_url})"])
        _append_tweet_content_lines(md_lines, parts, strip_author=True)

    markdown = "\n".join(md_lines).strip() + "\n"
    return enrich_markdown_metadata(
        markdown,
        source_url=tweet_url,
        title=title,
        extra={"tweet_id": _status_id_from_url(tweet_url) or ""},
    )


def fetch_tweet_thread_markdown(
    url: str,
    *,
    headless: bool = True,
    storage_state: Path | None = None,
    context_author_handle: str | None = None,
    context_time_text: str | None = None,
    context_time_datetime: str | None = None,
    capture_source: str = "liked",
    posted_kind: str | None = None,
    reply_parent_url: str | None = None,
) -> tuple[str, str]:
    """Return (markdown, filename) for a tweet, expanding threads when possible."""
    if sync_playwright is None:
        raise RuntimeError(
            "playwright is not installed. Run 'pip install playwright' and "
            "'playwright install chromium' to use this tool."
        )
    normalized_capture_source = _normalize_capture_source(capture_source)
    normalized_posted_kind = (
        _normalize_posted_kind(posted_kind) if normalized_capture_source == "posted" else None
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
        _wait_with_log(page, WAIT_MS, "load the tweet")
        _raise_if_access_issue(page)

        article = _locate_tweet_article(page, url)
        if article is None:
            _raise_if_access_issue(page)
            raise RuntimeError(
                "Could not find the post <article>. "
                "It may require login or be unavailable."
            )

        target_parts = _extract_tweet_parts(article, url, page=page, quoted_status_id=quoted_status["id"])
        target_time_text, target_time_datetime = _extract_time_details(article)
        effective_author_handle, effective_time_text, effective_time_datetime = _resolve_thread_context(
            context_author_handle,
            context_time_text,
            context_time_datetime,
            target_parts.author_handle,
            target_time_text,
            target_time_datetime,
        )
        filename = _build_filename(
            url,
            target_parts.author_handle,
            capture_source=normalized_capture_source,
        )

        thread_payload = tweet_detail.get("payload")
        if thread_payload is None:
            thread_payload = _wait_for_tweet_detail(page, TWEET_DETAIL_WAIT_MS)
            if thread_payload is not None:
                tweet_detail["payload"] = thread_payload
        parent_url = reply_parent_url or _reply_parent_url_from_payload(thread_payload, url)
        if _should_download_reply_chain(
            capture_source=normalized_capture_source,
            posted_kind=normalized_posted_kind,
            parent_url=parent_url,
            target_author_handle=target_parts.author_handle,
        ):
            parent_contexts = _extract_reply_parent_chain(
                page,
                tweet_url=url,
                first_parent_url=parent_url,
                first_payload=thread_payload,
            )
            browser.close()
            return _build_single_tweet_markdown(
                target_parts,
                url,
                capture_source=normalized_capture_source,
                posted_kind=normalized_posted_kind,
                reply_parent_contexts=parent_contexts,
                reply_parent_url=parent_url,
            ), filename

        if not effective_author_handle or not (effective_time_text or effective_time_datetime):
            browser.close()
            return _build_single_tweet_markdown(
                target_parts,
                url,
                capture_source=normalized_capture_source,
                posted_kind=normalized_posted_kind,
            ), filename

        if thread_payload is None:
            thread_payload = _wait_for_tweet_detail(page, TWEET_DETAIL_WAIT_MS)
            if thread_payload is not None:
                tweet_detail["payload"] = thread_payload
        thread_marker = _has_thread_marker(article)
        thread_ids = _extract_thread_ids_from_payload(
            thread_payload,
            author_handle=effective_author_handle,
            anchor_time_datetime=effective_time_datetime,
        )

        articles = page.locator("article")
        total = articles.count()
        if total <= 1 and (not thread_ids or len(thread_ids) <= 1):
            if thread_payload is None and thread_marker:
                _wait_with_log(page, WAIT_MS, "load the thread")
                thread_payload = tweet_detail.get("payload")
                thread_marker = _has_thread_marker(article)
                thread_ids = _extract_thread_ids_from_payload(
                    thread_payload,
                    author_handle=effective_author_handle,
                    anchor_time_datetime=effective_time_datetime,
                )
                articles = page.locator("article")
                total = articles.count()
            if total <= 1 and (not thread_ids or len(thread_ids) <= 1):
                browser.close()
                return _build_single_tweet_markdown(
                    target_parts,
                    url,
                    capture_source=normalized_capture_source,
                    posted_kind=normalized_posted_kind,
                ), filename

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
            author_handle=effective_author_handle,
            time_text=effective_time_text,
            anchor_time_datetime=effective_time_datetime,
        )

        if thread_ids and target_id and target_id in thread_ids:
            target_idx = thread_ids.index(target_id)
        if thread_ids and len(thread_ids) > len(selected_indices):
            primary_handle = effective_author_handle
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
                _wait_with_log(page, WAIT_MS, "load a tweet from the thread")
                art = _locate_tweet_article(page, section_url)
                if art is None:
                    continue
                parts = _extract_tweet_parts(art, section_url, page=page)
                thread_parts.append((section_url, parts))
        else:
            if len(selected_indices) <= 1:
                browser.close()
                return _build_single_tweet_markdown(
                    target_parts,
                    url,
                    capture_source=normalized_capture_source,
                    posted_kind=normalized_posted_kind,
                ), filename

            primary_handle = effective_author_handle
            thread_parts = []
            for idx in selected_indices:
                art = articles.nth(idx)
                section_url = url if idx == target_idx else _extract_article_status_url(art, primary_handle)
                extract_url = section_url or url
                parts = target_parts if idx == target_idx else _extract_tweet_parts(art, extract_url, page=page)
                thread_parts.append((section_url, parts))

        if len(thread_parts) <= 1:
            browser.close()
            return _build_single_tweet_markdown(
                target_parts,
                url,
                capture_source=normalized_capture_source,
                posted_kind=normalized_posted_kind,
            ), filename

        print(f"🧵 Thread downloaded ({len(thread_parts)} tweets).")
        markdown = _build_thread_markdown(
            thread_parts,
            url,
            target_parts,
            author_handle=effective_author_handle,
            capture_source=normalized_capture_source,
            posted_kind=normalized_posted_kind,
        )
        browser.close()
        return markdown, filename


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a public tweet and save it as pipeline-ready Markdown.",
    )
    parser.add_argument("url", help="Tweet URL on https://x.com/...")
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
        "--capture-source",
        choices=sorted(VALID_CAPTURE_SOURCES),
        default="liked",
        help="Mark the downloaded Markdown as liked or posted (default: liked).",
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
    storage_state = cfg.TWEET_LIKES_STATE if cfg.TWEET_LIKES_STATE.exists() else None

    try:
        markdown, auto_filename = fetch_tweet_thread_markdown(
            args.url,
            headless=args.headless,
            storage_state=storage_state,
            capture_source=args.capture_source,
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
