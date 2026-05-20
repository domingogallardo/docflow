from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta
from pathlib import Path

from utils import build_daily_tweet_consolidated as mod
from utils import highlight_store
from utils import site_state


def _set_mtime_for_day(path: Path, day: str, *, hour: int) -> float:
    dt = datetime.strptime(day, "%Y-%m-%d").replace(hour=hour, minute=0, second=0)
    ts = dt.timestamp()
    os.utime(path, (ts, ts))
    return ts


def _write_tweet_pair(
    tweets_dir: Path,
    stem: str,
    day: str,
    *,
    hour: int,
    body: str = "Tweet body.",
    capture_source: str = "liked",
    extra_front_matter: str = "",
) -> tuple[Path, Path]:
    md_path = tweets_dir / f"{stem}.md"
    html_path = tweets_dir / f"{stem}.html"
    md_path.write_text(
        "---\n"
        "source: tweet\n"
        f"tweet_url: https://x.com/{stem.replace(' ', '_')}\n"
        f"tweet_capture_source: {capture_source}\n"
        f"{extra_front_matter}"
        "---\n\n"
        f"# {stem}\n\n"
        f"{body}\n",
        encoding="utf-8",
    )
    html_path.write_text("<html><body>tweet html</body></html>", encoding="utf-8")
    _set_mtime_for_day(md_path, day, hour=hour)
    _set_mtime_for_day(html_path, day, hour=hour)
    return md_path, html_path


