#!/usr/bin/env python3
"""Build a daily consolidated tweets document (Markdown + HTML).

Style:
- Small item titles (h4).
- No hour in item headers.
- Full tweet/thread content, including images from source Markdown.
"""

from __future__ import annotations

import argparse
import html
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

import config as cfg
import markdown
import utils as U
from utils.highlight_store import load_highlights_for_path, save_highlights_for_path
from utils.site_paths import rel_path_from_abs
try:
    from utils.tweet_to_markdown import strip_tweet_stats as _strip_tweet_stats
except Exception:  # pragma: no cover - defensive fallback
    def _strip_tweet_stats(text: str) -> str:
        return text


TITLE_PREFIX_RE = re.compile(r"^Tweet\s*-\s*", re.IGNORECASE)
GENERIC_H1_RE = re.compile(r"^#\s*(tweet|thread)\b", re.IGNORECASE)
X_URL_RE = re.compile(r"https?://x\.com/[^\s)]+")
VIEW_QUOTED_RE = re.compile(r"^\[view quoted tweet\]\(", re.IGNORECASE)
PARAGRAPH_TAG_RE = re.compile(r"(<p[^>]*>)(.*?)(</p>)", re.IGNORECASE | re.DOTALL)
PARAGRAPH_BLOCK_TAG_RE = re.compile(
    r"</?(?:address|article|aside|blockquote|div|dl|fieldset|figcaption|figure|footer|form|h[1-6]|header|hr|li|main|nav|ol|p|pre|section|table|tbody|td|tfoot|th|thead|tr|ul)\b",
    re.IGNORECASE,
)
DASH_LIST_LINE_RE = re.compile(r"^-\s*(.*)$")
METRIC_NUMBER_RE = re.compile(r"^\d[\d.,]*(?:\s?[kmbKMB])?$")
METRIC_TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")
_CONSOLIDATED_PREFIXES = ("Tweets ", "Consolidado Tweets ", "Consolidados Tweets ")
DEFAULT_TWEET_DAY_ROLLOVER_HOUR = 3
TWEET_DAY_ROLLOVER_ENV = "DOCFLOW_TWEET_DAY_ROLLOVER_HOUR"
METRIC_TOKEN_RE = re.compile(r"[0-9]+(?:[.,][0-9]+)?[kmb]?|[a-záéíóúñü]+", re.IGNORECASE)
METRIC_NUMBER_TOKEN_RE = re.compile(r"^\d+(?:[.,]\d+)?[kmb]?$", re.IGNORECASE)
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


@dataclass(frozen=True)
class TweetEntry:
    path: Path
    title: str
    author_label: str
    kind: str
    tweet_url: str
    body: str
    mtime: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a daily consolidated tweets file from Tweets/Tweets <YEAR>.",
    )
    parser.add_argument(
        "--day",
        required=True,
        help="Day to consolidate in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Tweets year folder (defaults to year from --day).",
    )
    parser.add_argument(
        "--tweets-dir",
        type=Path,
        help="Override tweets directory (defaults to BASE_DIR/Tweets/Tweets <YEAR>).",
    )
    parser.add_argument(
        "--output-base",
        help=(
            "Output filename stem without extension. "
            "Default: 'Tweets <DAY>'"
        ),
    )
    parser.add_argument(
        "--cleanup-if-consolidated",
        action="store_true",
        help=(
            "Delete source tweet HTML files for --day only when a consolidated "
            "file for that day already exists (source Markdown is kept)."
        ),
    )
    return parser.parse_args()


