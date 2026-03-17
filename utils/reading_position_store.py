"""Local reading-position storage helpers for the intranet mode.

Canonical storage:
  BASE_DIR/state/reading_positions/<sha256-prefix>/<sha256>.json
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.site_paths import normalize_rel_path, state_root

MEANINGFUL_SCROLL_Y = 24.0
MEANINGFUL_PROGRESS = 0.01


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def reading_positions_state_root(base_dir: Path) -> Path:
    return state_root(base_dir) / "reading_positions"


def _reading_position_hash(rel_path: str) -> str:
    return hashlib.sha256(rel_path.encode("utf-8")).hexdigest()


def reading_position_state_path(base_dir: Path, rel_path: str) -> Path:
    normalized = normalize_rel_path(rel_path)
    digest = _reading_position_hash(normalized)
    return reading_positions_state_root(base_dir) / digest[:2] / f"{digest}.json"


def _coerce_number(
    value: object,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float | None:
    if isinstance(value, bool) or value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number):
        return None

    if min_value is not None and number < min_value:
        number = min_value
    if max_value is not None and number > max_value:
        number = max_value
    return number


def _coerce_payload(normalized_path: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    updated_at = str(payload.get("updated_at") or "").strip()
    if payload and not updated_at:
        updated_at = _utc_now_iso()

    return {
        "version": 1,
        "path": normalized_path,
        "url": str(payload.get("url") or ""),
        "title": str(payload.get("title") or ""),
        "updated_at": updated_at,
        "scroll_y": _coerce_number(payload.get("scroll_y"), min_value=0.0),
        "max_scroll": _coerce_number(payload.get("max_scroll"), min_value=0.0),
        "progress": _coerce_number(payload.get("progress"), min_value=0.0, max_value=1.0),
        "viewport_height": _coerce_number(payload.get("viewport_height"), min_value=0.0),
        "document_height": _coerce_number(payload.get("document_height"), min_value=0.0),
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


def _remove_dir_if_empty(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        return


def _has_meaningful_position(payload: dict[str, Any]) -> bool:
    scroll_y = payload.get("scroll_y")
    if isinstance(scroll_y, (int, float)) and scroll_y > MEANINGFUL_SCROLL_Y:
        return True

    progress = payload.get("progress")
    return isinstance(progress, (int, float)) and progress > MEANINGFUL_PROGRESS


def load_reading_position_for_path(base_dir: Path, rel_path: str) -> dict[str, Any]:
    normalized = normalize_rel_path(rel_path)
    canonical_path = reading_position_state_path(base_dir, normalized)

    if canonical_path.is_file():
        data = _read_json(canonical_path)
        if data is not None:
            return _coerce_payload(normalized, data)

    return _coerce_payload(normalized, None)


def save_reading_position_for_path(base_dir: Path, rel_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_rel_path(rel_path)
    normalized_payload = _coerce_payload(normalized, payload)
    canonical_path = reading_position_state_path(base_dir, normalized)

    if not _has_meaningful_position(normalized_payload):
        if canonical_path.exists():
            canonical_path.unlink()
            _remove_dir_if_empty(canonical_path.parent)
        return normalized_payload

    _write_json_atomic(canonical_path, normalized_payload)
    return normalized_payload


def clear_reading_position_for_path(base_dir: Path, rel_path: str) -> bool:
    canonical_path = reading_position_state_path(base_dir, rel_path)
    if not canonical_path.exists():
        return False
    canonical_path.unlink()
    _remove_dir_if_empty(canonical_path.parent)
    return True
