#!/usr/bin/env python3
"""Sync highlights from the public /data/highlights/ folder into local Posts/Posts <YEAR>/highlights/.

Phase 1 sync:
- Download highlight JSON files from the public server.
- Store them under Posts/Posts <YEAR>/highlights/ based on the matching local HTML year.
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
from urllib.parse import unquote, urljoin, urlparse

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


@dataclass
class SyncSummary:
    total: int = 0
    downloaded: int = 0
    skipped: int = 0
    missing_local: int = 0
    errors: int = 0


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


def derive_base_url() -> str | None:
    env_base = os.getenv("HIGHLIGHTS_BASE_URL", "").strip()
    if env_base:
        return env_base
    reads_base = os.getenv("PUBLIC_READS_URL_BASE", "").strip()
    if not reads_base:
        return None
    parsed = urlparse(reads_base)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


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


def build_local_html_index(base_dir: Path) -> Tuple[Dict[str, int], set[str]]:
    year_by_name: Dict[str, int] = {}
    found: set[str] = set()
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for filename in files:
            if not filename.lower().endswith((".html", ".htm")):
                continue
            found.add(filename)
            year = extract_year_from_path(Path(root) / filename)
            if year is None:
                continue
            current = year_by_name.get(filename)
            if current is None or year > current:
                year_by_name[filename] = year
    return year_by_name, found


def pick_year_for_basename(
    basename: str,
    *,
    year_index: Dict[str, int],
    known_names: set[str],
    default_year: int,
) -> Tuple[int, bool]:
    if basename in year_index:
        return year_index[basename], True
    if basename in known_names:
        return default_year, True
    return default_year, False


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


def sync_public_highlights(
    *,
    base_url: str,
    highlights_path: str,
    base_dir: Path,
    default_year: int,
    timeout: int = 20,
    listing_fetcher: Callable[[str], str] | None = None,
    json_fetcher: Callable[[str], Tuple[str, dict, str | None]] | None = None,
) -> SyncSummary:
    summary = SyncSummary()
    listing_fetcher = listing_fetcher or (lambda url: fetch_listing(url, timeout=timeout))
    json_fetcher = json_fetcher or (lambda url: fetch_highlight_json(url, timeout=timeout))

    listing_url = urljoin(base_url + "/", highlights_path.lstrip("/"))
    _log(f"🔎 Buscando subrayados en {listing_url}")
    html_text = listing_fetcher(listing_url)
    remote_files = extract_links_from_autoindex(html_text)
    summary.total = len(remote_files)
    if not remote_files:
        _log("⚠️  No se encontraron subrayados en el listado.")
        return summary

    year_index, known_names = build_local_html_index(base_dir)
    state_cache: Dict[int, dict] = {}

    for remote_name in remote_files:
        decoded_name = decode_highlight_basename(remote_name)
        year, has_local = pick_year_for_basename(
            decoded_name,
            year_index=year_index,
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

        files_state = state.setdefault("files", {})
        entry = files_state.get(remote_name, {})
        entry_updated_at = parse_remote_updated_at(entry.get("remote_updated_at"))

        dest_file = dest_dir / remote_name
        if (
            updated_at
            and entry_updated_at
            and updated_at <= entry_updated_at
            and dest_file.exists()
        ):
            summary.skipped += 1
            continue

        text = raw_text
        if not text.endswith("\n"):
            text += "\n"
        tmp_path = dest_file.with_suffix(dest_file.suffix + ".tmp")
        tmp_path.write_text(text, encoding="utf-8")
        tmp_path.replace(dest_file)

        files_state[remote_name] = {
            "remote_updated_at": updated_at_text,
            "synced_at": now_iso(),
            "source_url": remote_url,
            "local_file": remote_name,
            "bytes": len(text.encode("utf-8")),
            "etag": etag,
        }
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
        _log("❌ Falta --base-url o HIGHLIGHTS_BASE_URL/PUBLIC_READS_URL_BASE.")
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
        f"{summary.missing_local} sin local, "
        f"{summary.errors} errores."
    )
    return 0 if summary.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
