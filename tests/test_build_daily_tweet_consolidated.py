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


def test_main_keeps_source_markdown_and_removes_source_html_after_consolidation(
    tmp_path: Path, monkeypatch
) -> None:
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

    assert md1.exists()
    assert md2.exists()
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


def test_cleanup_only_if_consolidated_keeps_md_and_removes_html_without_rebuild(
    tmp_path: Path, monkeypatch
) -> None:
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
    assert src_md.is_file()
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
    assert "image 1" in cleaned


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
