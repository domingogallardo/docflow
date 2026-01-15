#!/usr/bin/env python3
"""Sync highlights from the public /data/highlights/ folder into local Posts/Posts <YEAR>/highlights/.

Phase 1 sync:
- Download highlight JSON files from the public server.
- Store them under Posts/Posts <YEAR>/highlights/ based on the matching local HTML year.
- Update local .md files with invisible highlight markers (when the public HTML changes).
- Track sync metadata in a per-year sync_state.json.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Callable, Dict, Iterable, Tuple
from urllib.parse import unquote, urljoin

# Allow running as a script from the repo root or utils/.
REPO_ROOT = Path(__file__).resolve().parents[1]
repo_root_str = str(REPO_ROOT)
if repo_root_str not in sys.path:
    sys.path.insert(0, repo_root_str)

import requests

import config as cfg


YEAR_PATTERN = re.compile(r"(\d{4})$")
HIGHLIGHT_EXT = ".json"
DEFAULT_HIGHLIGHTS_PATH = "/data/highlights/"
DEFAULT_READS_PATH = "/read/"
HIGHLIGHT_START_PREFIX = "<!-- docflow:highlight"
HIGHLIGHT_START_SUFFIX = "-->"
HIGHLIGHT_END = "<!-- /docflow:highlight -->"
HIGHLIGHT_IDS_PATTERN = re.compile(r"ids=([^\s>]+)")
HIGHLIGHT_ID_PATTERN = re.compile(r"id=([^\s>]+)")
MATCH_TRANSLATION_TABLE = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u00a0": " ",
    }
)


@dataclass
class SyncSummary:
    total: int = 0
    downloaded: int = 0
    skipped: int = 0
    missing_local: int = 0
    errors: int = 0
    md_updated: int = 0
    md_missing: int = 0


def _log(message: str) -> None:
    print(message)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_base_url(value: str) -> str:
    trimmed = value.strip()
    if trimmed.endswith("/"):
        trimmed = trimmed[:-1]
    return trimmed


def normalize_highlights_path(value: str) -> str:
    path = value.strip() or DEFAULT_HIGHLIGHTS_PATH
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/"):
        path += "/"
    return path


def normalize_reads_path(value: str) -> str:
    path = value.strip() or DEFAULT_READS_PATH
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/"):
        path += "/"
    return path


def build_public_html_url(base_url: str, reads_path: str, html_name: str) -> str:
    reads_path = normalize_reads_path(reads_path)
    return urljoin(base_url + "/", reads_path.lstrip("/") + html_name)


def derive_base_url() -> str | None:
    env_base = os.getenv("HIGHLIGHTS_BASE_URL", "").strip()
    if env_base:
        return env_base
    return None


def extract_links_from_autoindex(html_text: str) -> list[str]:
    links: list[str] = []
    for match in re.finditer(r'href="([^"]+)"', html_text, flags=re.IGNORECASE):
        href = match.group(1)
        if not href or href.startswith("../"):
            continue
        href = href.split("?", 1)[0].split("#", 1)[0]
        name = href.rsplit("/", 1)[-1]
        if not name or name in (".", ".."):
            continue
        if not name.lower().endswith(HIGHLIGHT_EXT):
            continue
        links.append(name)
    return sorted(set(links))


def normalize_match_text(text: str) -> str:
    cleaned = str(text or "").translate(MATCH_TRANSLATION_TABLE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def strip_highlight_markers(md_text: str) -> str:
    cleaned = re.sub(rf"{re.escape(HIGHLIGHT_START_PREFIX)}.*?{re.escape(HIGHLIGHT_START_SUFFIX)}", "", md_text)
    cleaned = cleaned.replace(HIGHLIGHT_END, "")
    return cleaned


def extract_marker_ids(md_text: str) -> set[str]:
    ids: set[str] = set()
    for match in HIGHLIGHT_IDS_PATTERN.finditer(md_text):
        raw = match.group(1)
        for part in raw.split(","):
            value = part.strip()
            if value:
                ids.add(value)
    for match in HIGHLIGHT_ID_PATTERN.finditer(md_text):
        value = match.group(1).strip()
        if value:
            ids.add(value)
    return ids


def has_nested_highlight_markers(md_text: str) -> bool:
    start_pattern = re.compile(rf"{re.escape(HIGHLIGHT_START_PREFIX)}[^>]*{re.escape(HIGHLIGHT_START_SUFFIX)}")
    end_pattern = re.compile(re.escape(HIGHLIGHT_END))
    idx = 0
    depth = 0
    while idx < len(md_text):
        start_match = start_pattern.search(md_text, idx)
        end_match = end_pattern.search(md_text, idx)
        if not start_match and not end_match:
            return False
        if start_match and (not end_match or start_match.start() < end_match.start()):
            if depth > 0:
                return True
            depth += 1
            idx = start_match.end()
            continue
        if end_match:
            if depth > 0:
                depth -= 1
            idx = end_match.end()
            continue
    return False


def dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def split_front_matter(md_text: str) -> tuple[str, str]:
    lines = md_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return "", md_text
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            head = "\n".join(lines[: idx + 1])
            body = "\n".join(lines[idx + 1 :])
            if md_text.endswith("\n") and not body.endswith("\n"):
                body += "\n"
            return head, body
    return "", md_text


def normalize_visible_char(ch: str) -> str:
    return ch.translate(MATCH_TRANSLATION_TABLE)


def build_visible_index(md_text: str) -> tuple[str, list[int]]:
    visible_chars: list[str] = []
    mapping: list[int] = []
    idx = 0
    length = len(md_text)
    while idx < length:
        if md_text.startswith("<!--", idx):
            end = md_text.find("-->", idx + 4)
            if end == -1:
                break
            idx = end + 3
            continue
        ch = md_text[idx]
        if ch == "!" and idx + 1 < length and md_text[idx + 1] == "[":
            idx += 1
            continue
        if ch == "[":
            idx += 1
            continue
        if ch == "]":
            cursor = idx + 1
            while cursor < length and md_text[cursor].isspace():
                cursor += 1
            if cursor < length and md_text[cursor] == "(":
                depth = 1
                cursor += 1
                while cursor < length and depth > 0:
                    if md_text[cursor] == "(":
                        depth += 1
                    elif md_text[cursor] == ")":
                        depth -= 1
                    cursor += 1
                idx = cursor
                continue
            idx += 1
            continue
        if ch in ("*", "_", "`"):
            idx += 1
            continue
        if ch in ("#", "-", "+", ">") and (idx == 0 or md_text[idx - 1] == "\n"):
            cursor = idx
            while cursor < length and md_text[cursor] in ("#", "-", "+", ">"):
                cursor += 1
            if cursor < length and md_text[cursor] == " ":
                idx = cursor + 1
                continue
        if ch == "<":
            end = md_text.find(">", idx + 1)
            if end != -1:
                idx = end + 1
                continue
        visible_chars.append(ch)
        mapping.append(idx)
        idx += 1
    return "".join(visible_chars), mapping


def build_normalized_index(text: str, mapping: list[int] | None = None) -> tuple[str, list[int]]:
    normalized: list[str] = []
    normalized_map: list[int] = []
    prev_space = False
    for idx, ch in enumerate(text):
        ch = normalize_visible_char(ch)
        if ch.isspace():
            if not prev_space:
                normalized.append(" ")
                normalized_map.append(mapping[idx] if mapping else idx)
                prev_space = True
            continue
        normalized.append(ch)
        normalized_map.append(mapping[idx] if mapping else idx)
        prev_space = False
    return "".join(normalized), normalized_map


def iter_match_indices(full_text: str, target: str) -> Iterable[int]:
    start = 0
    while True:
        idx = full_text.find(target, start)
        if idx == -1:
            return
        yield idx
        start = idx + len(target)


def _context_matches(full_text: str, idx: int, target_len: int, prefix: str, suffix: str) -> bool:
    if prefix:
        window = full_text[max(0, idx - len(prefix) - 1) : idx]
        if not (window.endswith(prefix) or window.rstrip().endswith(prefix)):
            return False
    if suffix:
        window = full_text[idx + target_len : idx + target_len + len(suffix) + 1]
        if not (window.startswith(suffix) or window.lstrip().startswith(suffix)):
            return False
    return True


def _find_match_index(full_text: str, target: str, prefix: str, suffix: str) -> int:
    if not target:
        return -1
    occurrences = list(iter_match_indices(full_text, target))
    if not occurrences:
        return -1
    if len(occurrences) == 1 and not (prefix or suffix):
        return occurrences[0]
    if len(occurrences) == 1 and (prefix or suffix):
        return occurrences[0]
    if prefix or suffix:
        for idx in occurrences:
            if _context_matches(full_text, idx, len(target), prefix, suffix):
                return idx
    return occurrences[0]


def find_highlight_spans(md_body: str, highlights: list[dict]) -> list[tuple[int, int, dict]]:
    visible_text, visible_map = build_visible_index(md_body)
    normalized_body, mapping = build_normalized_index(visible_text, visible_map)
    spans: list[tuple[int, int, dict]] = []
    for item in highlights:
        target = normalize_match_text(item.get("text"))
        if not target:
            continue
        prefix = normalize_match_text(item.get("prefix"))
        suffix = normalize_match_text(item.get("suffix"))
        idx = _find_match_index(normalized_body, target, prefix, suffix)
        if idx == -1:
            continue
        end_idx = idx + len(target) - 1
        if idx >= len(mapping) or end_idx >= len(mapping):
            continue
        start_orig = mapping[idx]
        end_orig = mapping[end_idx] + 1
        spans.append((start_orig, end_orig, item))
    return spans


def merge_highlight_items(spans: list[tuple[int, int, dict]]) -> dict:
    if not spans:
        return {}
    if len(spans) == 1:
        return dict(spans[0][2])
    _, _, primary_item = max(
        spans,
        key=lambda span: (span[1] - span[0], -span[0]),
    )
    merged: dict = {}
    primary_id = str(primary_item.get("id") or "").strip()
    primary_created_at = str(primary_item.get("created_at") or "").strip()
    if primary_id:
        merged["id"] = primary_id
    if primary_created_at:
        merged["created_at"] = primary_created_at
    ids = dedupe_preserve_order(
        str(item.get("id") or "").strip() for _, _, item in spans if item.get("id")
    )
    if len(ids) > 1:
        merged["ids"] = ids
    elif ids and "id" not in merged:
        merged["id"] = ids[0]
    return merged


def consolidate_highlight_spans(spans: list[tuple[int, int, dict]]) -> list[tuple[int, int, dict]]:
    if not spans:
        return []
    spans_sorted = sorted(spans, key=lambda item: (item[0], item[1]))
    consolidated: list[tuple[int, int, dict]] = []
    current_group: list[tuple[int, int, dict]] = [spans_sorted[0]]
    current_start, current_end = spans_sorted[0][0], spans_sorted[0][1]
    for start, end, item in spans_sorted[1:]:
        if start < current_end:
            current_group.append((start, end, item))
            current_end = max(current_end, end)
            continue
        merged_item = merge_highlight_items(current_group)
        consolidated.append((current_start, current_end, merged_item))
        current_group = [(start, end, item)]
        current_start, current_end = start, end
    merged_item = merge_highlight_items(current_group)
    consolidated.append((current_start, current_end, merged_item))
    return consolidated


def build_start_marker(item: dict) -> str:
    parts: list[str] = []
    highlight_ids = item.get("ids") or []
    if isinstance(highlight_ids, str):
        highlight_ids = [value.strip() for value in highlight_ids.split(",")]
    ids_list = dedupe_preserve_order(str(value).strip() for value in highlight_ids if value)
    highlight_id = str(item.get("id") or "").strip()
    created_at = str(item.get("created_at") or "").strip()
    if len(ids_list) > 1:
        parts.append(f"ids={','.join(ids_list)}")
    if highlight_id:
        parts.append(f"id={highlight_id}")
    if created_at:
        parts.append(f"created_at={created_at}")
    if parts:
        return f"{HIGHLIGHT_START_PREFIX} {' '.join(parts)} {HIGHLIGHT_START_SUFFIX}"
    return f"{HIGHLIGHT_START_PREFIX}{HIGHLIGHT_START_SUFFIX}"


def apply_highlight_markers(md_text: str, highlights: list[dict]) -> str:
    front, body = split_front_matter(md_text)
    cleaned_body = strip_highlight_markers(body)
    spans = find_highlight_spans(cleaned_body, highlights)
    spans = consolidate_highlight_spans(spans)
    if not spans:
        combined = cleaned_body
        if front:
            combined = front + "\n" + cleaned_body.lstrip("\n")
        return combined if combined.endswith("\n") else combined + "\n"

    spans.sort(key=lambda item: (item[0], -item[1]))
    start_markers: dict[int, list[tuple[int, str]]] = {}
    end_markers: dict[int, list[tuple[int, str]]] = {}
    for start, end, item in spans:
        start_markers.setdefault(start, []).append((end, build_start_marker(item)))
        end_markers.setdefault(end, []).append((start, HIGHLIGHT_END))

    inserts: dict[int, str] = {}
    indices = set(start_markers) | set(end_markers)
    for idx in indices:
        end_list = end_markers.get(idx, [])
        start_list = start_markers.get(idx, [])
        end_list.sort(key=lambda item: item[0], reverse=True)
        start_list.sort(key=lambda item: item[0], reverse=True)
        marker_text = "".join(marker for _, marker in end_list) + "".join(marker for _, marker in start_list)
        if marker_text:
            inserts[idx] = marker_text

    updated = cleaned_body
    for idx in sorted(inserts, reverse=True):
        updated = updated[:idx] + inserts[idx] + updated[idx:]

    combined = updated
    if front:
        combined = front + "\n" + updated.lstrip("\n")
    return combined if combined.endswith("\n") else combined + "\n"


def decode_highlight_basename(encoded_name: str) -> str:
    name = encoded_name
    if name.lower().endswith(HIGHLIGHT_EXT):
        name = name[: -len(HIGHLIGHT_EXT)]
    return unquote(name)


def extract_year_from_path(path: Path) -> int | None:
    for parent in path.parents:
        match = YEAR_PATTERN.search(parent.name)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue
    return None


def build_local_html_index(
    base_dir: Path,
) -> Tuple[Dict[str, Tuple[int, Path]], Dict[str, Path], set[str]]:
    year_by_name: Dict[str, Tuple[int, Path]] = {}
    fallback_paths: Dict[str, Path] = {}
    found: set[str] = set()
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for filename in files:
            if not filename.lower().endswith((".html", ".htm")):
                continue
            found.add(filename)
            path = Path(root) / filename
            year = extract_year_from_path(path)
            if year is None:
                fallback_paths.setdefault(filename, path)
                continue
            current = year_by_name.get(filename)
            if current is None or year > current[0]:
                year_by_name[filename] = (year, path)
    return year_by_name, fallback_paths, found


def pick_local_html_info(
    basename: str,
    *,
    year_index: Dict[str, Tuple[int, Path]],
    fallback_paths: Dict[str, Path],
    known_names: set[str],
    default_year: int,
) -> Tuple[int, Path | None, bool]:
    if basename in year_index:
        year, path = year_index[basename]
        return year, path, True
    if basename in fallback_paths:
        return default_year, fallback_paths[basename], True
    if basename in known_names:
        return default_year, None, True
    return default_year, None, False


def parse_remote_updated_at(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def load_sync_state(path: Path, *, year: int, base_url: str, highlights_path: str) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("files", {})
                data["schema_version"] = 1
                data["year"] = year
                data["source"] = {"base_url": base_url, "highlights_path": highlights_path}
                return data
        except Exception:
            pass
    return {
        "schema_version": 1,
        "year": year,
        "source": {"base_url": base_url, "highlights_path": highlights_path},
        "last_run_at": "",
        "files": {},
    }


def save_sync_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def fetch_listing(url: str, *, timeout: int) -> str:
    res = requests.get(url, timeout=timeout)
    res.raise_for_status()
    return res.text


def fetch_highlight_json(url: str, *, timeout: int) -> Tuple[str, dict, str | None]:
    res = requests.get(url, timeout=timeout)
    res.raise_for_status()
    text = res.text
    payload = json.loads(text)
    return text, payload, res.headers.get("ETag")


def fetch_html_head(url: str, *, timeout: int) -> tuple[str | None, str | None]:
    res = requests.head(url, allow_redirects=True, timeout=timeout)
    res.raise_for_status()
    return res.headers.get("ETag"), res.headers.get("Last-Modified")


def sync_public_highlights(
    *,
    base_url: str,
    highlights_path: str,
    reads_path: str = DEFAULT_READS_PATH,
    base_dir: Path,
    default_year: int,
    timeout: int = 20,
    listing_fetcher: Callable[[str], str] | None = None,
    json_fetcher: Callable[[str], Tuple[str, dict, str | None]] | None = None,
    html_head_fetcher: Callable[[str], tuple[str | None, str | None]] | None = None,
) -> SyncSummary:
    summary = SyncSummary()
    listing_fetcher = listing_fetcher or (lambda url: fetch_listing(url, timeout=timeout))
    json_fetcher = json_fetcher or (lambda url: fetch_highlight_json(url, timeout=timeout))
    html_head_fetcher = html_head_fetcher or (lambda url: fetch_html_head(url, timeout=timeout))

    listing_url = urljoin(base_url + "/", highlights_path.lstrip("/"))
    _log(f"🔎 Buscando subrayados en {listing_url}")
    html_text = listing_fetcher(listing_url)
    remote_files = extract_links_from_autoindex(html_text)
    summary.total = len(remote_files)
    if not remote_files:
        _log("⚠️  No se encontraron subrayados en el listado.")
        return summary

    year_index, fallback_paths, known_names = build_local_html_index(base_dir)
    state_cache: Dict[int, dict] = {}

    for remote_name in remote_files:
        decoded_name = decode_highlight_basename(remote_name)
        year, html_path, has_local = pick_local_html_info(
            decoded_name,
            year_index=year_index,
            fallback_paths=fallback_paths,
            known_names=known_names,
            default_year=default_year,
        )
        if not has_local:
            summary.missing_local += 1
            _log(f"⚠️  No se encontro local para {decoded_name}; usando {year}.")

        dest_dir = base_dir / "Posts" / f"Posts {year}" / "highlights"
        dest_dir.mkdir(parents=True, exist_ok=True)
        state_path = dest_dir / "sync_state.json"
        state = state_cache.get(year)
        if state is None:
            state = load_sync_state(state_path, year=year, base_url=base_url, highlights_path=highlights_path)
            state_cache[year] = state

        remote_url = urljoin(listing_url, remote_name)
        try:
            raw_text, payload, etag = json_fetcher(remote_url)
        except Exception as exc:
            summary.errors += 1
            _log(f"❌ Error al descargar {remote_name}: {exc}")
            continue

        updated_at_text = str(payload.get("updated_at") or "").strip()
        updated_at = parse_remote_updated_at(updated_at_text)

        highlights = payload.get("highlights") or []
        if not isinstance(highlights, list):
            highlights = []
        has_highlights = bool(highlights)

        files_state = state.setdefault("files", {})
        entry = files_state.get(remote_name, {})
        entry_updated_at = parse_remote_updated_at(entry.get("remote_updated_at"))

        dest_file = dest_dir / remote_name
        downloaded = False
        entry_empty = bool(entry.get("empty"))
        if (
            updated_at
            and entry_updated_at
            and updated_at <= entry_updated_at
            and (dest_file.exists() or entry_empty)
        ):
            summary.skipped += 1
        else:
            if highlights:
                text = raw_text
                if not text.endswith("\n"):
                    text += "\n"
                tmp_path = dest_file.with_suffix(dest_file.suffix + ".tmp")
                tmp_path.write_text(text, encoding="utf-8")
                tmp_path.replace(dest_file)
                downloaded = True

        html_changed = False
        html_etag = None
        html_last_modified = None
        if decoded_name.lower().endswith((".html", ".htm")):
            html_name = remote_name[: -len(HIGHLIGHT_EXT)]
            public_html_url = build_public_html_url(base_url, reads_path, html_name)
            try:
                html_etag, html_last_modified = html_head_fetcher(public_html_url)
            except Exception as exc:
                _log(f"⚠️  No se pudo comprobar HTML publicado {decoded_name}: {exc}")
            if html_etag or html_last_modified:
                if html_etag != entry.get("html_etag") or html_last_modified != entry.get("html_last_modified"):
                    html_changed = True

        md_path = None
        md_text = None
        needs_marker_refresh = False
        if html_path is not None:
            md_path = html_path.with_suffix(".md")
            if md_path.exists():
                md_text = md_path.read_text(encoding="utf-8")
                has_markers = HIGHLIGHT_START_PREFIX in md_text
                highlight_ids = {str(item.get("id")).strip() for item in highlights if item.get("id")}
                marker_ids = extract_marker_ids(md_text)
                has_all_ids = highlight_ids.issubset(marker_ids) if highlight_ids else True
                has_nested = has_markers and has_nested_highlight_markers(md_text)
                if highlights:
                    needs_marker_refresh = (not has_markers) or (not has_all_ids) or has_nested
                else:
                    needs_marker_refresh = has_markers
            else:
                md_path = None

        should_update_md = downloaded or html_changed or needs_marker_refresh
        if should_update_md:
            if html_path is None:
                summary.md_missing += 1
                _log(f"⚠️  No se encontro HTML local para actualizar MD: {decoded_name}")
            elif md_path is None:
                summary.md_missing += 1
                _log(f"⚠️  No existe MD para actualizar: {html_path.with_suffix('.md').name}")
            else:
                if md_text is None:
                    md_text = md_path.read_text(encoding="utf-8")
                updated_text = apply_highlight_markers(md_text, highlights)
                if updated_text != md_text:
                    st = md_path.stat()
                    md_path.write_text(updated_text, encoding="utf-8")
                    try:
                        os.utime(md_path, (st.st_atime, st.st_mtime))
                    except Exception:
                        pass
                    summary.md_updated += 1
                    _log(f"📝 Resaltados actualizados: {md_path.name}")

        if not has_highlights:
            if dest_file.exists():
                try:
                    dest_file.unlink()
                    _log(f"🧹 Sin subrayados, eliminado: {remote_name}")
                except OSError as exc:
                    summary.errors += 1
                    _log(f"❌ No se pudo eliminar {remote_name}: {exc}")
        entry.update(
            {
                "remote_updated_at": updated_at_text,
                "synced_at": now_iso(),
                "source_url": remote_url,
                "local_file": remote_name,
                "bytes": len(raw_text.encode("utf-8")),
                "etag": etag,
                "empty": not has_highlights,
            }
        )
        if html_etag is not None:
            entry["html_etag"] = html_etag
        if html_last_modified is not None:
            entry["html_last_modified"] = html_last_modified
        files_state[remote_name] = entry

        if downloaded:
            summary.downloaded += 1
            _log(f"✅ {remote_name} -> Posts {year}/highlights/")

    for year, state in state_cache.items():
        state["last_run_at"] = now_iso()
        dest_dir = base_dir / "Posts" / f"Posts {year}" / "highlights"
        dest_dir.mkdir(parents=True, exist_ok=True)
        save_sync_state(dest_dir / "sync_state.json", state)

    return summary


def main(argv: Iterable[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Sincroniza los subrayados publicos hacia Posts/Posts <YEAR>/highlights/.",
    )
    parser.add_argument(
        "--base-url",
        default=derive_base_url(),
        help="Base URL del sitio (ej. https://domingogallardo.com).",
    )
    parser.add_argument(
        "--highlights-path",
        default=os.getenv("HIGHLIGHTS_PATH", DEFAULT_HIGHLIGHTS_PATH),
        help="Ruta del listado de highlights (default: /data/highlights/).",
    )
    parser.add_argument(
        "--base-dir",
        default=str(cfg.BASE_DIR),
        help="Directorio base local (default: config.BASE_DIR).",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=cfg.get_default_year(),
        help="Ano por defecto si no se encuentra el HTML local.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="Timeout HTTP en segundos.",
    )
    args = parser.parse_args(list(argv))

    if not args.base_url:
        _log("❌ Falta --base-url o HIGHLIGHTS_BASE_URL.")
        return 2

    base_url = normalize_base_url(args.base_url)
    highlights_path = normalize_highlights_path(args.highlights_path)

    try:
        summary = sync_public_highlights(
            base_url=base_url,
            highlights_path=highlights_path,
            base_dir=Path(args.base_dir),
            default_year=args.year,
            timeout=args.timeout,
        )
    except Exception as exc:
        _log(f"❌ Error al sincronizar: {exc}")
        return 1

    _log(
        "📌 Resultado: "
        f"{summary.downloaded} descargados, "
        f"{summary.skipped} omitidos, "
        f"{summary.md_updated} md actualizados, "
        f"{summary.md_missing} md ausentes, "
        f"{summary.missing_local} sin local, "
        f"{summary.errors} errores."
    )
    return 0 if summary.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