def _parse_day(day: str) -> datetime:
    try:
        return datetime.strptime(day, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit(f"❌ Invalid --day value '{day}'. Use YYYY-MM-DD.") from exc


def _tweets_dir(base_dir: Path, year: int, override: Path | None) -> Path:
    if override is not None:
        return override.expanduser()
    return base_dir / "Tweets" / f"Tweets {year}"


def _tweet_day_rollover_hour() -> int:
    raw = os.getenv(TWEET_DAY_ROLLOVER_ENV, str(DEFAULT_TWEET_DAY_ROLLOVER_HOUR)).strip()
    try:
        parsed = int(raw)
    except ValueError:
        return DEFAULT_TWEET_DAY_ROLLOVER_HOUR
    if 0 <= parsed <= 23:
        return parsed
    return DEFAULT_TWEET_DAY_ROLLOVER_HOUR


def _tweet_operational_day_from_mtime(mtime: float, *, rollover_hour: int | None = None) -> str:
    hour = _tweet_day_rollover_hour() if rollover_hour is None else rollover_hour
    dt = datetime.fromtimestamp(mtime)
    if hour > 0 and dt.hour < hour:
        dt -= timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def _collect_daily_source_markdown(tweets_dir: Path, day: str) -> list[Path]:
    selected: list[Path] = []
    for path in tweets_dir.glob("*.md"):
        if not path.is_file():
            continue
        if path.name.startswith(_CONSOLIDATED_PREFIXES):
            continue
        local_day = _tweet_operational_day_from_mtime(path.stat().st_mtime)
        if local_day == day:
            selected.append(path)
    return selected


def _consolidated_base_candidates(day: str, output_base: str | None) -> list[str]:
    candidates: list[str] = []
    if output_base:
        candidates.append(output_base)
    for base_name in (
        f"Tweets {day}",
        f"Consolidado Tweets {day}",
        f"Consolidados Tweets {day}",
    ):
        if base_name not in candidates:
            candidates.append(base_name)
    return candidates


def _find_existing_daily_consolidated_outputs(
    tweets_dir: Path,
    day: str,
    output_base: str | None,
) -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    for base_name in _consolidated_base_candidates(day, output_base):
        md_path = tweets_dir / f"{base_name}.md"
        html_path = tweets_dir / f"{base_name}.html"
        if md_path.is_file() and html_path.is_file():
            pairs.append((md_path, html_path))
    return pairs


def _extract_first_x_url(text: str) -> str:
    match = X_URL_RE.search(text)
    if match:
        return match.group(0)
    return ""


def _normalize_title(stem: str) -> str:
    return TITLE_PREFIX_RE.sub("", stem).strip() or stem


def _author_label(meta: dict[str, str]) -> str:
    parts: list[str] = []
    author_name = meta.get("tweet_author_name", "").strip()
    author_handle = meta.get("tweet_author", "").strip()
    if author_name:
        parts.append(author_name)
    if author_handle:
        parts.append(author_handle)
    return " ".join(parts) if parts else "(author not detected)"


def _entry_kind(meta: dict[str, str]) -> str:
    is_thread = meta.get("tweet_thread", "").strip().lower() == "true"
    if not is_thread:
        return "Tweet"
    try:
        count = int(meta.get("tweet_thread_count", "0") or "0")
    except ValueError:
        count = 0
    if count > 0:
        return f"Thread ({count} tweets)"
    return "Thread"


def _clean_body(body: str) -> str:
    lines = body.splitlines()

    while lines and not lines[0].strip():
        lines.pop(0)

    if lines and GENERIC_H1_RE.match(lines[0].strip()):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)

    # Remove a duplicated top "View on X" link when we already print the URL
    # in metadata. Keep all later links (thread sections, quoted tweets, etc.).
    if lines:
        first = lines[0].strip().lower()
        if first.startswith("[view on x](") or first.startswith("[ver en x]("):
            lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)

    text = _strip_stats_by_sections("\n".join(lines).strip())
    text = _blockquote_quoted_sections(text)
    text = _normalize_wrapped_dash_lists(text)
    return text + ("\n" if text else "")


def _strip_stats_by_sections(text: str) -> str:
    if not text:
        return ""

    sections: list[str] = []
    current: list[str] = []
    for raw in text.splitlines():
        if raw.strip() == "---":
            section_text = "\n".join(current).strip()
            if section_text:
                cleaned = _strip_tweet_stats(section_text).strip()
                cleaned = _strip_metric_blocks(cleaned)
                cleaned = _strip_tail_metrics(cleaned)
                if cleaned:
                    sections.append(cleaned)
            sections.append("---")
            current = []
            continue
        current.append(raw)

    section_text = "\n".join(current).strip()
    if section_text:
        cleaned = _strip_tweet_stats(section_text).strip()
        cleaned = _strip_metric_blocks(cleaned)
        cleaned = _strip_tail_metrics(cleaned)
        if cleaned:
            sections.append(cleaned)

    # Normalize separators: no duplicates, no leading/trailing separators.
    normalized: list[str] = []
    prev_sep = True
    for item in sections:
        if item == "---":
            if prev_sep:
                continue
            normalized.append(item)
            prev_sep = True
            continue
        normalized.append(item)
        prev_sep = False

    while normalized and normalized[-1] == "---":
        normalized.pop()

    return "\n\n".join(normalized).strip()


