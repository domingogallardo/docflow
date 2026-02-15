"""Local highlight storage helpers for the intranet mode.

Canonical storage:
  BASE_DIR/state/highlights/<sha256-prefix>/<sha256>.json

Compatibility:
- If canonical data is missing, legacy highlight JSON under
  Posts/Posts <YEAR>/highlights/<encoded-basename>.json is read as fallback.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from utils.site_paths import normalize_rel_path, state_root


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def highlights_state_root(base_dir: Path) -> Path:
    return state_root(base_dir) / "highlights"


def _highlight_hash(rel_path: str) -> str:
    return hashlib.sha256(rel_path.encode("utf-8")).hexdigest()


def highlight_state_path(base_dir: Path, rel_path: str) -> Path:
    normalized = normalize_rel_path(rel_path)
    digest = _highlight_hash(normalized)
    return highlights_state_root(base_dir) / digest[:2] / f"{digest}.json"


def _legacy_highlight_path(base_dir: Path, rel_path: str) -> Path | None:
    normalized = normalize_rel_path(rel_path)
    parts = Path(normalized).parts
    if len(parts) < 3:
        return None
    if parts[0] != "Posts":
        return None

    year_dir = parts[1]
    if not year_dir.startswith("Posts "):
        return None

    highlights_dir = base_dir / "Posts" / year_dir / "highlights"
    if not highlights_dir.is_dir():
        return None

    basename = parts[-1]
    candidates = [
        quote(basename),
        quote(basename, safe="~!*()'"),
    ]
    seen: set[str] = set()
    for encoded in candidates:
        if encoded in seen:
            continue
        seen.add(encoded)
        path = highlights_dir / f"{encoded}.json"
        if path.is_file():
            return path
    return None


def _coerce_payload(normalized_path: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    highlights_raw = payload.get("highlights")
    highlights: list[dict[str, Any]] = []
    if isinstance(highlights_raw, list):
        for item in highlights_raw:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            copied = dict(item)
            copied["text"] = text
            highlights.append(copied)

    return {
        "version": 1,
        "path": normalized_path,
        "url": str(payload.get("url") or ""),
        "title": str(payload.get("title") or ""),
        "updated_at": str(payload.get("updated_at") or _utc_now_iso()),
        "highlights": highlights,
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def load_highlights_for_path(base_dir: Path, rel_path: str) -> dict[str, Any]:
    normalized = normalize_rel_path(rel_path)
    canonical_path = highlight_state_path(base_dir, normalized)

    if canonical_path.is_file():
        data = _read_json(canonical_path)
        if data is not None:
            return _coerce_payload(normalized, data)

    legacy_path = _legacy_highlight_path(base_dir, normalized)
    if legacy_path is not None:
        data = _read_json(legacy_path)
        if data is not None:
            return _coerce_payload(normalized, data)

    return _coerce_payload(normalized, {"highlights": []})


def save_highlights_for_path(base_dir: Path, rel_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_rel_path(rel_path)
    normalized_payload = _coerce_payload(normalized, payload)
    canonical_path = highlight_state_path(base_dir, normalized)

    if not normalized_payload["highlights"]:
        if canonical_path.exists():
            canonical_path.unlink()
        return normalized_payload

    _write_json_atomic(canonical_path, normalized_payload)
    return normalized_payload


def has_highlights_for_path(base_dir: Path, rel_path: str) -> bool:
    payload = load_highlights_for_path(base_dir, rel_path)
    highlights = payload.get("highlights")
    return isinstance(highlights, list) and bool(highlights)
