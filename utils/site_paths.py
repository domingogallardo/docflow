"""Shared path helpers for the local intranet site contract."""

from __future__ import annotations

import importlib.util
import os
import posixpath
from pathlib import Path
from urllib.parse import unquote

BASE_DIR_ENV = "DOCFLOW_BASE_DIR"


class PathValidationError(ValueError):
    """Raised when a relative path is invalid or unsafe."""


def _load_config_base_dir() -> Path | None:
    try:
        from config import BASE_DIR  # local import to keep tests isolated

        return Path(BASE_DIR).expanduser()
    except Exception:
        pass

    try:
        repo_root = Path(__file__).resolve().parents[1]
        config_path = repo_root / "config.py"
        if not config_path.is_file():
            return None
        spec = importlib.util.spec_from_file_location("docflow_config", config_path)
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        assert spec and spec.loader
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        value = getattr(module, "BASE_DIR", None)
        return Path(value).expanduser() if value else None
    except Exception:
        return None


def resolve_base_dir(cli_base_dir: str | None = None) -> Path:
    """Resolve BASE_DIR with priority: CLI -> env -> config.py."""
    if cli_base_dir:
        return Path(cli_base_dir).expanduser()

    env_value = os.getenv(BASE_DIR_ENV)
    if env_value:
        return Path(env_value).expanduser()

    base_dir = _load_config_base_dir()
    if base_dir is None:
        raise RuntimeError("Could not resolve BASE_DIR")

    return base_dir


def site_root(base_dir: Path) -> Path:
    return base_dir / "_site"


def state_root(base_dir: Path) -> Path:
    return base_dir / "state"


def published_state_path(base_dir: Path) -> Path:
    return state_root(base_dir) / "published.json"


def bump_state_path(base_dir: Path) -> Path:
    return state_root(base_dir) / "bump.json"


def _preferred_child(base_dir: Path, *names: str) -> Path:
    for name in names:
        candidate = base_dir / name
        if candidate.exists():
            return candidate
    return base_dir / names[0]


def library_roots(base_dir: Path) -> dict[str, Path]:
    """Return canonical roots used by browse generation and raw routing."""
    return {
        "incoming": _preferred_child(base_dir, "Incoming"),
        "posts": _preferred_child(base_dir, "Posts"),
        "tweets": _preferred_child(base_dir, "Tweets"),
        "pdfs": _preferred_child(base_dir, "Pdfs", "PDFs"),
        "images": _preferred_child(base_dir, "Images"),
        "podcasts": _preferred_child(base_dir, "Podcasts"),
        "files": base_dir,
    }


def raw_route_map(base_dir: Path) -> dict[str, Path]:
    roots = library_roots(base_dir)
    return {
        "/incoming/raw": roots["incoming"],
        "/posts/raw": roots["posts"],
        "/tweets/raw": roots["tweets"],
        "/pdfs/raw": roots["pdfs"],
        "/images/raw": roots["images"],
        "/podcasts/raw": roots["podcasts"],
        "/files/raw": roots["files"],
    }


def normalize_rel_path(rel_path: str) -> str:
    """Normalize a BASE_DIR-relative path and reject traversal or empties."""
    value = (rel_path or "").strip().replace("\\", "/")
    if not value:
        raise PathValidationError("Path is empty")

    value = value.lstrip("/")
    normalized = posixpath.normpath(value)

    if normalized in ("", ".", ".."):
        raise PathValidationError("Path is empty or invalid")
    if normalized.startswith("../"):
        raise PathValidationError("Path traversal is not allowed")

    return normalized


def resolve_library_path(base_dir: Path, rel_path: str) -> Path:
    """Resolve a relative library path inside BASE_DIR."""
    rel = normalize_rel_path(rel_path)
    base = base_dir.resolve()
    target = (base / Path(rel)).resolve()
    if target == base or str(target).startswith(str(base) + os.sep):
        return target
    raise PathValidationError("Resolved path escapes BASE_DIR")


def rel_path_from_abs(base_dir: Path, abs_path: Path) -> str:
    """Convert an absolute path under BASE_DIR to a normalized relative path."""
    base = base_dir.resolve()
    target = abs_path.resolve()
    rel = target.relative_to(base)
    return normalize_rel_path(rel.as_posix())


def resolve_raw_path(base_dir: Path, request_path: str) -> Path | None:
    """Resolve '/<bucket>/raw/<path>' into an absolute library path."""
    for prefix, root in raw_route_map(base_dir).items():
        if request_path == prefix:
            return root
        if not request_path.startswith(prefix + "/"):
            continue

        rel_encoded = request_path[len(prefix) + 1 :]
        rel_decoded = normalize_rel_path(unquote(rel_encoded))
        base = root.resolve()
        target = (base / Path(rel_decoded)).resolve()
        if target == base or str(target).startswith(str(base) + os.sep):
            return target
        return None

    return None


def raw_url_for_rel_path(rel_path: str) -> str:
    """Build a raw URL for a BASE_DIR-relative file path."""
    rel = normalize_rel_path(rel_path)
    head, _, tail = rel.partition("/")

    bucket_map = {
        "Incoming": "incoming",
        "Posts": "posts",
        "Tweets": "tweets",
        "Pdfs": "pdfs",
        "PDFs": "pdfs",
        "Images": "images",
        "Podcasts": "podcasts",
    }
    bucket = bucket_map.get(head, "files")

    from urllib.parse import quote

    payload = tail if tail else head
    safe_chars = "~!*()'/-"
    return f"/{bucket}/raw/{quote(payload, safe=safe_chars)}"