def _is_metric_tail_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False

    lowered = stripped.lower()
    metric_only = _is_metric_only_line(stripped)
    if stripped == "·":
        return True
    if METRIC_NUMBER_RE.match(stripped):
        return True

    metric_keywords = (
        "retweets",
        "reposts",
        "quotes",
        "likes",
        "bookmarks",
        "replies",
        "me gusta",
        "citas",
        "marcadores",
        "respuestas",
    )
    if metric_only and any(token in lowered for token in metric_keywords):
        return True
    if metric_only and ("views" in lowered or "visualizaciones" in lowered):
        return True
    if metric_only and ("relevant" in lowered or "relevante" in lowered):
        return True

    # Typical timestamp/date line shown before the metrics block.
    return bool(
        metric_only
        and METRIC_TIME_RE.search(stripped)
        and ("am" in lowered or "pm" in lowered or "·" in stripped)
    )


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


def _strip_tail_metrics(text: str) -> str:
    if not text:
        return ""

    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[-1].strip():
        lines.pop()

    removed = False
    while lines and _is_metric_tail_line(lines[-1]):
        removed = True
        lines.pop()
        while lines and not lines[-1].strip():
            lines.pop()

    if not removed:
        return text.strip()
    return "\n".join(lines).strip()


def _contains_metric_summary(line: str) -> bool:
    lowered = line.strip().lower()
    if not lowered:
        return False
    if not _is_metric_only_line(lowered):
        return False
    return ("views" in lowered or "visualizaciones" in lowered) and (
        "relevant" in lowered
        or METRIC_NUMBER_RE.search(lowered) is not None
    )


def _looks_like_metric_timestamp(line: str) -> bool:
    stripped = line.strip()
    lowered = stripped.lower()
    if not stripped:
        return False
    metric_time = _is_metric_only_line(stripped) and METRIC_TIME_RE.search(stripped)
    if not metric_time:
        return False
    if "am" in lowered or "pm" in lowered or "·" in stripped:
        return True
    months = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
              "ene", "abr", "ago", "dic")
    if any(mon in lowered for mon in months):
        return True
    return re.search(r"\b20\d{2}\b", lowered) is not None


def _has_metrics_ahead(lines: list[str], start: int, lookahead: int = 8) -> bool:
    end = min(len(lines), start + lookahead)
    for idx in range(start + 1, end):
        candidate = lines[idx].strip()
        if not candidate:
            continue
        low = candidate.lower()
        if _is_metric_only_line(low) and ("views" in low or "visualizaciones" in low or "relevant" in low):
            return True
    return False


def _strip_metric_blocks(text: str) -> str:
    if not text:
        return ""

    lines = text.splitlines()
    out: list[str] = []
    idx = 0
    while idx < len(lines):
        stripped = lines[idx].strip()
        if _contains_metric_summary(stripped):
            idx += 1
            continue

        block_start = False
        if _looks_like_metric_timestamp(stripped) and _has_metrics_ahead(lines, idx):
            block_start = True
        if stripped == "·" and _has_metrics_ahead(lines, idx):
            block_start = True

        if not block_start:
            out.append(lines[idx])
            idx += 1
            continue

        # Drop current marker line and the following metric lines.
        idx += 1
        while idx < len(lines):
            candidate = lines[idx].strip()
            if not candidate:
                idx += 1
                continue
            if _is_metric_tail_line(candidate) or _contains_metric_summary(candidate):
                idx += 1
                continue
            break

    return "\n".join(out).strip()


