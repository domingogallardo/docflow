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
    _wait_for_tweet_detail,
    _detect_access_issue,
    PlaywrightTimeoutError,
    _expand_show_more,
    _read_article_text,
    _resolve_thread_context,
    _select_thread_indices,
    _extract_thread_ids_from_payload,
    _build_single_tweet_markdown,
    TweetParts,
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


def test_rebuild_urls_stops_on_ellipsis_with_trailing_text():
    raw = "\n".join(
        [
            "Texto introductorio",
            "https://example.com/path/",
            "segmento",
            "… y sigue el texto.",
            "Cierre",
        ]
    )
    result = rebuild_urls_from_lines(raw)
    lines = result.splitlines()
    assert "https://example.com/path/segmento" in result
    assert "… y sigue el texto." not in result
    assert any("y sigue el texto." in line for line in lines)


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


def test_strip_tweet_stats_keeps_compact_line_with_real_content():
    raw = (
        "monos estocásticos@monospodcastOpenClaw se va a OpenAiQuote"
        "Sam Altman@sama·Feb 15Peter Steinberger joins OpenAI"
        "Show more11:04 PM · Feb 15, 2026·965 Views116"
    )
    result = strip_tweet_stats(raw)
    assert "OpenClaw se va a OpenAi" in result
    assert result.strip() != ""


def test_strip_tweet_stats_removes_trailing_show_more_after_metrics():
    raw = "\n".join(
        [
            "Contenido válido.",
            "Show more",
            "11:04 PM · Feb 15, 2026",
            "·",
            "965",
            "Views",
            "1",
            "16",
        ]
    )
    result = strip_tweet_stats(raw)
    assert result == "Contenido válido."


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


def test_build_single_tweet_markdown_includes_external_link_without_media():
    parts = TweetParts(
        author_name="Autor",
        author_handle="@autor",
        body_text="Texto del tweet.",
        avatar_url=None,
        trailing_media_lines=[],
        media_present=False,
        external_link="https://example.com/post",
    )
    md = _build_single_tweet_markdown(parts, "https://x.com/autor/status/123")
    assert "Original link: https://example.com/post" in md


def test_build_single_tweet_markdown_skips_duplicate_external_link():
    parts = TweetParts(
        author_name="Autor",
        author_handle="@autor",
        body_text="Texto https://example.com/post/ con enlace.",
        avatar_url=None,
        trailing_media_lines=[],
        media_present=False,
        external_link="https://example.com/post",
    )
    md = _build_single_tweet_markdown(parts, "https://x.com/autor/status/123")
    assert "Original link: https://example.com/post" not in md


def test_wait_for_tweet_detail_returns_payload():
    class FakeResponse:
        url = "https://x.com/i/api/graphql/xyz/TweetDetail"

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class FakeContext:
        def __init__(self, response):
            self.value = response

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakePage:
        def expect_response(self, predicate, timeout):
            resp = FakeResponse({"ok": True})
            assert predicate(resp)
            assert timeout == 123
            return FakeContext(resp)

    assert _wait_for_tweet_detail(FakePage(), 123) == {"ok": True}


def test_wait_for_tweet_detail_returns_none_on_timeout():
    class FakePage:
        def expect_response(self, predicate, timeout):
            raise PlaywrightTimeoutError("timeout")

    assert _wait_for_tweet_detail(FakePage(), 50) is None


def test_wait_for_tweet_detail_returns_none_on_bad_json():
    class FakeResponse:
        url = "https://x.com/i/api/graphql/xyz/TweetDetail"

        def json(self):
            raise ValueError("bad")

    class FakeContext:
        def __init__(self, response):
            self.value = response

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakePage:
        def expect_response(self, predicate, timeout):
            resp = FakeResponse()
            assert predicate(resp)
            return FakeContext(resp)

    assert _wait_for_tweet_detail(FakePage(), 100) is None


def test_expand_show_more_clicks_buttons_and_waits():
    clicked: list[int | None] = []
    waits: list[int] = []

    class FakeButton:
        def __init__(self, bucket):
            self.bucket = bucket

        def click(self, timeout=None):
            self.bucket.append(timeout)

    class FakeLocator:
        def __init__(self, count, bucket):
            self._count = count
            self._bucket = bucket

        def count(self):
            return self._count

        def nth(self, idx):
            return FakeButton(self._bucket)

    class FakeArticle:
        def get_by_role(self, role, name, exact):
            if role == "button" and name == "Show more" and exact:
                return FakeLocator(2, clicked)
            return FakeLocator(0, clicked)

        def locator(self, selector):
            raise AssertionError("fallback should not be used")

    class FakePage:
        def wait_for_timeout(self, wait_ms):
            waits.append(wait_ms)

    _expand_show_more(FakeArticle(), FakePage(), wait_ms=123)
    assert len(clicked) == 2
    assert waits == [123, 123]


