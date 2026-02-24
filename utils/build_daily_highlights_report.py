#!/usr/bin/env python3
"""Generate a Markdown report with highlights created on a specific day."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

# Support direct execution: `python utils/build_daily_highlights_report.py ...`
if __package__ in (None, ""):
    _REPO_ROOT = Path(__file__).resolve().parents[1]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from utils.site_paths import normalize_rel_path, raw_url_for_rel_path, resolve_base_dir, state_root


_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_EDGE_PUNCT_RE = re.compile(r"^[\s\.,;:!\?\-]+|[\s\.,;:!\?\-]+$")


@dataclass(frozen=True)
class HighlightRecord:
    rel_path: str
    file_title: str
    payload_title: str
    highlight_id: str
    text: str
    prefix: str
    suffix: str
    created_at: datetime


@dataclass(frozen=True)
class TextSegment:
    start: int
    end: int
    heading: str


@dataclass(frozen=True)
class DocumentIndex:
    full_text: str
    segments: list[TextSegment]
    first_heading: str


@dataclass(frozen=True)
class RenderedHighlight:
    record: HighlightRecord
    section_title: str
    page_url: str
    highlight_url: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a Markdown report with highlights created on a specific day. "
            "The report is grouped by source file."
        ),
    )
    parser.add_argument(
        "--day",
        required=True,
        help="Day to export in YYYY-MM-DD format (local timezone).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output Markdown file path.",
    )
    parser.add_argument(
        "--base-dir",
        help="Override BASE_DIR (defaults to CLI/env/config resolution).",
    )
    parser.add_argument(
        "--intranet-base-url",
        default="http://localhost:8080",
        help="Intranet base URL used to build absolute links (default: http://localhost:8080).",
    )
    return parser.parse_args()


def _parse_day(day_value: str) -> date:
    try:
        return date.fromisoformat(day_value)
    except ValueError as exc:
        raise SystemExit(f"Invalid --day value '{day_value}'. Use YYYY-MM-DD.") from exc


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _parse_iso_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed


def _local_day(dt: datetime) -> date:
    return dt.astimezone().date()


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _escape_markdown(value: str) -> str:
    escaped = str(value or "")
    escaped = escaped.replace("\\", "\\\\")
    for char in ("`", "*", "_", "[", "]"):
        escaped = escaped.replace(char, f"\\{char}")
    return escaped


def _escape_md_blockquote(value: str) -> str:
    lines = str(value or "").splitlines()
    if not lines:
        return "> "
    return "\n".join(f"> {line}" if line else ">" for line in lines)


def _strip_edge_punctuation(value: str) -> str:
    text = str(value or "")
    return _EDGE_PUNCT_RE.sub("", text)


def _build_text_fragment(value: str) -> str:
    text = _strip_edge_punctuation(_normalize_whitespace(value))
    if not text:
        return ""

    words = text.split()
    if len(words) <= 10:
        return "#:~:text=" + quote(_strip_edge_punctuation(text), safe="")

    snippet_size = max(4, min(8, int(math.ceil(len(words) / 4))))
    if len(words) <= snippet_size * 2:
        return "#:~:text=" + quote(text, safe="")

    head = " ".join(words[:snippet_size]).rstrip(" .,;:!?-")
    tail = " ".join(words[-snippet_size:]).lstrip(" .,;:!?-")
    if not head or not tail:
        return "#:~:text=" + quote(text, safe="")
    return "#:~:text=" + quote(head, safe="") + "," + quote(tail, safe="")


def _iter_highlight_state_files(base_dir: Path) -> list[Path]:
    root = state_root(base_dir) / "highlights"
    if not root.is_dir():
        return []
    return sorted(path for path in root.rglob("*.json") if path.is_file())


def _collect_daily_highlights(base_dir: Path, target_day: date) -> dict[str, list[HighlightRecord]]:
    grouped: dict[str, list[HighlightRecord]] = {}
    for state_file in _iter_highlight_state_files(base_dir):
        payload = _load_json(state_file)
        if payload is None:
            continue

        raw_path = str(payload.get("path") or "").strip()
        if not raw_path:
            continue
        try:
            rel_path = normalize_rel_path(raw_path)
        except Exception:
            continue

        raw_highlights = payload.get("highlights")
        if not isinstance(raw_highlights, list):
            continue

        payload_title = str(payload.get("title") or "").strip()
        file_title = Path(rel_path).stem.strip() or Path(rel_path).name

        for item in raw_highlights:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            created_at = _parse_iso_datetime(item.get("created_at"))
            if created_at is None:
                continue
            if _local_day(created_at) != target_day:
                continue

            record = HighlightRecord(
                rel_path=rel_path,
                file_title=file_title,
                payload_title=payload_title,
                highlight_id=str(item.get("id") or "").strip(),
                text=text,
                prefix=str(item.get("prefix") or ""),
                suffix=str(item.get("suffix") or ""),
                created_at=created_at,
            )
            grouped.setdefault(rel_path, []).append(record)

    return grouped


def _is_skippable_text_node(node: NavigableString) -> bool:
    parent = node.parent
    while isinstance(parent, Tag):
        if parent.get("data-articlejs-ui") == "1":
            return True
        if (parent.name or "").lower() in {"script", "style", "noscript"}:
            return True
        parent = parent.parent
    return False


def _build_document_index(html_text: str) -> DocumentIndex:
    soup = BeautifulSoup(html_text, "html.parser")
    root = soup.body or soup

    segments: list[TextSegment] = []
    parts: list[str] = []
    cursor = 0
    current_heading = ""
    first_heading = ""

    for node in root.descendants:
        if isinstance(node, Tag):
            name = (node.name or "").lower()
            if name in _HEADING_TAGS:
                heading = _normalize_whitespace(node.get_text(" ", strip=True))
                if heading:
                    current_heading = heading
                    if not first_heading:
                        first_heading = heading
            continue

        if not isinstance(node, NavigableString):
            continue
        if _is_skippable_text_node(node):
            continue

        value = str(node)
        if not value:
            continue
        start = cursor
        cursor += len(value)
        parts.append(value)
        segments.append(TextSegment(start=start, end=cursor, heading=current_heading))

    return DocumentIndex(full_text="".join(parts), segments=segments, first_heading=first_heading)


def _find_match_index(full_text: str, target: str, prefix: str, suffix: str) -> int:
    if not target:
        return -1
    start = 0
    while True:
        idx = full_text.find(target, start)
        if idx < 0:
            return -1

        valid = True
        if prefix:
            actual_prefix = full_text[max(0, idx - len(prefix)) : idx]
            expected_prefix = prefix[len(prefix) - len(actual_prefix) :]
            if actual_prefix != expected_prefix:
                valid = False

        if valid and suffix:
            actual_suffix = full_text[idx + len(target) : idx + len(target) + len(suffix)]
            expected_suffix = suffix[: len(actual_suffix)]
            if actual_suffix != expected_suffix:
                valid = False

        if valid:
            return idx
        start = idx + len(target)


def _heading_for_index(segments: list[TextSegment], index: int, fallback: str) -> str:
    last_heading = ""
    for segment in segments:
        if segment.heading:
            last_heading = segment.heading
        if segment.start <= index < segment.end:
            return segment.heading or last_heading or fallback
    return last_heading or fallback


def _resolve_document_index(base_dir: Path, rel_path: str) -> DocumentIndex:
    abs_path = base_dir / Path(rel_path)
    if not abs_path.is_file():
        return DocumentIndex(full_text="", segments=[], first_heading="")
    if abs_path.suffix.lower() not in {".html", ".htm"}:
        return DocumentIndex(full_text="", segments=[], first_heading="")
    try:
        html_text = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return DocumentIndex(full_text="", segments=[], first_heading="")
    return _build_document_index(html_text)


def _intranet_page_url(rel_path: str, base_url: str) -> str:
    raw_path = raw_url_for_rel_path(rel_path)
    normalized_base = base_url.strip() or "http://localhost:8080"
    if not normalized_base.endswith("/"):
        normalized_base += "/"
    return urljoin(normalized_base, raw_path)


def _resolve_section_title(record: HighlightRecord, index: DocumentIndex) -> str:
    default_title = record.payload_title or record.file_title
    if not index.full_text:
        return default_title

    hit = _find_match_index(index.full_text, record.text, record.prefix, record.suffix)
    if hit < 0:
        return index.first_heading or default_title
    return _heading_for_index(index.segments, hit, index.first_heading or default_title)


def _build_rendered_highlights(
    base_dir: Path,
    highlights_by_path: dict[str, list[HighlightRecord]],
    intranet_base_url: str,
) -> dict[str, list[RenderedHighlight]]:
    rendered: dict[str, list[RenderedHighlight]] = {}
    index_cache: dict[str, DocumentIndex] = {}

    for rel_path, records in highlights_by_path.items():
        if rel_path not in index_cache:
            index_cache[rel_path] = _resolve_document_index(base_dir, rel_path)
        index = index_cache[rel_path]
        page_url = _intranet_page_url(rel_path, intranet_base_url)

        items: list[RenderedHighlight] = []
        for record in sorted(records, key=lambda r: (r.created_at, r.highlight_id, r.text)):
            section_title = _resolve_section_title(record, index)
            fragment = _build_text_fragment(record.text)
            highlight_url = page_url + fragment if fragment else page_url
            items.append(
                RenderedHighlight(
                    record=record,
                    section_title=section_title,
                    page_url=page_url,
                    highlight_url=highlight_url,
                )
            )
        rendered[rel_path] = items

    return rendered


def _render_markdown(day_value: date, rendered_by_path: dict[str, list[RenderedHighlight]]) -> str:
    total = sum(len(items) for items in rendered_by_path.values())
    lines = [
        f"# Daily highlights ({day_value.isoformat()})",
        "",
        f"Total highlights: **{total}**",
        "",
    ]

    if total == 0:
        lines.append("_No highlights found for this day._")
        lines.append("")
        return "\n".join(lines)

    ordered_paths = sorted(
        rendered_by_path.keys(),
        key=lambda rel: (Path(rel).stem.casefold(), rel.casefold()),
    )

    for rel_path in ordered_paths:
        items = rendered_by_path[rel_path]
        if not items:
            continue
        lines.append(f"### [{_escape_markdown(items[0].record.file_title)}](<{items[0].page_url}>)")
        lines.append("")

        grouped_by_section: dict[str, list[RenderedHighlight]] = {}
        for item in items:
            grouped_by_section.setdefault(item.section_title, []).append(item)

        for section_title, section_items in grouped_by_section.items():
            lines.append(f"**{_escape_markdown(section_title)}**")
            lines.append("")
            for item in section_items:
                lines.append(_escape_md_blockquote(item.record.text))
                lines.append("")
                lines.append(f"[Highlight](<{item.highlight_url}>)")
                lines.append("")

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    target_day = _parse_day(args.day)
    base_dir = resolve_base_dir(args.base_dir)
    output_path = args.output.expanduser()

    highlights_by_path = _collect_daily_highlights(base_dir, target_day)
    rendered_by_path = _build_rendered_highlights(base_dir, highlights_by_path, args.intranet_base_url)
    content = _render_markdown(target_day, rendered_by_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")

    total = sum(len(items) for items in rendered_by_path.values())
    print(f"Wrote report with {total} highlight(s) to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
