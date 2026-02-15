from __future__ import annotations

import os
from pathlib import Path

from utils import sync_tweets_public as mod


def _write_consolidated(path: Path, content: str, mtime: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    os.utime(path, (mtime, mtime))


def test_sync_consolidated_tweets_copies_by_year_and_cleans_stale(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    y2026 = base_dir / "Tweets" / "Tweets 2026"
    y2025 = base_dir / "Tweets" / "Tweets 2025"
    _write_consolidated(y2026 / "Consolidado Tweets 2026-01-02.html", "2026-new", 2_000)
    _write_consolidated(y2026 / "Consolidado Tweets 2026-01-01.html", "2026-old", 1_000)
    _write_consolidated(y2025 / "Consolidado Tweets 2025-12-31.html", "2025", 500)

    output_dir = tmp_path / "public" / "read" / "tweets"
    output_dir.mkdir(parents=True)
    stale_flat = output_dir / "Consolidado Tweets 1999-01-01.html"
    stale_flat.write_text("legacy", encoding="utf-8")
    stale_year = output_dir / "2024"
    stale_year.mkdir(parents=True)
    _write_consolidated(stale_year / "Consolidado Tweets 2024-01-01.html", "stale", 1)
    stale_inside_year = output_dir / "2026" / "Consolidado Tweets 2026-01-99.html"
    _write_consolidated(stale_inside_year, "stale", 1)

    stats = mod.sync_consolidated_tweets(base_dir, output_dir)

    copied_2026 = output_dir / "2026" / "Consolidado Tweets 2026-01-02.html"
    copied_2025 = output_dir / "2025" / "Consolidado Tweets 2025-12-31.html"
    assert copied_2026.is_file()
    assert copied_2025.is_file()
    assert int(copied_2026.stat().st_mtime) == 2_000
    assert not stale_flat.exists()
    assert not stale_year.exists()
    assert not stale_inside_year.exists()
    assert stats.copied == 3
    assert stats.removed_files == 2
    assert stats.removed_dirs == 1


def test_sync_consolidated_tweets_is_idempotent(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    y2026 = base_dir / "Tweets" / "Tweets 2026"
    _write_consolidated(y2026 / "Consolidado Tweets 2026-01-02.html", "2026-new", 2_000)
    _write_consolidated(y2026 / "Consolidado Tweets 2026-01-01.html", "2026-old", 1_000)

    output_dir = tmp_path / "public" / "read" / "tweets"
    first = mod.sync_consolidated_tweets(base_dir, output_dir)
    second = mod.sync_consolidated_tweets(base_dir, output_dir)

    assert first.copied == 2
    assert second.copied == 0
    assert second.skipped == 2
