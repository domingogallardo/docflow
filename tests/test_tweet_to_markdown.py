#!/usr/bin/env python3
"""Tests para utilidades de tweet_to_markdown."""
from utils.tweet_to_markdown import (
    rebuild_urls_from_lines,
    strip_tweet_stats,
    _media_markdown_lines,
)


def test_rebuild_urls_from_lines_merges_wrapped_urls():
    raw = "\n".join(
        [
            "Texto introductorio",
            "https://example.com/path/",
            "segmento",
            "final",
            "Título:",
            "Más texto",
        ]
    )
    result = rebuild_urls_from_lines(raw)
    assert "https://example.com/path/segmentofinal" in result
    assert "segmento" not in result.splitlines()[2]


def test_rebuild_urls_stops_on_ellipsis_or_blank():
    raw = "\n".join(
        [
            "https://example.com/uno/",
            "dos",
            "…",
            "https://example.com/tres/",
            "cuatro",
            "",
            "Fin",
        ]
    )
    result = rebuild_urls_from_lines(raw)
    assert "https://example.com/uno/dos" in result
    assert "https://example.com/tres/cuatro" in result
    assert "Fin" in result.splitlines()[-1]


def test_strip_tweet_stats_removes_metrics_lines():
    raw = "\n".join(
        [
            "Autor",
            "@handle",
            "Texto del tweet que debe quedarse.",
            "",
            "Contenido adicional.",
            "10:25 PM · Jul 13, 2025 · 1.2M Views",
            "12.3K Retweets   900 Quotes   8.1K Likes   300 Bookmarks",
        ]
    )
    result = strip_tweet_stats(raw)
    lines = result.splitlines()
    assert "Texto del tweet que debe quedarse." in lines
    assert "Contenido adicional." in lines
    for metric in ("Views", "Retweets", "Quotes", "Likes", "Bookmarks"):
        assert all(metric not in line for line in lines)


def test_strip_tweet_stats_removes_timestamp_and_counts_block():
    raw = "\n".join(
        [
            "Contenido válido.",
            "",
            "6:47 AM · Nov 10, 2025",
            "·",
            "18.3K",
            "Views",
            "2",
            "24",
            "175",
            "136",
        ]
    )
    result = strip_tweet_stats(raw)
    assert "Contenido válido." in result
    for snippet in ("Nov 10", "18.3K", "Views", "175"):
        assert snippet not in result


def test_media_markdown_lines_include_direct_links():
    lines = _media_markdown_lines(
        [
            "https://pbs.twimg.com/media/img1?format=jpg",
            "https://pbs.twimg.com/media/img2?format=jpg",
        ]
    )
    assert lines[0] == "[![image 1](https://pbs.twimg.com/media/img1?format=jpg)](https://pbs.twimg.com/media/img1?format=jpg)"
    assert lines[1] == "[![image 2](https://pbs.twimg.com/media/img2?format=jpg)](https://pbs.twimg.com/media/img2?format=jpg)"
