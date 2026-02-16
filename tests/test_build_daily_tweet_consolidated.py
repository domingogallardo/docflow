from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from utils import build_daily_tweet_consolidated as mod


def _set_mtime_for_day(path: Path, day: str, *, hour: int) -> float:
    dt = datetime.strptime(day, "%Y-%m-%d").replace(hour=hour, minute=0, second=0)
    ts = dt.timestamp()
    os.utime(path, (ts, ts))
    return ts


def _write_tweet_pair(tweets_dir: Path, stem: str, day: str, *, hour: int) -> tuple[Path, Path]:
    md_path = tweets_dir / f"{stem}.md"
    html_path = tweets_dir / f"{stem}.html"
    md_path.write_text(
        "---\n"
        "source: tweet\n"
        f"tweet_url: https://x.com/{stem.replace(' ', '_')}\n"
        "---\n\n"
        f"# {stem}\n\n"
        "Tweet body.\n",
        encoding="utf-8",
    )
    html_path.write_text("<html><body>tweet html</body></html>", encoding="utf-8")
    _set_mtime_for_day(md_path, day, hour=hour)
    _set_mtime_for_day(html_path, day, hour=hour)
    return md_path, html_path


def test_main_removes_source_tweet_files_after_consolidation(tmp_path: Path, monkeypatch) -> None:
    day = "2026-02-13"
    tweets_dir = tmp_path / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    md1, html1 = _write_tweet_pair(tweets_dir, "Tweet - user-1", day, hour=10)
    md2, html2 = _write_tweet_pair(tweets_dir, "Tweet - user-2", day, hour=11)

    args = argparse.Namespace(
        day=day,
        year=2026,
        tweets_dir=tweets_dir,
        output_base=None,
        cleanup_if_consolidated=False,
    )
    monkeypatch.setattr(mod, "parse_args", lambda: args)

    exit_code = mod.main()
    assert exit_code == 0

    consolidated_md = tweets_dir / f"Tweets {day}.md"
    consolidated_html = tweets_dir / f"Tweets {day}.html"
    assert consolidated_md.is_file()
    assert consolidated_html.is_file()
    assert "Total de ficheros: **2**" in consolidated_md.read_text(encoding="utf-8")

    assert not md1.exists()
    assert not md2.exists()
    assert not html1.exists()
    assert not html2.exists()


def test_main_keeps_output_files_when_output_base_matches_input_stem(tmp_path: Path, monkeypatch) -> None:
    day = "2026-02-13"
    tweets_dir = tmp_path / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    _write_tweet_pair(tweets_dir, "daily", day, hour=10)

    args = argparse.Namespace(
        day=day,
        year=2026,
        tweets_dir=tweets_dir,
        output_base="daily",
        cleanup_if_consolidated=False,
    )
    monkeypatch.setattr(mod, "parse_args", lambda: args)

    exit_code = mod.main()
    assert exit_code == 0

    md_path = tweets_dir / "daily.md"
    html_path = tweets_dir / "daily.html"
    assert md_path.is_file()
    assert html_path.is_file()
    assert "Consolidado diario de tweets (2026-02-13)" in md_path.read_text(encoding="utf-8")


def test_cleanup_only_if_consolidated_removes_sources_without_rebuild(tmp_path: Path, monkeypatch) -> None:
    day = "2026-02-13"
    tweets_dir = tmp_path / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    src_md, src_html = _write_tweet_pair(tweets_dir, "Tweet - keep-cleaning", day, hour=10)
    consolidated_md = tweets_dir / f"Tweets {day}.md"
    consolidated_html = tweets_dir / f"Tweets {day}.html"
    consolidated_md.write_text("already built", encoding="utf-8")
    consolidated_html.write_text("<html><body>already built</body></html>", encoding="utf-8")
    original_consolidated_md = consolidated_md.read_text(encoding="utf-8")

    args = argparse.Namespace(
        day=day,
        year=2026,
        tweets_dir=tweets_dir,
        output_base=None,
        cleanup_if_consolidated=True,
    )
    monkeypatch.setattr(mod, "parse_args", lambda: args)

    exit_code = mod.main()
    assert exit_code == 0

    assert consolidated_md.read_text(encoding="utf-8") == original_consolidated_md
    assert consolidated_html.is_file()
    assert not src_md.exists()
    assert not src_html.exists()


def test_cleanup_only_if_consolidated_keeps_sources_when_no_consolidated(tmp_path: Path, monkeypatch) -> None:
    day = "2026-02-13"
    tweets_dir = tmp_path / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    src_md, src_html = _write_tweet_pair(tweets_dir, "Tweet - no-consolidated", day, hour=10)

    args = argparse.Namespace(
        day=day,
        year=2026,
        tweets_dir=tweets_dir,
        output_base=None,
        cleanup_if_consolidated=True,
    )
    monkeypatch.setattr(mod, "parse_args", lambda: args)

    exit_code = mod.main()
    assert exit_code == 0

    assert src_md.is_file()
    assert src_html.is_file()