def _blockquote_quoted_sections(text: str) -> str:
    if not text:
        return ""

    lines = text.splitlines()
    out: list[str] = []
    in_quoted_section = False

    for line in lines:
        stripped = line.strip()

        if VIEW_QUOTED_RE.match(stripped):
            if out and out[-1].strip():
                out.append("")
            out.append("###### Tweet citado")
            out.append(line)
            in_quoted_section = True
            continue

        if in_quoted_section and stripped == "---":
            in_quoted_section = False
            out.append("")
            out.append("---")
            continue

        if in_quoted_section and stripped.lower() == "quote":
            continue

        out.append(line)

    return "\n".join(out).strip()


def _normalize_wrapped_dash_lists(text: str) -> str:
    """Normalize wrapped dash bullets into proper Markdown list items."""
    if not text:
        return ""

    lines = text.splitlines()
    merged: list[str] = []
    idx = 0

    while idx < len(lines):
        raw = lines[idx]
        stripped = raw.strip()
        if stripped == "":
            merged.append("")
            idx += 1
            continue
        if stripped == "---":
            merged.append(raw)
            idx += 1
            continue

        # Preserve indented lines (nested lists / code blocks) as-is.
        if raw.lstrip() != raw:
            merged.append(raw)
            idx += 1
            continue

        bullet_match = DASH_LIST_LINE_RE.match(stripped)
        if bullet_match is None:
            merged.append(raw)
            idx += 1
            continue

        first_part = (bullet_match.group(1) or "").strip()
        parts: list[str] = [first_part] if first_part else []
        cursor = idx + 1

        while cursor < len(lines):
            nxt = lines[cursor]
            nxt_stripped = nxt.strip()
            if nxt_stripped == "" or nxt_stripped == "---":
                break
            if nxt.lstrip() != nxt:
                break
            if DASH_LIST_LINE_RE.match(nxt_stripped):
                break
            if nxt_stripped.startswith("#"):
                break
            if nxt_stripped.startswith("<") and not nxt_stripped.startswith("@"):
                break
            parts.append(nxt_stripped)
            cursor += 1

        if parts:
            merged.append(f"- {' '.join(parts)}")

        idx = cursor

    normalized: list[str] = []
    for i, line in enumerate(merged):
        current = line.strip()
        next_line = merged[i + 1].strip() if i + 1 < len(merged) else ""
        normalized.append(line)

        # Start a list after a regular line when the next one is a dash bullet.
        if (
            current
            and current != "---"
            and not current.startswith("- ")
            and next_line.startswith("- ")
        ):
            normalized.append("")

        # End a list before resuming normal paragraph text.
        if (
            current.startswith("- ")
            and next_line
            and next_line != "---"
            and not next_line.startswith("- ")
        ):
            normalized.append("")

        if current.endswith(":") and next_line.startswith("- "):
            normalized.append("")
        if current.startswith("- ") and next_line.endswith(":") and not next_line.startswith("- "):
            normalized.append("")

    return "\n".join(normalized).strip()


def _preserve_paragraph_line_breaks(html_fragment: str) -> str:
    """Keep source hard line breaks only inside plain <p> blocks."""
    if not html_fragment or "<p" not in html_fragment.lower():
        return html_fragment

    def _replace(match: re.Match[str]) -> str:
        open_tag, content, close_tag = match.groups()
        normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        if "\n" not in normalized:
            return match.group(0)
        if "<br" in normalized.lower():
            return match.group(0)
        if PARAGRAPH_BLOCK_TAG_RE.search(normalized):
            return match.group(0)

        with_breaks = normalized.replace("\n", "<br>\n")
        with_breaks = re.sub(r"^(?:<br>\n)+", "", with_breaks)
        with_breaks = re.sub(r"(?:<br>\n)+$", "", with_breaks)
        return f"{open_tag}{with_breaks}{close_tag}"

    return PARAGRAPH_TAG_RE.sub(_replace, html_fragment)


def _markdown_to_html_fragment(md_text: str) -> str:
    if not md_text.strip():
        return ""

    linked_text = U.convert_urls_to_links(md_text)

    try:
        rendered = markdown.markdown(
            linked_text,
            extensions=[
                "fenced_code",
                "tables",
                "attr_list",
            ],
            output_format="html5",
        )
        return _preserve_paragraph_line_breaks(rendered)
    except Exception:
        safe = html.escape(linked_text).replace("\n", "<br>\n")
        return f"<p>{safe}</p>"


