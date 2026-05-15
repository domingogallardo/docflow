"""Shared timestamp helpers."""

from __future__ import annotations

from datetime import datetime


def local_now_iso(*, timespec: str = "seconds") -> str:
    """Return a local ISO 8601 timestamp including the timezone offset."""
    return datetime.now().astimezone().isoformat(timespec=timespec)
