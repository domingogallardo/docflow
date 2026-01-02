#!/usr/bin/env python3
"""Tests para utilidades de tweet_to_markdown."""
from utils.tweet_to_markdown import (
    rebuild_urls_from_lines,
    strip_tweet_stats,
    _media_markdown_lines,
    _insert_quote_separator,
    _pick_quoted_tweet_url,
    _has_quote_marker,
    _insert_media_before_quote,
    _status_id_from_url,
    _find_quoted_status_id,
    _quoted_url_from_graphql_id,
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


def test_insert_quote_separator_adds_hr_before_quote():
    raw = "\n".join(
        [
            "Texto del tweet.",
            "Quote",
            "@autor",
            "Texto citado.",
        ]
    )
    result = _insert_quote_separator(raw)
    expected = "\n".join(
        [
            "Texto del tweet.",
            "",
            "---",
            "Quote",
            "@autor",
            "Texto citado.",
        ]
    )
    assert result == expected


def test_insert_quote_separator_adds_quoted_link_after_hr():
    raw = "\n".join(
        [
            "Texto del tweet.",
            "Quote",
            "@autor",
            "Texto citado.",
        ]
    )
    result = _insert_quote_separator(raw, "https://x.com/i/web/status/999")
    expected = "\n".join(
        [
            "Texto del tweet.",
            "",
            "---",
            "[View quoted tweet](https://x.com/i/web/status/999)",
            "Quote",
            "@autor",
            "Texto citado.",
        ]
    )
    assert result == expected


def test_insert_quote_separator_ignores_inline_quote_word():
    raw = "Linea con quote en medio."
    assert _insert_quote_separator(raw) == raw


def test_insert_media_before_quote_places_block_before_hr():
    raw = "\n".join(
        [
            "Texto del tweet.",
            "",
            "---",
            "[View quoted tweet](https://x.com/i/web/status/999)",
            "Quote",
            "Texto citado.",
        ]
    )
    media = ["[![image 1](https://example.com/img.jpg)](https://example.com/img.jpg)"]
    result = _insert_media_before_quote(raw, media)
    expected = "\n".join(
        [
            "Texto del tweet.",
            "",
            "[![image 1](https://example.com/img.jpg)](https://example.com/img.jpg)",
            "",
            "---",
            "[View quoted tweet](https://x.com/i/web/status/999)",
            "Quote",
            "Texto citado.",
        ]
    )
    assert result == expected


def test_pick_quoted_tweet_url_skips_self_and_picks_next():
    hrefs = [
        "/user/status/12345",
        "https://x.com/other/status/999",
    ]
    assert (
        _pick_quoted_tweet_url(hrefs, "https://x.com/user/status/12345")
        == "https://x.com/other/status/999"
    )


def test_pick_quoted_tweet_url_accepts_i_web_status():
    hrefs = [
        "/user/status/12345",
        "/i/web/status/9876543210",
    ]
    assert (
        _pick_quoted_tweet_url(hrefs, "https://x.com/user/status/12345")
        == "https://x.com/i/web/status/9876543210"
    )


def test_has_quote_marker_detects_standalone_quote_line():
    raw = "\n".join(["Texto", "Quote", "Mas texto"])
    assert _has_quote_marker(raw) is True


def test_status_id_from_url_handles_status_variants():
    assert _status_id_from_url("https://x.com/user/status/12345") == "12345"
    assert _status_id_from_url("https://x.com/i/web/status/987654") == "987654"
    assert _status_id_from_url("https://x.com/user") is None


def test_find_quoted_status_id_from_graphql():
    payload = {
        "data": {"tweetResult": {"quoted_status_id_str": "999"}},
    }
    assert _find_quoted_status_id(payload) == "999"


def test_find_quoted_status_id_from_quoted_result():
    payload = {
        "quoted_status_result": {
            "result": {"rest_id": "888"},
        }
    }
    assert _find_quoted_status_id(payload) == "888"


def test_quoted_url_from_graphql_id_skips_self():
    tweet_url = "https://x.com/user/status/123"
    assert _quoted_url_from_graphql_id("123", tweet_url) is None
    assert (
        _quoted_url_from_graphql_id("456", tweet_url)
        == "https://x.com/i/web/status/456"
    )


def test_media_markdown_lines_include_direct_links():
    lines = _media_markdown_lines(
        [
            "https://pbs.twimg.com/media/img1?format=jpg",
            "https://pbs.twimg.com/media/img2?format=jpg",
        ]
    )
    assert lines[0] == "[![image 1](https://pbs.twimg.com/media/img1?format=jpg)](https://pbs.twimg.com/media/img1?format=jpg)"
    assert lines[1] == "[![image 2](https://pbs.twimg.com/media/img2?format=jpg)](https://pbs.twimg.com/media/img2?format=jpg)"