def _render_full_html(md_text: str, title: str) -> str:
    body_html = markdown.markdown(
        md_text,
        extensions=[
            "fenced_code",
            "tables",
            "toc",
            "attr_list",
        ],
        output_format="html5",
    )
    safe_title = html.escape(title)
    return (
        "<!DOCTYPE html>\n"
        "<html>\n<head>\n<meta charset=\"UTF-8\">\n"
        f"<title>{safe_title}</title>\n"
        "</head>\n<body>\n"
        f"{body_html}\n"
        "</body>\n</html>\n"
    )


def _build_entry(path: Path) -> TweetEntry:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    meta, body = U.split_front_matter(raw)
    tweet_url = meta.get("tweet_url", "").strip() or _extract_first_x_url(raw)

    if not body.strip():
        body = raw
    cleaned_body = _clean_body(body)

    return TweetEntry(
        path=path,
        title=_normalize_title(path.stem),
        author_label=_author_label(meta),
        kind=_entry_kind(meta),
        tweet_url=tweet_url,
        body=cleaned_body,
        mtime=path.stat().st_mtime,
    )


def _set_mtime(path: Path, mtime: float) -> None:
    st = path.stat()
    os.utime(path, (st.st_atime, mtime))


def _path_key(path: Path) -> str:
    return str(path.resolve())


def _state_base_dir_for_tweets_dir(tweets_dir: Path) -> Path | None:
    resolved = tweets_dir.resolve()
    if resolved.parent.name == "Tweets":
        return resolved.parent.parent

    try:
        configured = Path(cfg.BASE_DIR).expanduser().resolve()
    except Exception:
        return None

    try:
        resolved.relative_to(configured)
    except ValueError:
        return None
    return configured


def _safe_rel_path(base_dir: Path | None, path: Path) -> str | None:
    if base_dir is None:
        return None
    try:
        return rel_path_from_abs(base_dir, path)
    except Exception:
        return None


def _highlight_signature(item: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(item.get("text") or "").strip(),
        str(item.get("prefix") or ""),
        str(item.get("suffix") or ""),
    )


def _merge_highlight_lists(*highlight_lists: list[dict[str, object]]) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = []
    seen_signatures: set[tuple[str, str, str]] = set()
    used_ids: set[str] = set()

    for items in highlight_lists:
        for item in items:
            if not isinstance(item, dict):
                continue
            signature = _highlight_signature(item)
            if not signature[0] or signature in seen_signatures:
                continue

            copied = dict(item)
            highlight_id = str(copied.get("id") or "").strip()
            if not highlight_id or highlight_id in used_ids:
                copied["id"] = ""
            else:
                used_ids.add(highlight_id)

            merged.append(copied)
            seen_signatures.add(signature)

    return merged


def _source_tweet_html_paths(
    source_markdown: Iterable[Path],
    *,
    keep_paths: Iterable[Path] = (),
) -> list[Path]:
    keep = {_path_key(path) for path in keep_paths}
    html_paths: list[Path] = []

    for md_path in source_markdown:
        if _path_key(md_path) in keep:
            continue

        html_path = md_path.with_suffix(".html")
        if html_path == md_path:
            continue
        if _path_key(html_path) in keep:
            continue
        html_paths.append(html_path)

    return html_paths