def test_collect_daily_source_markdown_uses_rollover_hour_for_early_next_day(
    tmp_path: Path,
    monkeypatch,
) -> None:
    day = "2026-02-13"
    next_day = (datetime.strptime(day, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    tweets_dir = tmp_path / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    same_day_md, _ = _write_tweet_pair(tweets_dir, "Tweet - same-day", day, hour=23)
    early_next_day_md, _ = _write_tweet_pair(tweets_dir, "Tweet - early-next-day", next_day, hour=1)
    boundary_next_day_md, _ = _write_tweet_pair(tweets_dir, "Tweet - boundary-next-day", next_day, hour=3)

    monkeypatch.setenv("DOCFLOW_TWEET_DAY_ROLLOVER_HOUR", "3")

    selected = mod._collect_daily_source_markdown(tweets_dir, day)
    selected_set = set(selected)

    assert same_day_md in selected_set
    assert early_next_day_md in selected_set
    assert boundary_next_day_md not in selected_set


def test_collect_daily_source_markdown_excludes_tweet_articles(tmp_path: Path) -> None:
    day = "2026-02-13"
    tweets_dir = tmp_path / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    normal_md, _ = _write_tweet_pair(tweets_dir, "Tweet - normal", day, hour=10)
    article_md, _ = _write_tweet_pair(
        tweets_dir,
        "Tweet - article",
        day,
        hour=11,
        extra_front_matter="tweet_content_type: article\n",
    )

    selected = mod._collect_daily_source_markdown(tweets_dir, day)

    assert selected == [normal_md]
    assert article_md not in selected


def test_main_excludes_tweet_articles_and_keeps_their_html(tmp_path: Path, monkeypatch) -> None:
    day = "2026-02-13"
    tweets_dir = tmp_path / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    normal_md, normal_html = _write_tweet_pair(tweets_dir, "Tweet - normal", day, hour=10)
    article_md, article_html = _write_tweet_pair(
        tweets_dir,
        "Tweet - article",
        day,
        hour=11,
        body="Article body should stay out.",
        extra_front_matter="tweet_content_type: article\n",
    )

    args = argparse.Namespace(
        day=day,
        year=2026,
        tweets_dir=tweets_dir,
        output_base=None,
        capture_source="liked",
        cleanup_if_consolidated=False,
    )
    monkeypatch.setattr(mod, "parse_args", lambda: args)

    exit_code = mod.main()

    assert exit_code == 0
    consolidated_md = tweets_dir / f"Tweets {day}.md"
    consolidated_text = consolidated_md.read_text(encoding="utf-8")
    assert "Total de ficheros: **1**" in consolidated_text
    assert "## normal" in consolidated_text
    assert "Article body should stay out." not in consolidated_text
    assert normal_md.is_file()
    assert not normal_html.exists()
    assert article_md.is_file()
    assert article_html.is_file()


def test_main_includes_early_next_day_files_in_previous_day_consolidation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    day = "2026-02-13"
    next_day = (datetime.strptime(day, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    tweets_dir = tmp_path / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    _write_tweet_pair(tweets_dir, "Tweet - same-day", day, hour=23)
    _write_tweet_pair(tweets_dir, "Tweet - early-next-day", next_day, hour=1)
    monkeypatch.setenv("DOCFLOW_TWEET_DAY_ROLLOVER_HOUR", "3")

    args = argparse.Namespace(
        day=day,
        year=2026,
        tweets_dir=tweets_dir,
        output_base=None,
        capture_source="liked",
        cleanup_if_consolidated=False,
    )
    monkeypatch.setattr(mod, "parse_args", lambda: args)

    exit_code = mod.main()
    assert exit_code == 0

    consolidated_md = tweets_dir / f"Tweets {day}.md"
    assert consolidated_md.is_file()
    assert "Total de ficheros: **2**" in consolidated_md.read_text(encoding="utf-8")


def test_main_keeps_source_markdown_and_removes_source_html_after_consolidation(
    tmp_path: Path, monkeypatch
) -> None:
    day = "2026-02-13"
    tweets_dir = tmp_path / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    md1, html1 = _write_tweet_pair(
        tweets_dir,
        "Tweet - user-1",
        day,
        hour=10,
        extra_front_matter="docflow_html_path: Tweets/Tweets 2026/Tweet - user-1.html\n",
    )
    md2, html2 = _write_tweet_pair(tweets_dir, "Tweet - user-2", day, hour=11)
    original_md1_mtime = md1.stat().st_mtime
    original_md2_mtime = md2.stat().st_mtime

    args = argparse.Namespace(
        day=day,
        year=2026,
        tweets_dir=tweets_dir,
        output_base=None,
        capture_source="liked",
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

    assert md1.exists()
    assert md2.exists()
    assert not html1.exists()
    assert not html2.exists()
    assert md1.stat().st_mtime == original_md1_mtime
    assert md2.stat().st_mtime == original_md2_mtime

    meta1, _ = mod.U.split_front_matter(md1.read_text(encoding="utf-8"))
    meta2, _ = mod.U.split_front_matter(md2.read_text(encoding="utf-8"))
    consolidated_meta, _ = mod.U.split_front_matter(consolidated_md.read_text(encoding="utf-8"))
    assert meta1["docflow_render_status"] == "markdown_only"
    assert meta2["docflow_render_status"] == "markdown_only"
    assert "docflow_html_path" not in meta1
    assert consolidated_meta["docflow_render_status"] == "paired_html"


def test_main_links_source_markdown_to_consolidated_anchor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    day = "2026-02-13"
    base_dir = tmp_path
    tweets_dir = base_dir / "Tweets" / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    src_md, _ = _write_tweet_pair(
        tweets_dir,
        "Tweet - anchored-source",
        day,
        hour=10,
        extra_front_matter="tweet_id: 1234567890\n",
    )
    original_mtime = src_md.stat().st_mtime

    args = argparse.Namespace(
        day=day,
        year=2026,
        tweets_dir=tweets_dir,
        output_base=None,
        capture_source="liked",
        cleanup_if_consolidated=False,
    )
    monkeypatch.setattr(mod, "parse_args", lambda: args)
    monkeypatch.setattr(mod.cfg, "BASE_DIR", base_dir)

    exit_code = mod.main()
    assert exit_code == 0

    consolidated_html = tweets_dir / f"Tweets {day}.html"
    html_text = consolidated_html.read_text(encoding="utf-8")
    assert '<article class="dg-entry" id="tweet-1234567890">' in html_text

    meta, _ = mod.U.split_front_matter(src_md.read_text(encoding="utf-8"))
    assert meta["tweet_consolidated_anchor"] == "tweet-1234567890"
    assert (
        meta["tweet_consolidated_url"]
        == "/tweets/raw/Tweets%202026/Tweets%202026-02-13.html#tweet-1234567890"
    )
    assert src_md.stat().st_mtime == original_mtime


def test_main_writes_plain_markdown_but_keeps_styled_html(tmp_path: Path, monkeypatch) -> None:
    day = "2026-02-13"
    tweets_dir = tmp_path / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    _write_tweet_pair(
        tweets_dir,
        "Tweet - user-1",
        day,
        hour=10,
        body="Line one\nLine two\n\n[![image 1](https://example.com/image.jpg)](https://example.com/image.jpg)",
    )

    args = argparse.Namespace(
        day=day,
        year=2026,
        tweets_dir=tweets_dir,
        output_base=None,
        capture_source="liked",
        cleanup_if_consolidated=False,
    )
    monkeypatch.setattr(mod, "parse_args", lambda: args)

    exit_code = mod.main()
    assert exit_code == 0

    consolidated_md = tweets_dir / f"Tweets {day}.md"
    consolidated_html = tweets_dir / f"Tweets {day}.html"
    md_text = consolidated_md.read_text(encoding="utf-8")
    html_text = consolidated_html.read_text(encoding="utf-8")

    assert "<style>" not in md_text
    assert "<article" not in md_text
    assert "<div" not in md_text
    assert "## user-1" in md_text
    assert "- Autor:" in md_text
    assert "[![image 1](https://example.com/image.jpg)](https://example.com/image.jpg)" in md_text

    assert "<style>" in html_text
    assert '<article class="dg-entry" id=' in html_text
    assert '<div class="dg-entry-body">' in html_text
    assert '<img alt="image 1" src="https://example.com/image.jpg"' in html_text


def test_main_ports_source_tweet_highlights_to_consolidated_html(
    tmp_path: Path,
    monkeypatch,
) -> None:
    day = "2026-02-13"
    base_dir = tmp_path
    tweets_dir = base_dir / "Tweets" / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    _write_tweet_pair(tweets_dir, "Tweet - user-1", day, hour=10, body="First highlighted body.")
    _write_tweet_pair(tweets_dir, "Tweet - user-2", day, hour=11, body="Second highlighted body.")

    highlight_store.save_highlights_for_path(
        base_dir,
        "Tweets/Tweets 2026/Tweet - user-1.html",
        {"highlights": [{"id": "h1", "text": "First highlighted body."}]},
    )
    highlight_store.save_highlights_for_path(
        base_dir,
        "Tweets/Tweets 2026/Tweet - user-2.html",
        {"highlights": [{"id": "h1", "text": "Second highlighted body."}]},
    )

    args = argparse.Namespace(
        day=day,
        year=2026,
        tweets_dir=tweets_dir,
        output_base=None,
        capture_source="liked",
        cleanup_if_consolidated=False,
    )
    monkeypatch.setattr(mod, "parse_args", lambda: args)
    monkeypatch.setattr(mod.cfg, "BASE_DIR", base_dir)

    exit_code = mod.main()
    assert exit_code == 0

    consolidated_payload = highlight_store.load_highlights_for_path(
        base_dir,
        f"Tweets/Tweets 2026/Tweets {day}.html",
    )
    highlights = consolidated_payload["highlights"]
    texts = {item["text"] for item in highlights}
    ids = [item["id"] for item in highlights]

    assert texts == {"First highlighted body.", "Second highlighted body."}
    assert len(ids) == 2
    assert len(set(ids)) == 2
    assert highlight_store.load_highlights_for_path(
        base_dir,
        "Tweets/Tweets 2026/Tweet - user-1.html",
    )["highlights"] == []
    assert highlight_store.load_highlights_for_path(
        base_dir,
        "Tweets/Tweets 2026/Tweet - user-2.html",
    )["highlights"] == []


def test_main_keeps_source_reading_html_state_and_highlights_when_consolidating(
    tmp_path: Path,
    monkeypatch,
) -> None:
    day = "2026-02-13"
    base_dir = tmp_path
    tweets_dir = base_dir / "Tweets" / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    _, html1 = _write_tweet_pair(tweets_dir, "Tweet - user-1", day, hour=10)
    _, html2 = _write_tweet_pair(tweets_dir, "Tweet - user-2", day, hour=11)
    highlight_store.save_highlights_for_path(
        base_dir,
        "Tweets/Tweets 2026/Tweet - user-1.html",
        {"highlights": [{"id": "h1", "text": "Reading highlight."}]},
    )

    site_state.save_reading_state(
        base_dir,
        {
            "version": site_state.STATE_VERSION,
            "items": {
                "Tweets/Tweets 2026/Tweet - user-1.html": {
                    "reading_at": "2026-02-13T10:30:00Z",
                },
                "Tweets/Tweets 2026/Tweet - user-2.html": {
                    "reading_at": "2026-02-13T10:15:00Z",
                },
            },
        },
    )

    args = argparse.Namespace(
        day=day,
        year=2026,
        tweets_dir=tweets_dir,
        output_base=None,
        capture_source="liked",
        cleanup_if_consolidated=False,
    )
    monkeypatch.setattr(mod, "parse_args", lambda: args)
    monkeypatch.setattr(mod.cfg, "BASE_DIR", base_dir)

    exit_code = mod.main()
    assert exit_code == 0

    assert html1.is_file()
    assert html2.is_file()
    assert site_state.load_reading_state(base_dir)["items"] == {
        "Tweets/Tweets 2026/Tweet - user-1.html": {
            "reading_at": "2026-02-13T10:30:00Z",
        },
        "Tweets/Tweets 2026/Tweet - user-2.html": {
            "reading_at": "2026-02-13T10:15:00Z",
        },
    }
    assert site_state.load_done_state(base_dir)["items"] == {}
    assert f"Tweets/Tweets 2026/Tweets {day}.html" not in site_state.load_reading_state(base_dir)["items"]
    assert highlight_store.load_highlights_for_path(
        base_dir,
        "Tweets/Tweets 2026/Tweet - user-1.html",
    )["highlights"] == [{"id": "h1", "text": "Reading highlight."}]
    assert highlight_store.load_highlights_for_path(
        base_dir,
        f"Tweets/Tweets 2026/Tweets {day}.html",
    )["highlights"] == []


def test_main_keeps_source_done_html_state_and_highlights_when_consolidating(
    tmp_path: Path,
    monkeypatch,
) -> None:
    day = "2026-02-13"
    base_dir = tmp_path
    tweets_dir = base_dir / "Tweets" / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    _, reading_html = _write_tweet_pair(tweets_dir, "Tweet - reading-source", day, hour=10)
    _, done_html = _write_tweet_pair(tweets_dir, "Tweet - done-source", day, hour=11)
    highlight_store.save_highlights_for_path(
        base_dir,
        "Tweets/Tweets 2026/Tweet - done-source.html",
        {"highlights": [{"id": "h1", "text": "Done highlight."}]},
    )

    site_state.save_reading_state(
        base_dir,
        {
            "version": site_state.STATE_VERSION,
            "items": {
                "Tweets/Tweets 2026/Tweet - reading-source.html": {
                    "reading_at": "2026-02-13T09:00:00Z",
                },
            },
        },
    )
    site_state.save_done_state(
        base_dir,
        {
            "version": site_state.STATE_VERSION,
            "items": {
                "Tweets/Tweets 2026/Tweet - done-source.html": {
                    "done_at": "2026-02-13T12:00:00Z",
                    "reading_started_at": "2026-02-13T08:00:00Z",
                },
            },
        },
    )

    args = argparse.Namespace(
        day=day,
        year=2026,
        tweets_dir=tweets_dir,
        output_base=None,
        capture_source="liked",
        cleanup_if_consolidated=False,
    )
    monkeypatch.setattr(mod, "parse_args", lambda: args)
    monkeypatch.setattr(mod.cfg, "BASE_DIR", base_dir)

    exit_code = mod.main()
    assert exit_code == 0

    assert reading_html.is_file()
    assert done_html.is_file()
    assert site_state.load_reading_state(base_dir)["items"] == {
        "Tweets/Tweets 2026/Tweet - reading-source.html": {
            "reading_at": "2026-02-13T09:00:00Z",
        },
    }
    assert site_state.load_done_state(base_dir)["items"] == {
        "Tweets/Tweets 2026/Tweet - done-source.html": {
            "done_at": "2026-02-13T12:00:00Z",
            "reading_started_at": "2026-02-13T08:00:00Z",
        }
    }
    assert f"Tweets/Tweets 2026/Tweets {day}.html" not in site_state.load_done_state(base_dir)["items"]
    assert highlight_store.load_highlights_for_path(
        base_dir,
        "Tweets/Tweets 2026/Tweet - done-source.html",
    )["highlights"] == [{"id": "h1", "text": "Done highlight."}]
    assert highlight_store.load_highlights_for_path(
        base_dir,
        f"Tweets/Tweets 2026/Tweets {day}.html",
    )["highlights"] == []


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
        capture_source="liked",
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


def test_cleanup_only_if_consolidated_keeps_md_and_removes_html_without_rebuild(
    tmp_path: Path, monkeypatch
) -> None:
    day = "2026-02-13"
    tweets_dir = tmp_path / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    src_md, src_html = _write_tweet_pair(tweets_dir, "Tweet - keep-cleaning", day, hour=10)
    original_src_mtime = src_md.stat().st_mtime
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
        capture_source="liked",
        cleanup_if_consolidated=True,
    )
    monkeypatch.setattr(mod, "parse_args", lambda: args)

    exit_code = mod.main()
    assert exit_code == 0

    assert consolidated_md.read_text(encoding="utf-8") == original_consolidated_md
    assert consolidated_html.is_file()
    assert src_md.is_file()
    assert not src_html.exists()
    assert src_md.stat().st_mtime == original_src_mtime
    meta, _ = mod.U.split_front_matter(src_md.read_text(encoding="utf-8"))
    assert meta["docflow_render_status"] == "markdown_only"


def test_cleanup_only_if_consolidated_ports_and_clears_source_highlights(
    tmp_path: Path,
    monkeypatch,
) -> None:
    day = "2026-02-13"
    base_dir = tmp_path
    tweets_dir = base_dir / "Tweets" / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    src_md, src_html = _write_tweet_pair(
        tweets_dir,
        "Tweet - keep-cleaning",
        day,
        hour=10,
        body="Cleanup highlighted body.",
    )
    consolidated_md = tweets_dir / f"Tweets {day}.md"
    consolidated_html = tweets_dir / f"Tweets {day}.html"
    consolidated_md.write_text("already built", encoding="utf-8")
    consolidated_html.write_text("<html><body>Cleanup highlighted body.</body></html>", encoding="utf-8")

    highlight_store.save_highlights_for_path(
        base_dir,
        "Tweets/Tweets 2026/Tweet - keep-cleaning.html",
        {"highlights": [{"id": "h1", "text": "Cleanup highlighted body."}]},
    )

    args = argparse.Namespace(
        day=day,
        year=2026,
        tweets_dir=tweets_dir,
        output_base=None,
        capture_source="liked",
        cleanup_if_consolidated=True,
    )
    monkeypatch.setattr(mod, "parse_args", lambda: args)
    monkeypatch.setattr(mod.cfg, "BASE_DIR", base_dir)

    exit_code = mod.main()
    assert exit_code == 0

    assert src_md.is_file()
    assert not src_html.exists()
    consolidated_payload = highlight_store.load_highlights_for_path(
        base_dir,
        f"Tweets/Tweets 2026/Tweets {day}.html",
    )
    assert [item["text"] for item in consolidated_payload["highlights"]] == ["Cleanup highlighted body."]
    assert highlight_store.load_highlights_for_path(
        base_dir,
        "Tweets/Tweets 2026/Tweet - keep-cleaning.html",
    )["highlights"] == []


def test_cleanup_only_if_consolidated_keeps_stateful_source_html_and_highlights(
    tmp_path: Path,
    monkeypatch,
) -> None:
    day = "2026-02-13"
    base_dir = tmp_path
    tweets_dir = base_dir / "Tweets" / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    _, src_html = _write_tweet_pair(
        tweets_dir,
        "Tweet - keep-stateful",
        day,
        hour=10,
        body="Stateful highlighted body.",
    )
    consolidated_md = tweets_dir / f"Tweets {day}.md"
    consolidated_html = tweets_dir / f"Tweets {day}.html"
    consolidated_md.write_text("already built", encoding="utf-8")
    consolidated_html.write_text("<html><body>Stateful highlighted body.</body></html>", encoding="utf-8")

    site_state.save_done_state(
        base_dir,
        {
            "version": site_state.STATE_VERSION,
            "items": {
                "Tweets/Tweets 2026/Tweet - keep-stateful.html": {
                    "done_at": "2026-02-13T12:00:00Z",
                },
            },
        },
    )
    highlight_store.save_highlights_for_path(
        base_dir,
        "Tweets/Tweets 2026/Tweet - keep-stateful.html",
        {"highlights": [{"id": "h1", "text": "Stateful highlighted body."}]},
    )

    args = argparse.Namespace(
        day=day,
        year=2026,
        tweets_dir=tweets_dir,
        output_base=None,
        capture_source="liked",
        cleanup_if_consolidated=True,
    )
    monkeypatch.setattr(mod, "parse_args", lambda: args)
    monkeypatch.setattr(mod.cfg, "BASE_DIR", base_dir)

    exit_code = mod.main()
    assert exit_code == 0

    assert src_html.is_file()
    assert site_state.load_done_state(base_dir)["items"] == {
        "Tweets/Tweets 2026/Tweet - keep-stateful.html": {
            "done_at": "2026-02-13T12:00:00Z",
        },
    }
    assert highlight_store.load_highlights_for_path(
        base_dir,
        "Tweets/Tweets 2026/Tweet - keep-stateful.html",
    )["highlights"] == [{"id": "h1", "text": "Stateful highlighted body."}]
    assert highlight_store.load_highlights_for_path(
        base_dir,
        f"Tweets/Tweets 2026/Tweets {day}.html",
    )["highlights"] == []


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
        capture_source="liked",
        cleanup_if_consolidated=True,
    )
    monkeypatch.setattr(mod, "parse_args", lambda: args)

    exit_code = mod.main()
    assert exit_code == 0

    assert src_md.is_file()
    assert src_html.is_file()


def test_collect_daily_source_markdown_filters_posted_only(tmp_path: Path) -> None:
    day = "2026-02-13"
    tweets_dir = tmp_path / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    liked_md, _ = _write_tweet_pair(tweets_dir, "Tweet - liked", day, hour=10, capture_source="liked")
    posted_md, _ = _write_tweet_pair(
        tweets_dir,
        "Tweet posted - posted",
        day,
        hour=11,
        capture_source="posted",
    )

    selected = mod._collect_daily_source_markdown(tweets_dir, day, capture_source="posted")

    assert selected == [posted_md]
    assert liked_md not in selected


def test_collect_daily_source_markdown_includes_reposts_marked_as_posted(tmp_path: Path) -> None:
    day = "2026-02-13"
    tweets_dir = tmp_path / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    repost_md, _ = _write_tweet_pair(
        tweets_dir,
        "Tweet posted - other-author-repost",
        day,
        hour=12,
        capture_source="posted",
    )

    selected = mod._collect_daily_source_markdown(tweets_dir, day, capture_source="posted")

    assert selected == [repost_md]


def test_entry_kind_uses_posted_kind_metadata() -> None:
    assert mod._entry_kind({"tweet_posted_kind": "reply"}) == "Reply"
    assert mod._entry_kind({"tweet_posted_kind": "repost"}) == "Repost"


def test_main_builds_posted_consolidated_without_touching_liked_sources(
    tmp_path: Path,
    monkeypatch,
) -> None:
    day = "2026-02-13"
    tweets_dir = tmp_path / "Tweets 2026"
    tweets_dir.mkdir(parents=True)

    liked_md, liked_html = _write_tweet_pair(
        tweets_dir,
        "Tweet - liked-source",
        day,
        hour=10,
        capture_source="liked",
    )
    posted_md, posted_html = _write_tweet_pair(
        tweets_dir,
        "Tweet posted - posted-source",
        day,
        hour=11,
        capture_source="posted",
    )

    args = argparse.Namespace(
        day=day,
        year=2026,
        tweets_dir=tweets_dir,
        output_base=None,
        capture_source="posted",
        cleanup_if_consolidated=False,
    )
    monkeypatch.setattr(mod, "parse_args", lambda: args)

    exit_code = mod.main()
    assert exit_code == 0

    consolidated_md = tweets_dir / f"Tweets posted {day}.md"
    consolidated_html = tweets_dir / f"Tweets posted {day}.html"
    assert consolidated_md.is_file()
    assert consolidated_html.is_file()
    consolidated_text = consolidated_md.read_text(encoding="utf-8")
    assert "# Consolidado diario de tweets publicados/reposteados/respuestas" in consolidated_text
    assert "Total de ficheros: **1**" in consolidated_text

    assert liked_md.is_file()
    assert posted_md.is_file()
    assert liked_html.is_file()
    assert not posted_html.exists()


def test_clean_body_keeps_compact_line_with_real_content() -> None:
    body = "\n".join(
        [
            "# Tweet by monos estocásticos (@monospodcast)",
            "",
            "[View on X](https://x.com/monospodcast/status/1)",
            "",
            "monos estocásticos@monospodcastOpenClaw se va a OpenAiQuote"
            "Sam Altman@sama·Feb 15Peter Steinberger joins OpenAI"
            "Show more11:04 PM · Feb 15, 2026·965 Views116",
            "",
            "[![image 1](https://pbs.twimg.com/media/example.jpg)](https://pbs.twimg.com/media/example.jpg)",
        ]
    )

    cleaned = mod._clean_body(body)

    assert "OpenClaw se va a OpenAi" in cleaned
    assert "---\n\n#### Tweet citado" in cleaned
    assert "#### Tweet citado" in cleaned
    assert "Sam Altman@sama" in cleaned
    assert "> Sam Altman@sama" not in cleaned
    assert "image 1" in cleaned


def test_clean_body_removes_glued_subscribe_prompt_and_formats_poll() -> None:
    body = "\n".join(
        [
            "# Tweet by Aella (@Aella_Girl)",
            "",
            "[View on X](https://x.com/Aella_Girl/status/1)",
            "",
            "Aella@Aella_GirlSubscribeClick to Subscribe to Aella_Girl"
            "Imagine a circle. Where did it land?"
            "On the red 80.2%On the yellow19.8%"
            "7,864 votes·6 days left"
            "12:49 AM · Apr 26, 2026·397.2K Views3765014.2K875RelevantView quotes",
        ]
    )

    cleaned = mod._clean_body(body)

    assert "SubscribeClick" not in cleaned
    assert "View quotes" not in cleaned
    assert "Aella @Aella_Girl\nImagine a circle." in cleaned
    assert "- On the red: 80.2%" in cleaned
    assert "- On the yellow: 19.8%" in cleaned
    assert "7,864 votes · 6 days left" in cleaned


def test_clean_body_removes_standalone_subscribe_prompt() -> None:
    body = "\n".join(
        [
            "# Tweet by Nathan Lambert (@natolambert)",
            "",
            "[View on X](https://x.com/natolambert/status/1)",
            "",
            "Nathan Lambert",
            "@natolambert",
            "Subscribe",
            "So much rests on which of these trend lines is more representative.",
        ]
    )

    cleaned = mod._clean_body(
        body,
        {
            "tweet_author_name": "Nathan Lambert",
            "tweet_author": "@natolambert",
        },
    )

    assert "Subscribe" not in cleaned
    assert "So much rests on which of these trend lines" in cleaned


def test_clean_body_removes_compact_article_metrics_and_prompt_tail() -> None:
    body = "\n".join(
        [
            "# Tweet by Lisan al Gaib (@scaling01)",
            "",
            "[View on X](https://x.com/scaling01/status/1)",
            "",
            "Lisan al Gaib",
            "@scaling01",
            "The AI model gap is bigger than you think142019430KLike all good articles, this one is a reaction.",
            "If you build something impressive, share it below.Want to publish your own Article?Upgrade to Premium+",
        ]
    )

    cleaned = mod._clean_body(
        body,
        {
            "tweet_author_name": "Lisan al Gaib",
            "tweet_author": "@scaling01",
        },
    )

    assert "142019430K" not in cleaned
    assert "Want to publish" not in cleaned
    assert "Upgrade to Premium" not in cleaned
    assert "The AI model gap is bigger than you think" in cleaned
    assert "Like all good articles, this one is a reaction." in cleaned


def test_clean_body_renders_inline_quoted_tweet_as_historical_section() -> None:
    from bs4 import BeautifulSoup

    body = "\n".join(
        [
            "# Tweet by Demis Hassabis (@demishassabis)",
            "",
            "[View on X](https://x.com/demishassabis/status/1)",
            "",
            "Demis Hassabis@demishassabisThanks for inviting me!Quote"
            "Garry Tan@garrytan·9hTruly an honor and blessing.",
            "> continued quoted line",
            "",
            "[![image 1](https://pbs.twimg.com/media/example.jpg)](https://pbs.twimg.com/media/example.jpg)",
        ]
    )

    cleaned = mod._clean_body(body)
    html_fragment = mod._markdown_to_html_fragment(cleaned)
    soup = BeautifulSoup(html_fragment, "html.parser")

    assert "QuoteGarry" not in cleaned
    assert "---\n\n#### Tweet citado" in cleaned
    assert "> Garry Tan" not in cleaned
    assert "> continued quoted line" not in cleaned
    assert "continued quoted line" in cleaned
    assert "Tweet citado" in soup.get_text(" ", strip=True)
    assert soup.find("blockquote") is None
    assert "Garry Tan@garrytan" in soup.get_text(" ", strip=True)


def test_clean_body_removes_blockquote_markers_inside_quoted_tweet_section() -> None:
    body = "\n".join(
        [
            "# Tweet by Example (@example)",
            "",
            "[View on X](https://x.com/example/status/1)",
            "",
            "Main text",
            "",
            "[View quoted tweet](https://x.com/i/web/status/2)",
            "Quote",
            "> quoted line one",
            "> quoted line two",
        ]
    )

    cleaned = mod._clean_body(body)

    assert "---\n[View quoted tweet](https://x.com/i/web/status/2)\n\n#### Tweet citado" in cleaned
    assert cleaned.count("#### Tweet citado") == 1
    assert "> quoted line" not in cleaned
    assert "quoted line one" in cleaned
    assert "quoted line two" in cleaned


def test_clean_body_does_not_duplicate_existing_quoted_tweet_heading() -> None:
    body = "\n".join(
        [
            "# Tweet by Example (@example)",
            "",
            "[View on X](https://x.com/example/status/1)",
            "",
            "Main text",
            "",
            "---",
            "[View quoted tweet](https://x.com/i/web/status/2)",
            "",
            "#### Tweet citado",
            "",
            "Quoted author @quoted",
            "quoted line",
        ]
    )

    cleaned = mod._clean_body(body)

    assert cleaned.count("#### Tweet citado") == 1
    assert "---\n[View quoted tweet](https://x.com/i/web/status/2)\n\n#### Tweet citado" in cleaned
    assert "Quoted author @quoted" in cleaned
    assert "quoted line" in cleaned


def test_clean_body_removes_legacy_heading_before_quoted_tweet_link() -> None:
    body = "\n".join(
        [
            "# Tweet by Example (@example)",
            "",
            "[View on X](https://x.com/example/status/1)",
            "",
            "Main text",
            "",
            "---",
            "",
            "#### Tweet citado",
            "[View quoted tweet](https://x.com/i/web/status/2)",
            "",
            "#### Tweet citado",
            "",
            "Quoted author @quoted",
            "quoted line",
        ]
    )

    cleaned = mod._clean_body(body)

    assert cleaned.count("#### Tweet citado") == 1
    assert "---\n[View quoted tweet](https://x.com/i/web/status/2)\n\n#### Tweet citado" in cleaned
    assert "Quoted author @quoted" in cleaned
    assert "quoted line" in cleaned


def test_clean_body_escapes_literal_markdown_headings_but_keeps_quote_heading() -> None:
    from bs4 import BeautifulSoup

    body = "\n".join(
        [
            "# Tweet by Example (@example)",
            "",
            "[View on X](https://x.com/example/status/1)",
            "",
            "Texto previo",
            "# =============================================================================",
            "# Bases y Tipos Generales SS",
            "",
            "[View quoted tweet](https://x.com/i/web/status/2)",
            "Quote",
            "quoted line",
        ]
    )

    cleaned = mod._clean_body(body)
    html_fragment = mod._markdown_to_html_fragment(cleaned)
    soup = BeautifulSoup(html_fragment, "html.parser")

    assert "\\# =============================================================================" in cleaned
    assert "\\# Bases y Tipos Generales SS" in cleaned
    assert "#### Tweet citado" in cleaned
    assert soup.find("h1") is None
    assert soup.find("h4").get_text(strip=True) == "Tweet citado"


def test_clean_body_keeps_reply_section_headings_for_html_rendering() -> None:
    from bs4 import BeautifulSoup

    body = "\n".join(
        [
            "# Tweet by Domingo (@domingo)",
            "",
            "[View on X](https://x.com/domingo/status/2)",
            "",
            "#### En respuesta a",
            "",
            "[Ver tweet padre en X](https://x.com/parent/status/1)",
            "",
            "**Parent Author (@parent)**",
            "",
            "Parent body.",
            "",
            "---",
            "",
            "#### Mi respuesta",
            "",
            "My reply.",
        ]
    )

    cleaned = mod._clean_body(body)
    html_fragment = mod._markdown_to_html_fragment(cleaned)
    soup = BeautifulSoup(html_fragment, "html.parser")
    headings = [heading.get_text(strip=True) for heading in soup.find_all("h4")]

    assert "\\#### En respuesta a" not in cleaned
    assert "\\#### Mi respuesta" not in cleaned
    assert headings == ["En respuesta a", "Mi respuesta"]


def test_clean_body_keeps_liked_reply_section_headings_for_html_rendering() -> None:
    from bs4 import BeautifulSoup

    body = "\n".join(
        [
            "# Tweet by Someone (@someone)",
            "",
            "[View on X](https://x.com/someone/status/2)",
            "",
            "#### En respuesta a",
            "",
            "[Ver tweet padre en X](https://x.com/parent/status/1)",
            "",
            "**Parent Author (@parent)**",
            "",
            "Parent body.",
            "",
            "---",
            "",
            "#### Tweet favorito",
            "",
            "Liked reply.",
        ]
    )

    cleaned = mod._clean_body(body)
    html_fragment = mod._markdown_to_html_fragment(cleaned)
    soup = BeautifulSoup(html_fragment, "html.parser")
    headings = [heading.get_text(strip=True) for heading in soup.find_all("h4")]

    assert "\\#### En respuesta a" not in cleaned
    assert "\\#### Tweet favorito" not in cleaned
    assert headings == ["En respuesta a", "Tweet favorito"]


def test_markdown_to_html_fragment_preserves_paragraph_hard_breaks() -> None:
    body = "\n".join(
        [
            "TL;DR:",
            "- Results replicated -",
            "@AnthropicAI",
            "latest models are scoring exceptionally well",
            "- OpenAI and Google models are not doing well and are not improving",
            "",
            "Links:",
            "- Data explorer:",
            "https://petergpt.github.io/bullshit-benchmark/viewer/index.v2.html",
            "- GitHub:",
            "https://github.com/petergpt/bullshit-benchmark",
        ]
    )

    html_fragment = mod._markdown_to_html_fragment(body)

    assert "TL;DR:<br>" in html_fragment
    assert "Links:<br>" in html_fragment
    assert "<a href=\"https://github.com/petergpt/bullshit-benchmark\">" in html_fragment


def test_markdown_to_html_fragment_keeps_x_handles_inline_with_punctuation() -> None:
    body = "\n".join(
        [
            "The work on TST was led by",
            "@bloc97_",
            ",",
            "@gigant_theo",
            ", and",
            "@theemozilla",
            ".",
        ]
    )

    html_fragment = mod._markdown_to_html_fragment(body)

    assert "@bloc97_<br>" not in html_fragment
    assert "@gigant_theo<br>" not in html_fragment
    assert "@theemozilla<br>" not in html_fragment
    assert "@bloc97_, @gigant_theo, and @theemozilla." in html_fragment


def test_markdown_to_html_fragment_joins_inline_x_handle_continuations() -> None:
    body = "\n".join(
        [
            "Replying to @StuartHameroff",
            "and @davidchalmers42",
            "The dumbing down began in the 1990s.",
        ]
    )

    html_fragment = mod._markdown_to_html_fragment(body)

    assert "@StuartHameroff<br>" not in html_fragment
    assert "Replying to @StuartHameroff and @davidchalmers42<br>" in html_fragment


def test_markdown_to_html_fragment_keeps_tight_list_items_clean() -> None:
    body = "\n".join(
        [
            "- Parent item",
            "  - Child item",
            "- Sibling item",
        ]
    )

    html_fragment = mod._markdown_to_html_fragment(body)

    assert "<li><p>" not in html_fragment
    assert "<li><br>" not in html_fragment
    assert html_fragment.count("<li>") == 3


def test_normalize_wrapped_dash_lists_merges_broken_items() -> None:
    import re

    body = "\n".join(
        [
            "TL;DR:",
            "- Results replicated -",
            "@AnthropicAI",
            "latest models are scoring exceptionally well",
            "-",
            "@Alibaba_Qwen",
            "is another very strong performer",
            "- OpenAI and Google models are not doing well and are not improving",
            "Links:",
            "- Data explorer:",
            "https://petergpt.github.io/bullshit-benchmark/viewer/index.v2.html",
            "- GitHub:",
            "https://github.com/petergpt/bullshit-benchmark",
        ]
    )

    normalized = mod._normalize_wrapped_dash_lists(body)

    assert re.search(r"TL;DR:\n+\- Results replicated -", normalized) is not None
    assert "- Results replicated - @AnthropicAI latest models are scoring exceptionally well" in normalized
    assert "- @Alibaba_Qwen is another very strong performer" in normalized
    assert "\n-\n" not in normalized


def test_clean_body_renders_wrapped_dash_lists_as_proper_ul() -> None:
    from bs4 import BeautifulSoup

    body = "\n".join(
        [
            "TL;DR:",
            "- Results replicated -",
            "@AnthropicAI",
            "latest models are scoring exceptionally well",
            "-",
            "@Alibaba_Qwen",
            "is another very strong performer",
            "- OpenAI and Google models are not doing well and are not improving",
            "",
            "Links:",
            "- Data explorer:",
            "https://petergpt.github.io/bullshit-benchmark/viewer/index.v2.html",
            "- GitHub:",
            "https://github.com/petergpt/bullshit-benchmark",
        ]
    )

    cleaned = mod._clean_body(body)
    html_fragment = mod._markdown_to_html_fragment(cleaned)
    soup = BeautifulSoup(html_fragment, "html.parser")

    items = [li.get_text(" ", strip=True) for li in soup.find_all("li")]
    assert "Results replicated - @AnthropicAI latest models are scoring exceptionally well" in items
    assert "@Alibaba_Qwen is another very strong performer" in items
    assert any(item.startswith("Data explorer:") for item in items)
    assert all(li.find("p") is None for li in soup.find_all("li"))


def test_clean_body_renders_arc_links_block_as_list_not_paragraph_breaks() -> None:
    from bs4 import BeautifulSoup

    body = "\n".join(
        [
            "ARC Prize",
            "@arcprize",
            "- Leaderboard:",
            "http://arcprize.org/leaderboard",
            "- Reproduce the results:",
            "http://github.com/arcprize/arc-a...",
            "- Testing policy:",
            "http://arcprize.org/policy",
            "- ARC Prize Foundation is hiring:",
            "http://arcprize.org/jobs",
            "- View raw results:",
            "https://huggingface.co/datasets/arcprize/arc_agi_v1_public_eval/tree/main",
            "",
            "Original link: https://t.co/G6cE2A4K7U",
        ]
    )

    cleaned = mod._clean_body(body)
    html_fragment = mod._markdown_to_html_fragment(cleaned)
    soup = BeautifulSoup(html_fragment, "html.parser")

    assert "<br>\n- Leaderboard:" not in html_fragment
    items = [li.get_text(" ", strip=True) for li in soup.find_all("li")]
    assert any(item.startswith("Leaderboard:") for item in items)
    assert any(item.startswith("Reproduce the results:") for item in items)
    assert any(item.startswith("View raw results:") for item in items)
    assert "Original link:" in soup.get_text(" ", strip=True)
