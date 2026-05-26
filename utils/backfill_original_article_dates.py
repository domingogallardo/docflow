"""Backfill original article publication dates from post URLs."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# Support direct execution: `python utils/backfill_original_article_dates.py ...`
if __package__ in (None, ""):
    _REPO_ROOT = Path(__file__).resolve().parents[1]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from utils.markdown_utils import split_front_matter, upsert_front_matter
from utils.site_paths import library_roots, resolve_base_dir

ORIGINAL_PUBLISHED_AT_KEY = "docflow_original_published_at"
ORIGINAL_PUBLISHED_SOURCE_KEY = "docflow_original_published_source"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 docflow-original-date-backfill/1.0"
)

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


@dataclass(frozen=True)
class DateCandidate:
    value: str
    source: str


@dataclass(frozen=True)
class BackfillResult:
    scanned: int
    with_url: int
    updated: int
    skipped_existing: int
    not_found: int
    failed: int


FetchUrl = Callable[[str, float], str]


def _iter_post_markdown_paths(base_dir: Path) -> list[Path]:
    posts_root = library_roots(base_dir)["posts"]
    if not posts_root.is_dir():
        return []

    paths: list[Path] = []
    for path in posts_root.rglob("*.md"):
        if any(part.startswith(".") for part in path.relative_to(posts_root).parts):
            continue
        if path.is_file():
            paths.append(path)
    return sorted(paths)


def _post_url_from_meta(meta: dict[str, str]) -> str:
    for key in ("docflow_post_url", "source_url"):
        value = str(meta.get(key, "")).strip()
        if value.startswith(("http://", "https://")):
            return value
    return ""


def _default_fetch_url(url: str, timeout: float) -> str:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    return response.text


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
        return DateCandidate(value, "url:path")
    return None


def extract_original_published_date(html: str, *, url: str = "") -> DateCandidate | None:
    soup = BeautifulSoup(html, "html.parser")
    for extractor in (_json_ld_date_candidate, _meta_date_candidate, _time_date_candidate):
        candidate = extractor(soup)
        if candidate:
            return candidate
    if url:
        return _url_date_candidate(url)
    return None


def backfill_original_article_dates(
    base_dir: Path,
    *,
    dry_run: bool = False,
    force: bool = False,
    limit: int | None = None,
    timeout: float = 10.0,
    fetch_url: FetchUrl | None = None,
) -> BackfillResult:
    fetch = fetch_url or _default_fetch_url
    scanned = 0
    with_url = 0
    updated = 0
    skipped_existing = 0
    not_found = 0
    failed = 0

    for path in _iter_post_markdown_paths(base_dir):
        if limit is not None and scanned >= limit:
            break
        scanned += 1

        md_text = path.read_text(encoding="utf-8", errors="replace")
        meta, _ = split_front_matter(md_text)
        url = _post_url_from_meta(meta)
        if not url:
            continue
        with_url += 1

        if meta.get(ORIGINAL_PUBLISHED_AT_KEY) and not force:
            skipped_existing += 1
            continue

        try:
            html = fetch(url, timeout)
            candidate = extract_original_published_date(html, url=url)
        except Exception as exc:
            candidate = _url_date_candidate(url)
            if candidate is None:
                failed += 1
                print(f"failed: {path.name}: {exc}")
                continue

        if candidate is None:
            not_found += 1
            continue

        if dry_run:
            updated += 1
            print(f"would update: {path.name}: {candidate.value} ({candidate.source})")
            continue

        original_stat = path.stat()
        updated_md = upsert_front_matter(
            md_text,
            {
                ORIGINAL_PUBLISHED_AT_KEY: candidate.value,
                ORIGINAL_PUBLISHED_SOURCE_KEY: candidate.source,
            },
        )
        if updated_md != md_text:
            path.write_text(updated_md, encoding="utf-8")
            os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        updated += 1

    return BackfillResult(
        scanned=scanned,
        with_url=with_url,
        updated=updated,
        skipped_existing=skipped_existing,
        not_found=not_found,
        failed=failed,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill original article publication dates in post Markdown.")
    parser.add_argument("--base-dir", help="BASE_DIR with Posts/ and state/")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing Markdown")
    parser.add_argument("--force", action="store_true", help="Refresh dates even when already present")
    parser.add_argument("--limit", type=int, help="Maximum number of Markdown files to scan")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout per URL in seconds")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv[1:])
    base_dir = resolve_base_dir(args.base_dir)
    result = backfill_original_article_dates(
        base_dir,
        dry_run=args.dry_run,
        force=args.force,
        limit=args.limit,
        timeout=args.timeout,
    )
    mode = "would update" if args.dry_run else "updated"
    print(
        f"Original article dates: scanned {result.scanned}, "
        f"{result.with_url} with URL, {result.updated} {mode}, "
        f"{result.skipped_existing} skipped existing, {result.not_found} not found, "
        f"{result.failed} failed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