def _port_source_highlights_to_consolidated(
    tweets_dir: Path,
    source_markdown: Iterable[Path],
    *,
    destination_html: Path | None,
    keep_paths: Iterable[Path] = (),
) -> tuple[int, int]:
    if destination_html is None:
        return 0, 0

    base_dir = _state_base_dir_for_tweets_dir(tweets_dir)
    destination_rel = _safe_rel_path(base_dir, destination_html)
    if destination_rel is None:
        return 0, 0

    source_html_paths = _source_tweet_html_paths(source_markdown, keep_paths=keep_paths)
    if not source_html_paths:
        return 0, 0

    source_payloads: list[dict[str, object]] = []
    source_rel_paths: list[str] = []
    moved_total = 0

    for html_path in source_html_paths:
        rel_path = _safe_rel_path(base_dir, html_path)
        if rel_path is None:
            continue
        payload = load_highlights_for_path(base_dir, rel_path)
        highlights = payload.get("highlights")
        if not isinstance(highlights, list) or not highlights:
            continue
        source_payloads.append(payload)
        source_rel_paths.append(rel_path)
        moved_total += len(highlights)

    if not source_payloads:
        return 0, 0

    destination_payload = load_highlights_for_path(base_dir, destination_rel)
    destination_highlights = destination_payload.get("highlights")
    if not isinstance(destination_highlights, list):
        destination_highlights = []

    merged_highlights = _merge_highlight_lists(
        destination_highlights,
        *[
            payload.get("highlights")
            for payload in source_payloads
            if isinstance(payload.get("highlights"), list)
        ],
    )
    save_highlights_for_path(
        base_dir,
        destination_rel,
        {
            "title": str(destination_payload.get("title") or ""),
            "url": str(destination_payload.get("url") or ""),
            "highlights": merged_highlights,
        },
    )

    for rel_path in source_rel_paths:
        save_highlights_for_path(base_dir, rel_path, {"highlights": []})

    return len(source_rel_paths), moved_total


def _delete_daily_source_html_only(
    source_markdown: Iterable[Path],
    *,
    keep_paths: Iterable[Path] = (),
) -> int:
    deleted_html = 0

    for html_path in _source_tweet_html_paths(source_markdown, keep_paths=keep_paths):
        if html_path.is_file():
            html_path.unlink()
            deleted_html += 1

    return deleted_html


def _cleanup_after_daily_consolidation(
    tweets_dir: Path,
    source_markdown: Iterable[Path],
    *,
    keep_paths: Iterable[Path],
    destination_html: Path | None,
) -> tuple[int, int, int]:
    migrated_docs, migrated_highlights = _port_source_highlights_to_consolidated(
        tweets_dir,
        source_markdown,
        destination_html=destination_html,
        keep_paths=keep_paths,
    )
    deleted_html = _delete_daily_source_html_only(source_markdown, keep_paths=keep_paths)
    return deleted_html, migrated_docs, migrated_highlights


def _render_markdown(day: str, entries: Iterable[TweetEntry]) -> str:
    entry_list = list(entries)
    thread_total = sum(1 for entry in entry_list if entry.kind.startswith("Thread"))

    lines: list[str] = [
        f"# Consolidado diario de tweets ({day})",
        "",
        f"- Total de ficheros: **{len(entry_list)}**",
        f"- Hilos detectados: **{thread_total}**",
        "",
        "<style>",
        ".dg-entry {",
        "  border: 1px solid #e5e7eb;",
        "  border-radius: 12px;",
        "  padding: 14px 16px;",
        "  margin: 18px 0 24px;",
        "  background: #fff;",
        "  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);",
        "}",
        ".dg-entry-title {",
        "  margin: 0 0 8px;",
        "  font-size: 1.02rem;",
        "  line-height: 1.35;",
        "}",
        ".dg-entry-meta {",
        "  margin: 0 0 12px;",
        "  color: #374151;",
        "  font-size: 0.95rem;",
        "}",
        ".dg-entry-body hr {",
        "  border: 0;",
        "  border-top: 1px solid #d1d5db;",
        "  margin: 14px 0;",
        "}",
        ".dg-entry-body p { margin: 0 0 7px; }",
        ".dg-entry-body blockquote {",
        "  margin: 10px 0;",
        "  padding: 8px 10px;",
        "  border-left: 3px solid #9ca3af;",
        "  background: #f8fafc;",
        "}",
        ".dg-entry-body blockquote p { margin: 0 0 6px; }",
        ".dg-entry-body a { word-break: break-word; }",
        "</style>",
        "",
    ]

    for entry in entry_list:
        author = html.escape(entry.author_label)
        title = html.escape(entry.title)
        kind = html.escape(entry.kind)
        lines.append('<article class="dg-entry">')
        lines.append(f'<h4 class="dg-entry-title">{title}</h4>')

        meta = f"<strong>Autor:</strong> {author} · <strong>Tipo:</strong> {kind}"
        if entry.tweet_url:
            safe_url = html.escape(entry.tweet_url, quote=True)
            meta += f' · <a href="{safe_url}" target="_blank" rel="noopener">Abrir en X</a>'
        lines.append(f'<p class="dg-entry-meta">{meta}</p>')

        body_html = _markdown_to_html_fragment(entry.body).strip() if entry.body else ""
        lines.append('<div class="dg-entry-body">')
        if body_html:
            lines.append(body_html)
        lines.append("</div>")
        lines.append("</article>")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _run_cleanup_for_existing_daily_consolidated(
    tweets_dir: Path,
    day: str,
    output_base: str | None,
) -> int:
    pairs = _find_existing_daily_consolidated_outputs(tweets_dir, day, output_base)
    if not pairs:
        print(f"🧾 No consolidated files found for {day}; cleanup skipped")
        return 0

    source_markdown = _collect_daily_source_markdown(tweets_dir, day)
    keep_paths = [path for pair in pairs for path in pair]
    destination_html = pairs[0][1]
    deleted_html, migrated_docs, migrated_highlights = _cleanup_after_daily_consolidation(
        tweets_dir,
        source_markdown,
        keep_paths=keep_paths,
        destination_html=destination_html,
    )
    print(
        f"🧹 Cleanup completed for {day}: "
        f"removed {deleted_html} HTML (source Markdown kept)"
    )
    if migrated_docs:
        print(
            f"🟡 Migrated {migrated_highlights} highlight(s) from "
            f"{migrated_docs} source tweet HTML file(s) to {destination_html.name}"
        )
    return 0