def test_expand_show_more_ignores_non_button_text_nodes():
    clicked: list[int | None] = []
    waits: list[int] = []

    class FakeButton:
        def __init__(self, bucket):
            self.bucket = bucket

        def click(self, timeout=None):
            self.bucket.append(timeout)

    class FakeLocator:
        def __init__(self, count, bucket):
            self._count = count
            self._bucket = bucket

        def count(self):
            return self._count

        def nth(self, idx):
            return FakeButton(self._bucket)

    class FakeArticle:
        def get_by_role(self, role, name, exact):
            return FakeLocator(0, clicked)

        def locator(self, selector):
            if selector == 'text="Show more"':
                return FakeLocator(1, clicked)
            return FakeLocator(0, clicked)

    class FakePage:
        def wait_for_timeout(self, wait_ms):
            waits.append(wait_ms)

    _expand_show_more(FakeArticle(), FakePage(), wait_ms=50)
    assert len(clicked) == 0
    assert waits == []


def test_resolve_thread_context_prefers_like_metadata():
    result = _resolve_thread_context(
        like_author_handle="@like",
        like_time_text="2h",
        like_time_datetime="2026-01-10T12:00:00.000Z",
        target_author_handle="@target",
        target_time_text="1h",
        target_time_datetime="2026-01-10T13:00:00.000Z",
    )
    assert result == ("@like", "2h", "2026-01-10T12:00:00.000Z")


def test_resolve_thread_context_falls_back_to_target():
    result = _resolve_thread_context(
        like_author_handle=None,
        like_time_text=None,
        like_time_datetime=None,
        target_author_handle="@target",
        target_time_text="1h",
        target_time_datetime="2026-01-10T13:00:00.000Z",
    )
    assert result == ("@target", "1h", "2026-01-10T13:00:00.000Z")


def test_read_article_text_retries_on_timeout(monkeypatch):
    calls = {"first": 0, "second": 0}

    class FakeArticle:
        def __init__(self, key):
            self.key = key

        def inner_text(self, timeout=None):
            calls[self.key] += 1
            if self.key == "first":
                raise PlaywrightTimeoutError("timeout")
            return "ok"

        def text_content(self, timeout=None):
            return None

        def evaluate(self, script):
            return "ok-eval"

    class FakePage:
        def wait_for_timeout(self, wait_ms):
            return None

    refreshed = FakeArticle("second")

    def fake_locate(page, tweet_url, timeout_ms=15000):
        assert tweet_url == "https://x.com/user/status/1"
        return refreshed

    monkeypatch.setattr("utils.tweet_to_markdown._locate_tweet_article", fake_locate)
    monkeypatch.setattr("utils.tweet_to_markdown._expand_show_more", lambda *args, **kwargs: None)

    result = _read_article_text(
        FakeArticle("first"),
        "https://x.com/user/status/1",
        page=FakePage(),
        timeout_ms=10,
    )
    assert result == "ok"
    assert calls == {"first": 1, "second": 1}


def test_read_article_text_uses_text_content_fallback():
    class FakeArticle:
        def inner_text(self, timeout=None):
            raise PlaywrightTimeoutError("timeout")

        def text_content(self, timeout=None):
            return "fallback"

        def evaluate(self, script):
            return "ok-eval"

    result = _read_article_text(
        FakeArticle(),
        "https://x.com/user/status/1",
        page=None,
        timeout_ms=10,
    )
    assert result == "fallback"


def test_read_article_text_uses_page_evaluate_fallback():
    class FakeArticle:
        def inner_text(self, timeout=None):
            raise PlaywrightTimeoutError("timeout")

        def text_content(self, timeout=None):
            raise PlaywrightTimeoutError("timeout")

        def evaluate(self, script):
            return "ok-eval"

    class FakePage:
        def locator(self, selector):
            assert selector == "a[href*='/status/1']"
            return FakeLocator()

    class FakeLocator:
        def __init__(self):
            self.first = self

        def evaluate(self, script):
            return "evaluated"

    result = _read_article_text(
        FakeArticle(),
        "https://x.com/user/status/1",
        page=FakePage(),
        timeout_ms=10,
    )
    assert result == "evaluated"


def test_read_article_text_uses_anchor_handle_first():
    class FakeArticle:
        def inner_text(self, timeout=None):
            raise PlaywrightTimeoutError("timeout")

        def text_content(self, timeout=None):
            return None

        def evaluate(self, script):
            return "ok-eval"

    class FakeHandle:
        def evaluate(self, script):
            return "from-handle"

    result = _read_article_text(
        FakeArticle(),
        "https://x.com/user/status/1",
        page=None,
        anchor_handle=FakeHandle(),
        timeout_ms=10,
    )
    assert result == "from-handle"


