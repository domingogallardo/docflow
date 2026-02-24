from __future__ import annotations

import argparse
from pathlib import Path

from utils import highlight_store
from utils import build_daily_highlights_report as mod


def test_main_builds_daily_report_grouped_by_file_and_section(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    html = posts / "doc.html"
    html.write_text(
        "<html><body>"
        "<h1>Main article</h1>"
        "<h2>Section Alpha</h2>"
        "<p>Alpha quote text.</p>"
        "<h2>Section Beta</h2>"
        "<p>Beta quote text.</p>"
        "</body></html>",
        encoding="utf-8",
    )

    rel_path = "Posts/Posts 2026/doc.html"
    highlight_store.save_highlights_for_path(
        base,
        rel_path,
        {
            "title": "Main article",
            "highlights": [
                {
                    "id": "h1",
                    "text": "Alpha quote text.",
                    "created_at": "2026-02-13T09:00:00Z",
                },
                {
                    "id": "h2",
                    "text": "Beta quote text.",
                    "created_at": "2026-02-13T10:00:00Z",
                },
                {
                    "id": "h3",
                    "text": "Should be filtered out.",
                    "created_at": "2026-02-14T08:00:00Z",
                },
            ],
        },
    )

    out_path = tmp_path / "reports" / "2026-02-13.md"
    args = argparse.Namespace(
        day="2026-02-13",
        output=out_path,
        base_dir=str(base),
        intranet_base_url="http://localhost:8080",
    )
    monkeypatch.setattr(mod, "parse_args", lambda: args)

    exit_code = mod.main()
    assert exit_code == 0
    assert out_path.is_file()

    content = out_path.read_text(encoding="utf-8")
    assert "### doc" in content
    assert "**Section Alpha**" in content
    assert "**Section Beta**" in content
    assert "Alpha quote text." in content
    assert "Beta quote text." in content
    assert "Should be filtered out." not in content
    assert "http://localhost:8080/posts/raw/Posts%202026/doc.html" in content
    assert "#:~:text=Alpha%20quote%20text" in content


def test_main_uses_payload_title_when_heading_is_missing(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "base"
    tweets = base / "Tweets" / "Tweets 2026"
    tweets.mkdir(parents=True)

    html = tweets / "tweet-1.html"
    html.write_text(
        "<html><body><p>Tweet body excerpt here.</p></body></html>",
        encoding="utf-8",
    )

    rel_path = "Tweets/Tweets 2026/tweet-1.html"
    highlight_store.save_highlights_for_path(
        base,
        rel_path,
        {
            "title": "Tweet by Alice (@alice)",
            "highlights": [
                {
                    "id": "h1",
                    "text": "Tweet body excerpt here.",
                    "created_at": "2026-02-13T12:00:00Z",
                }
            ],
        },
    )

    out_path = tmp_path / "daily.md"
    args = argparse.Namespace(
        day="2026-02-13",
        output=out_path,
        base_dir=str(base),
        intranet_base_url="http://localhost:8080",
    )
    monkeypatch.setattr(mod, "parse_args", lambda: args)

    exit_code = mod.main()
    assert exit_code == 0

    content = out_path.read_text(encoding="utf-8")
    assert "### tweet-1" in content
    assert "**Tweet by Alice (@alice)**" in content
    assert "http://localhost:8080/tweets/raw/Tweets%202026/tweet-1.html" in content


def test_main_writes_empty_report_when_no_highlights_for_day(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    html = posts / "doc.html"
    html.write_text("<html><body><p>Doc text.</p></body></html>", encoding="utf-8")

    rel_path = "Posts/Posts 2026/doc.html"
    highlight_store.save_highlights_for_path(
        base,
        rel_path,
        {
            "highlights": [
                {
                    "id": "h1",
                    "text": "Doc text.",
                    "created_at": "2026-02-14T09:00:00Z",
                }
            ]
        },
    )

    out_path = tmp_path / "daily.md"
    args = argparse.Namespace(
        day="2026-02-13",
        output=out_path,
        base_dir=str(base),
        intranet_base_url="http://localhost:8080",
    )
    monkeypatch.setattr(mod, "parse_args", lambda: args)

    exit_code = mod.main()
    assert exit_code == 0

    content = out_path.read_text(encoding="utf-8")
    assert "Total highlights: **0**" in content
    assert "_No highlights found for this day._" in content
