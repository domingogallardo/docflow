"""Persistent local state for done, working, and bumped entries."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.site_paths import bump_state_path, done_state_path, normalize_rel_path, working_state_path

STATE_VERSION = 1


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _empty_state() -> dict[str, Any]:
    return {"version": STATE_VERSION, "items": {}}


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_state()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _empty_state()

    if not isinstance(payload, dict):
        return _empty_state()

    items = payload.get("items", {})
    if not isinstance(items, dict):
        items = {}

    cleaned: dict[str, Any] = {}
    for key, value in items.items():
        if not isinstance(key, str):
            continue
        try:
            normalized = normalize_rel_path(key)
        except Exception:
            continue
        cleaned[normalized] = value if isinstance(value, dict) else {}

    return {"version": STATE_VERSION, "items": cleaned}


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def load_done_state(base_dir: Path) -> dict[str, Any]:
    return _read_state(done_state_path(base_dir))


def save_done_state(base_dir: Path, state: dict[str, Any]) -> None:
    _write_state(done_state_path(base_dir), state)


def load_working_state(base_dir: Path) -> dict[str, Any]:
    return _read_state(working_state_path(base_dir))


def save_working_state(base_dir: Path, state: dict[str, Any]) -> None:
    _write_state(working_state_path(base_dir), state)


def list_done(base_dir: Path) -> set[str]:
    state = load_done_state(base_dir)
    return set(state.get("items", {}).keys())


def list_working(base_dir: Path) -> set[str]:
    state = load_working_state(base_dir)
    return set(state.get("items", {}).keys())


def set_done_path(base_dir: Path, rel_path: str) -> bool:
    key = normalize_rel_path(rel_path)
    state = load_done_state(base_dir)
    items: dict[str, dict[str, Any]] = state["items"]
    already = key in items
    if not already:
        items[key] = {"done_at": _utc_now_iso()}
        save_done_state(base_dir, state)
    return not already


def clear_done_path(base_dir: Path, rel_path: str) -> bool:
    key = normalize_rel_path(rel_path)
    state = load_done_state(base_dir)
    items: dict[str, dict[str, Any]] = state["items"]
    if key not in items:
        return False
    items.pop(key, None)
    save_done_state(base_dir, state)
    return True


def is_done(base_dir: Path, rel_path: str) -> bool:
    key = normalize_rel_path(rel_path)
    return key in list_done(base_dir)


def set_working_path(base_dir: Path, rel_path: str) -> bool:
    key = normalize_rel_path(rel_path)
    state = load_working_state(base_dir)
    items: dict[str, dict[str, Any]] = state["items"]
    already = key in items
    if not already:
        items[key] = {"working_at": _utc_now_iso()}
        save_working_state(base_dir, state)
    return not already


def pop_working_path(base_dir: Path, rel_path: str) -> dict[str, Any] | None:
    key = normalize_rel_path(rel_path)
    state = load_working_state(base_dir)
    items: dict[str, dict[str, Any]] = state["items"]
    value = items.pop(key, None)
    if value is not None:
        save_working_state(base_dir, state)
    return value


def clear_working_path(base_dir: Path, rel_path: str) -> bool:
    return pop_working_path(base_dir, rel_path) is not None


def is_working(base_dir: Path, rel_path: str) -> bool:
    key = normalize_rel_path(rel_path)
    return key in list_working(base_dir)


def load_bump_state(base_dir: Path) -> dict[str, Any]:
    return _read_state(bump_state_path(base_dir))


def save_bump_state(base_dir: Path, state: dict[str, Any]) -> None:
    _write_state(bump_state_path(base_dir), state)


def set_bumped_path(base_dir: Path, rel_path: str, *, original_mtime: float, bumped_mtime: float) -> None:
    key = normalize_rel_path(rel_path)
    state = load_bump_state(base_dir)
    items: dict[str, dict[str, Any]] = state["items"]
    previous = items.get(key) or {}
    original_value = previous.get("original_mtime", original_mtime)
    try:
        original_value = float(original_value)
    except Exception:
        original_value = float(original_mtime)

    items[key] = {
        "original_mtime": float(original_value),
        "bumped_mtime": float(bumped_mtime),
        "updated_at": _utc_now_iso(),
    }
    save_bump_state(base_dir, state)


def pop_bumped_path(base_dir: Path, rel_path: str) -> dict[str, Any] | None:
    key = normalize_rel_path(rel_path)
    state = load_bump_state(base_dir)
    items: dict[str, dict[str, Any]] = state["items"]
    value = items.pop(key, None)
    if value is not None:
        save_bump_state(base_dir, state)
    return value


def get_bumped_entry(base_dir: Path, rel_path: str) -> dict[str, Any] | None:
    key = normalize_rel_path(rel_path)
    state = load_bump_state(base_dir)
    items: dict[str, dict[str, Any]] = state["items"]
    value = items.get(key)
    return value if isinstance(value, dict) else None


def list_bumped(base_dir: Path) -> set[str]:
    state = load_bump_state(base_dir)
    return set(state.get("items", {}).keys())