def _build_daily_consolidated_from_markdown(
    tweets_dir: Path,
    day: str,
    output_base: str | None,
) -> int:
    source_markdown = _collect_daily_source_markdown(tweets_dir, day)
    if not source_markdown:
        print(f"🐦 No tweet Markdown files found for {day} in {tweets_dir}")
        return 0

    entries = [_build_entry(path) for path in source_markdown]
    entries.sort(key=lambda item: (item.mtime, item.title.lower()))
    latest_tweet_mtime = max(entry.mtime for entry in entries)
    consolidated_mtime = latest_tweet_mtime + 60

    output_name = output_base or f"Tweets {day}"
    md_path = tweets_dir / f"{output_name}.md"
    html_path = tweets_dir / f"{output_name}.html"

    markdown_text = _render_markdown(day, entries)
    md_path.write_text(markdown_text, encoding="utf-8")

    html_text = _render_full_html(markdown_text, md_path.stem)
    html_path.write_text(html_text, encoding="utf-8")
    U.add_margins_to_html_files(tweets_dir, file_filter=lambda path: path == html_path)

    # Keep consolidated files interleaved with tweets when listing by mtime.
    _set_mtime(md_path, consolidated_mtime)
    _set_mtime(html_path, consolidated_mtime)

    deleted_html, migrated_docs, migrated_highlights = _cleanup_after_daily_consolidation(
        tweets_dir,
        source_markdown,
        keep_paths=(md_path, html_path),
        destination_html=html_path,
    )

    print(f"✅ Consolidated Markdown generated: {md_path}")
    print(f"✅ Consolidated HTML generated: {html_path}")
    print(f"🧾 Entries included: {len(entries)}")
    print(f"🧹 Source tweet cleanup: removed {deleted_html} HTML (source Markdown kept)")
    if migrated_docs:
        print(
            f"🟡 Migrated {migrated_highlights} highlight(s) from "
            f"{migrated_docs} source tweet HTML file(s) to {html_path.name}"
        )
    return 0


def main() -> int:
    args = parse_args()
    day_dt = _parse_day(args.day)
    year = args.year or day_dt.year

    tweets_dir = _tweets_dir(cfg.BASE_DIR, year, args.tweets_dir)
    if not tweets_dir.is_dir():
        raise SystemExit(f"❌ Tweets directory not found: {tweets_dir}")

    if args.cleanup_if_consolidated:
        return _run_cleanup_for_existing_daily_consolidated(
            tweets_dir,
            args.day,
            args.output_base,
        )

    return _build_daily_consolidated_from_markdown(
        tweets_dir,
        args.day,
        args.output_base,
    )


if __name__ == "__main__":
    raise SystemExit(main())