def test_read_article_text_prefers_richer_page_text_over_compact_anchor():
    class FakeArticle:
        def inner_text(self, timeout=None):
            raise AssertionError("should not call inner_text when richer text is available")

    class FakeHandle:
        def evaluate(self, script):
            return "compact-from-anchor"

    class FakeLocator:
        def __init__(self):
            self.first = self

        def evaluate(self, script):
            return "line 1\nline 2 from page"

    class FakePage:
        def locator(self, selector):
            assert selector == "a[href*='/status/1']"
            return FakeLocator()

    result = _read_article_text(
        FakeArticle(),
        "https://x.com/user/status/1",
        page=FakePage(),
        anchor_handle=FakeHandle(),
        timeout_ms=10,
    )
    assert result == "line 1\nline 2 from page"


def test_select_thread_indices_requires_context():
    entries = [("@user", "4h", None), ("@user", "4h", None)]
    assert _select_thread_indices(entries, 1, author_handle=None, time_text="4h", anchor_time_datetime=None) == [1]
    assert _select_thread_indices(entries, 1, author_handle="@user", time_text=None, anchor_time_datetime=None) == [1]


def test_select_thread_indices_collects_contiguous_matches():
    entries = [("@user", "4h", None), ("@user", "4h", None), ("@user", "4h", None)]
    assert _select_thread_indices(entries, 2, author_handle="@user", time_text="4h", anchor_time_datetime=None) == [0, 1, 2]


def test_select_thread_indices_stops_on_first_mismatch():
    entries = [("@user", "4h", None), ("@other", "4h", None), ("@user", "4h", None)]
    assert _select_thread_indices(entries, 2, author_handle="@user", time_text="4h", anchor_time_datetime=None) == [2]


def test_select_thread_indices_uses_datetime_window():
    entries = [
        ("@user", "32m", "2026-01-09T16:54:22.000Z"),
        ("@user", "27m", "2026-01-09T16:59:23.000Z"),
    ]
    selected = _select_thread_indices(
        entries,
        1,
        author_handle="@user",
        time_text="27m",
        anchor_time_datetime="2026-01-09T16:59:23.000Z",
    )
    assert selected == [0, 1]


def test_select_thread_indices_respects_datetime_window_limit():
    entries = [
        ("@user", "2d", "2026-01-07T10:00:00.000Z"),
        ("@user", "1h", "2026-01-09T12:30:00.000Z"),
    ]
    selected = _select_thread_indices(
        entries,
        1,
        author_handle="@user",
        time_text="1h",
        anchor_time_datetime="2026-01-09T12:30:00.000Z",
    )
    assert selected == [1]


def test_extract_thread_ids_from_payload_filters_author_and_time():
    payload = {
        "data": {
            "threaded_conversation_with_injections_v2": {
                "instructions": [
                    {
                        "type": "TimelineAddEntries",
                        "entries": [
                            {
                                "entryId": "tweet-1",
                                "content": {
                                    "itemContent": {
                                        "tweet_results": {
                                            "result": {
                                                "__typename": "Tweet",
                                                "rest_id": "111",
                                                "core": {
                                                    "user_results": {
                                                        "result": {
                                                            "core": {
                                                                "screen_name": "author",
                                                            }
                                                        }
                                                    }
                                                },
                                                "legacy": {
                                                    "created_at": "Thu Jan 08 10:00:00 +0000 2026"
                                                },
                                            }
                                        }
                                    }
                                },
                            },
                            {
                                "entryId": "tweet-2",
                                "content": {
                                    "itemContent": {
                                        "tweet_results": {
                                            "result": {
                                                "__typename": "Tweet",
                                                "rest_id": "222",
                                                "core": {
                                                    "user_results": {
                                                        "result": {
                                                            "core": {
                                                                "screen_name": "other",
                                                            }
                                                        }
                                                    }
                                                },
                                                "legacy": {
                                                    "created_at": "Thu Jan 08 11:00:00 +0000 2026"
                                                },
                                            }
                                        }
                                    }
                                },
                            },
                        ],
                    }
                ]
            }
        }
    }
    ids = _extract_thread_ids_from_payload(
        payload,
        author_handle="@author",
        anchor_time_datetime="2026-01-08T12:00:00.000Z",
    )
    assert ids == ["111"]


def test_detect_access_issue_flags_login_url():
    class FakeLocator:
        def __init__(self, count=0):
            self._count = count

        def count(self):
            return self._count

    class FakePage:
        def __init__(self, url):
            self.url = url

        def locator(self, selector):
            return FakeLocator(0)

    page = FakePage("https://x.com/i/flow/login")
    assert _detect_access_issue(page) == "X requires login (login wall)."


def test_detect_access_issue_flags_unavailable_text():
    class FakeLocator:
        def __init__(self, count=0):
            self._count = count

        def count(self):
            return self._count

    class FakePage:
        def __init__(self, hits):
            self.url = "https://x.com/someone/status/1"
            self._hits = hits

        def locator(self, selector):
            return FakeLocator(self._hits.get(selector, 0))

    page = FakePage({"text=This Post is unavailable": 1})
    assert (
        _detect_access_issue(page)
        == "Tweet unavailable (deleted, protected, or restricted)."
    )
