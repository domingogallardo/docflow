"""Extract original publication dates from clipped article content."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from utils.markdown_utils import split_front_matter

ORIGINAL_PUBLISHED_AT_KEY = "docflow_original_published_at"
ORIGINAL_PUBLISHED_SOURCE_KEY = "docflow_original_published_source"

_JSON_LD_DATE_KEYS = (
    "datePublished",
    "dateCreated",
    "uploadDate",
    "dateModified",
)
_META_DATE_KEYS = (
    ("property", "article:published_time"),
    ("property", "og:published_time"),
    ("name", "article:published_time"),
    ("name", "datePublished"),
    ("name", "datepublished"),
    ("name", "date"),
    ("name", "pubdate"),
    ("name", "publishdate"),
    ("name", "publish_date"),
    ("name", "parsely-pub-date"),
    ("name", "sailthru.date"),
    ("name", "dc.date"),
    ("name", "dc.date.issued"),
    ("name", "dcterms.date"),
    ("name", "dcterms.issued"),
    ("itemprop", "datePublished"),
    ("itemprop", "dateCreated"),
)
_VISIBLE_MONTHS = {
    "january": 1,
    "jan": 1,
    "jan.": 1,
    "february": 2,
    "feb": 2,
    "feb.": 2,
    "march": 3,
    "mar": 3,
    "mar.": 3,
    "april": 4,
    "apr": 4,
    "apr.": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "jun.": 6,
    "july": 7,
    "jul": 7,
    "jul.": 7,
    "august": 8,
    "aug": 8,
    "aug.": 8,
    "september": 9,
    "sep": 9,
    "sep.": 9,
    "sept": 9,
    "sept.": 9,
    "october": 10,
    "oct": 10,
    "oct.": 10,
    "november": 11,
    "nov": 11,
    "nov.": 11,
    "december": 12,
    "dec": 12,
    "dec.": 12,
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
_VISIBLE_MONTH_RE = "|".join(re.escape(month) for month in sorted(_VISIBLE_MONTHS, key=len, reverse=True))
_VISIBLE_DATE_PATTERNS = (
    re.compile(rf"\b({_VISIBLE_MONTH_RE})\s+(\d{{1,2}})(?:st|nd|rd|th)?[,]?\s+((?:19|20)\d{{2}})\b", re.I),
    re.compile(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:de\s+)?({_VISIBLE_MONTH_RE})(?:\s+de)?[,]?\s+((?:19|20)\d{{2}})\b",
        re.I,
    ),
    re.compile(r"\b((?:19|20)\d{2})[-/.]([01]?\d)[-/.]([0-3]?\d)\b"),
    re.compile(r"\b([0-3]?\d)[-/]([01]?\d)[-/]((?:19|20)\d{2})\b"),
)
_VISIBLE_CONTAINER_SELECTORS = (
    "article",
    "main",
    "[role='main']",
    ".post",
    ".entry",
    ".article",
    ".content",
)
_VISIBLE_SKIP_TAGS = ("script", "style", "noscript", "svg", "nav", "footer", "aside", "form")
_VISIBLE_LINE_LIMIT = 10
_VISIBLE_TOTAL_CHAR_LIMIT = 900
_VISIBLE_LINE_CHAR_LIMIT = 180
_MARKDOWN_INITIAL_LINE_LIMIT = 3
_MARKDOWN_LINE_CHAR_LIMIT = 130
_MIN_ORIGINAL_DATE = date(1990, 1, 1)
_MARKDOWN_DATE_CONTEXT_RE = re.compile(
    r"\b("
    r"published|posted|publicado|publicada|pubblicato|submitted|"
    r"first published|written by|by|por"
    r")\b",
    re.I,
)
_MARKDOWN_DATE_NOISE_RE = re.compile(
    r"\b("
    r"updated|retrieved|accessed|archived|accepted|doi|last modified|"
    r"ultima entrada|\u00faltima entrada|cover date|episode aired|temporada|season|"
    r"compartida|tweet|twitter|forecast|created by|reported|results as of"
    r")\b",
    re.I,
)


@dataclass(frozen=True)
class DateCandidate:
    value: str
    source: str


def _normalize_date_value(raw_value: object) -> str | None:
    if isinstance(raw_value, list):
        for item in raw_value:
            normalized = _normalize_date_value(item)
            if normalized:
                return normalized
        return None

    value = str(raw_value or "").strip()
    if not value:
        return None

    value = re.sub(r"\s+", " ", value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            return None

    iso_value = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_value)
    except ValueError:
        parsed = None
    if parsed is not None:
        return _format_datetime_or_date(parsed)

    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        parsed = None
    if parsed is not None:
        return _format_datetime_or_date(parsed)

    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass

    match = re.search(r"\b((?:19|20)\d{2})[-/.]([01]\d)[-/.]([0-3]\d)\b", value)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
        except ValueError:
            return None

    return None


def _format_datetime_or_date(parsed: datetime) -> str:
    if parsed.hour == parsed.minute == parsed.second == parsed.microsecond == 0:
        return parsed.date().isoformat()
    if parsed.tzinfo is None:
        return parsed.isoformat(timespec="seconds")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json_ld_date_candidate(soup: BeautifulSoup) -> DateCandidate | None:
    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        text = script.string or script.get_text()
        if not text.strip():
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        candidate = _date_from_json_value(payload)
        if candidate:
            return candidate
    return None


def _date_from_json_value(value: object) -> DateCandidate | None:
    if isinstance(value, list):
        for item in value:
            candidate = _date_from_json_value(item)
            if candidate:
                return candidate
        return None

    if not isinstance(value, dict):
        return None

    for key in _JSON_LD_DATE_KEYS:
        normalized = _normalize_date_value(value.get(key))
        if normalized:
            return DateCandidate(normalized, f"json_ld:{key}")

    graph = value.get("@graph")
    candidate = _date_from_json_value(graph)
    if candidate:
        return candidate

    for nested in value.values():
        if isinstance(nested, (dict, list)):
            candidate = _date_from_json_value(nested)
            if candidate:
                return candidate
    return None


def _meta_date_candidate(soup: BeautifulSoup) -> DateCandidate | None:
    meta_tags = soup.find_all("meta")
    for attr, expected in _META_DATE_KEYS:
        for tag in meta_tags:
            actual = str(tag.get(attr, "")).strip().lower()
            if actual != expected.lower():
                continue
            normalized = _normalize_date_value(tag.get("content"))
            if normalized:
                return DateCandidate(normalized, f"meta:{attr}={expected}")
    return None


def _time_date_candidate(soup: BeautifulSoup) -> DateCandidate | None:
    for tag in soup.find_all("time"):
        for attr in ("datetime", "title"):
            normalized = _normalize_date_value(tag.get(attr))
            if normalized:
                return DateCandidate(normalized, f"time:{attr}")
        normalized = _normalize_date_value(tag.get_text(" ", strip=True))
        if normalized:
            return DateCandidate(normalized, "time:text")
    return None


def _visible_text_date_candidate(soup: BeautifulSoup) -> DateCandidate | None:
    root = _visible_text_root(soup)
    if root is None:
        return None

    for line in _initial_visible_lines(root):
        normalized = _parse_visible_text_date(line)
        if normalized:
            return DateCandidate(normalized, "visible_text:article_start")
    return None


def _visible_text_root(soup: BeautifulSoup):
    for selector in _VISIBLE_CONTAINER_SELECTORS:
        found = soup.select_one(selector)
        if found is not None:
            return found
    return soup.body or soup


def _initial_visible_lines(root) -> list[str]:
    for tag in root.find_all(_VISIBLE_SKIP_TAGS):
        tag.decompose()

    lines: list[str] = []
    total_chars = 0
    for raw_text in root.stripped_strings:
        line = re.sub(r"\s+", " ", raw_text).strip()
        if len(line) < 6 or len(line) > _VISIBLE_LINE_CHAR_LIMIT:
            continue

        lines.append(line)
        total_chars += len(line)
        if len(lines) >= _VISIBLE_LINE_LIMIT or total_chars >= _VISIBLE_TOTAL_CHAR_LIMIT:
            break
    return lines


def _parse_visible_text_date(line: str) -> str | None:
    for index, pattern in enumerate(_VISIBLE_DATE_PATTERNS):
        match = pattern.search(line)
        if not match:
            continue

        if index == 0:
            return _date_from_parts(match.group(3), _VISIBLE_MONTHS[match.group(1).lower()], match.group(2))
        if index == 1:
            return _date_from_parts(match.group(3), _VISIBLE_MONTHS[match.group(2).lower()], match.group(1))
        if index == 2:
            return _date_from_parts(match.group(1), match.group(2), match.group(3))
        return _date_from_parts(match.group(3), match.group(2), match.group(1))
    return None


def extract_original_published_date_from_markdown(markdown: str) -> DateCandidate | None:
    _, body = split_front_matter(markdown)
    for line in _initial_markdown_text_lines(body):
        if _MARKDOWN_DATE_NOISE_RE.search(line) and not _MARKDOWN_DATE_CONTEXT_RE.search(line):
            continue
        normalized = _parse_visible_text_date(line)
        if not normalized or not _is_supported_original_date(normalized):
            continue
        if _looks_like_markdown_publication_line(line):
            return DateCandidate(normalized, "markdown_text:first_lines")
    return None


def _initial_markdown_text_lines(body: str) -> list[str]:
    lines: list[str] = []
    for raw_line in body.splitlines():
        line = _clean_markdown_line(raw_line)
        if not line:
            continue
        lines.append(line)
        if len(lines) >= _MARKDOWN_INITIAL_LINE_LIMIT:
            break
    return lines


def _clean_markdown_line(raw_line: str) -> str:
    line = raw_line.strip()
    if not line:
        return ""
    if line.startswith(("#", ">", "!", "<!--")):
        return ""
    if "http://" in line or "https://" in line:
        return ""

    line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)
    line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
    line = re.sub(r"[*_`~]+", "", line)
    line = re.sub(r"\s+", " ", line).strip(" -\t")
    if len(line) < 6 or len(line) > _MARKDOWN_LINE_CHAR_LIMIT:
        return ""
    return line


def _looks_like_markdown_publication_line(line: str) -> bool:
    if _MARKDOWN_DATE_CONTEXT_RE.search(line):
        return True
    if len(re.findall(r"\w+", line, flags=re.UNICODE)) > 10:
        return False
    return bool(_parse_visible_text_date(line))


def _date_from_parts(year: object, month: object, day: object) -> str | None:
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except (TypeError, ValueError):
        return None


def _candidate_date(candidate: DateCandidate) -> date | None:
    try:
        return date.fromisoformat(candidate.value[:10])
    except ValueError:
        return None


def _is_today_json_ld_candidate(candidate: DateCandidate) -> bool:
    candidate_day = _candidate_date(candidate)
    return candidate.source.startswith("json_ld:") and candidate_day == date.today()


def _supported_candidate(candidate: DateCandidate | None) -> DateCandidate | None:
    if candidate and _is_supported_original_date(candidate.value):
        return candidate
    return None


def _select_html_date_candidate(soup: BeautifulSoup) -> DateCandidate | None:
    json_ld = _supported_candidate(_json_ld_date_candidate(soup))
    meta = _supported_candidate(_meta_date_candidate(soup))
    time_candidate = _supported_candidate(_time_date_candidate(soup))
    visible = _supported_candidate(_visible_text_date_candidate(soup))

    if json_ld is not None:
        if _is_today_json_ld_candidate(json_ld):
            for fallback in (time_candidate, visible, meta):
                if fallback is not None and _candidate_date(fallback) is not None:
                    return fallback
            return None
        return json_ld

    for candidate in (meta, time_candidate, visible):
        if candidate is not None:
            return candidate
    return None


def _url_date_candidate(url: str) -> DateCandidate | None:
    path = urlparse(url).path
    patterns = (
        r"/((?:19|20)\d{2})/([01]\d)/([0-3]\d)(?:/|$)",
        r"/((?:19|20)\d{2})-([01]\d)-([0-3]\d)(?:[-_/]|$)",
        r"/((?:19|20)\d{2})([01]\d)([0-3]\d)(?:[-_/]|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, path)
        if not match:
            continue
        try:
            value = date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
        except ValueError:
            continue
        candidate = DateCandidate(value, "url:path")
        if _is_supported_original_date(candidate.value):
            return candidate
    return None


def extract_original_published_date(html: str, *, url: str = "") -> DateCandidate | None:
    soup = BeautifulSoup(html, "html.parser")
    candidate = _select_html_date_candidate(soup)
    if candidate is not None:
        return candidate
    if url:
        return _url_date_candidate(url)
    return None


def _is_supported_original_date(value: str) -> bool:
    try:
        parsed = date.fromisoformat(value[:10])
    except ValueError:
        return False
    return _MIN_ORIGINAL_DATE <= parsed <= date.today()
