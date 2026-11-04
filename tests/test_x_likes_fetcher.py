#!/usr/bin/env python3
from datetime import datetime, timezone

from utils import x_likes_fetcher as xl


class FakeLink:
    def __init__(self, href: str):
        self.href = href

    def get_attribute(self, name: str):
        if name == "href":
            return self.href
        return None


class FakeSocialContext:
    def __init__(self, text: str, hrefs=None):
        self.text = text
        self.hrefs = hrefs or []

    def inner_text(self):
        return self.text

    def query_selector_all(self, selector):
        if selector == "a[href]":
            return [FakeLink(href) for href in self.hrefs]
        return []


class FakeSpan:
    def __init__(self, text: str):
        self.text = text

    def inner_text(self):
        return self.text


class FakeTime:
    def __init__(self, text: str | None = None, datetime_value: str | None = None):
        self.text = text or ""
        self.datetime_value = datetime_value

    def inner_text(self):
        return self.text

    def get_attribute(self, name: str):
        if name == "datetime":
            return self.datetime_value
        return None


class FakeTextBlock:
    def __init__(self, text: str):
        self.text = text

    def inner_text(self):
        return self.text


class FakeTextLocator:
    def __init__(self, texts):
        self.texts = texts

    def count(self):
        return len(self.texts)

    def nth(self, index):
        return FakeTextBlock(self.texts[index])


class FakeArticle:
    def __init__(
        self,
        hrefs,
        *,
        spans=None,
        social_contexts=None,
        time_href: str | None = None,
        time_text: str | None = None,
        time_datetime: str | None = None,
        text: str | None = None,
        tweet_texts=None,
    ):
        self.hrefs = hrefs
        self.spans = spans or []
        self.social_contexts = social_contexts or []
        self.time_href = time_href
        self.time_text = time_text
        self.time_datetime = time_datetime
        self.text = text
        self.tweet_texts = tweet_texts or []

    def inner_text(self):
        return self.text or "\n".join(self.spans)

    def query_selector_all(self, selector):
        if selector == "a[href*='/status/']":
            return [FakeLink(href) for href in self.hrefs]
        if selector == "span":
            return [FakeSpan(text) for text in self.spans]
        if selector == "[data-testid='socialContext']":
            contexts = []
            for context in self.social_contexts:
                if isinstance(context, tuple):
                    text, hrefs = context
                    contexts.append(FakeSocialContext(text, hrefs))
                else:
                    contexts.append(FakeSocialContext(context))
            return contexts
        return []

    def query_selector(self, selector):
        if selector == "a:has(time)":
            href = self.time_href or (self.hrefs[0] if self.hrefs else None)
            return FakeLink(href) if href else None
        if selector == "time":
            if self.time_text is None and self.time_datetime is None:
                return None
            return FakeTime(self.time_text, self.time_datetime)
        return None

    def locator(self, selector):
        assert selector == "[data-testid='tweetText']"
        return FakeTextLocator(self.tweet_texts)


class FakeLocator:
    def __init__(self, articles):
        self._articles = articles

    def element_handles(self):
        return self._articles

    def count(self):
        return len(self._articles)


class FakePage:
    def __init__(self, articles):
        self._locator = FakeLocator(articles)

    def locator(self, selector: str):
        assert selector == "article"
        return self._locator


def test_normalize_stop_url_handles_relative_and_spaces():
    assert xl._normalize_stop_url("  /user/status/42  ") == "https://x.com/user/status/42"
    assert xl._normalize_stop_url(None) is None


def test_extract_timeline_items_filters_to_expected_author():
    articles = [
        FakeArticle(
            ["/domingo/status/1"],
            spans=["Domingo", "@domingo"],
            time_href="/domingo/status/1",
            time_text="1h",
            time_datetime="2026-04-21T10:00:00.000Z",
        ),
        FakeArticle(
            ["/other/status/2"],
            spans=["Other", "@other"],
            time_href="/other/status/2",
            time_text="2h",
            time_datetime="2026-04-21T09:00:00.000Z",
        ),
    ]

    items = xl._extract_timeline_items(
        FakePage(articles),
        set(),
        expected_author_handle="@domingo",
    )

    assert [item.url for item in items] == ["https://x.com/domingo/status/1"]
    assert items[0].text == "Domingo\n@domingo"


def test_parse_timeline_datetime_normalizes_to_utc():
    parsed = xl._parse_timeline_datetime("2026-08-03T01:30:00+02:00")

    assert parsed == datetime(2026, 8, 2, 23, 30, tzinfo=timezone.utc)
    assert xl._parse_timeline_datetime("not-a-date") is None


def test_extract_timeline_items_prefers_semantic_text_and_flags_truncation():
    article = FakeArticle(
        ["/domingo/status/1"],
        spans=["Domingo", "@domingo"],
        time_href="/domingo/status/1",
        text="Domingo\n@domingo\nSemantic content\nShow more\n1\n2\n3",
        tweet_texts=["Semantic content", "Quoted context"],
    )

    items = xl._extract_timeline_items(
        FakePage([article]),
        set(),
        expected_author_handle="@domingo",
    )

    assert items[0].text == "Semantic content\n\nQuoted context"
    assert items[0].text_truncated is True


def test_extract_timeline_items_includes_reposts_when_requested():
    articles = [
        FakeArticle(
            ["/other/status/2"],
            spans=["Domingo reposted", "Other", "@other"],
            social_contexts=[("Domingo reposted", ["/domingo"])],
            time_href="/other/status/2",
            time_text="2h",
            time_datetime="2026-04-21T09:00:00.000Z",
        ),
    ]

    items = xl._extract_timeline_items(
        FakePage(articles),
        set(),
        expected_author_handle="@domingo",
        include_reposts=True,
    )

    assert [item.url for item in items] == ["https://x.com/other/status/2"]
    assert items[0].author_name == "Other"
    assert items[0].author_handle == "@other"


def test_extract_timeline_items_excludes_reposts_by_default():
    articles = [
        FakeArticle(
            ["/other/status/2"],
            spans=["Domingo reposted", "Other", "@other"],
            social_contexts=[("Domingo reposted", ["/domingo"])],
            time_href="/other/status/2",
            time_text="2h",
        ),
    ]

    items = xl._extract_timeline_items(
        FakePage(articles),
        set(),
        expected_author_handle="@domingo",
    )

    assert items == []


def test_extract_timeline_items_ignores_reposts_from_other_profile_contexts():
    articles = [
        FakeArticle(
            ["/other/status/2"],
            spans=["Someone reposted", "Other", "@other"],
            social_contexts=[("Someone reposted", ["/someone"])],
            time_href="/other/status/2",
            time_text="2h",
        ),
    ]

    items = xl._extract_timeline_items(
        FakePage(articles),
        set(),
        expected_author_handle="@domingo",
        include_reposts=True,
    )

    assert items == []


def test_extract_timeline_items_skips_pinned_articles_when_requested():
    articles = [
        FakeArticle(
            ["/domingo/status/1"],
            spans=["Pinned", "Domingo", "@domingo"],
            time_href="/domingo/status/1",
            time_text="1h",
        ),
        FakeArticle(
            ["/domingo/status/2"],
            spans=["Domingo", "@domingo"],
            time_href="/domingo/status/2",
            time_text="32m",
        ),
    ]

    items = xl._extract_timeline_items(
        FakePage(articles),
        set(),
        expected_author_handle="@domingo",
        exclude_pinned=True,
    )

    assert [item.url for item in items] == ["https://x.com/domingo/status/2"]


def test_fetch_post_items_includes_reposts(monkeypatch):
    captured = {}

    def fake_fetch(*args, **kwargs):
        captured.update(kwargs)
        return [], False, 0

    monkeypatch.setattr(xl, "fetch_timeline_items_with_state", fake_fetch)

    xl.fetch_post_items_with_state("state.json", posts_url="https://x.com/domingo")

    assert captured["expected_author_handle"] == "@domingo"
    assert captured["exclude_pinned"] is True
    assert captured["include_reposts"] is True


def test_reply_items_from_payload_collects_only_expected_author_replies():
    payload = {
        "tweets": [
            {
                "__typename": "Tweet",
                "rest_id": "1",
                "core": {
                    "user_results": {
                        "result": {
                            "core": {
                                "screen_name": "domingo",
                                "name": "Domingo",
                            }
                        }
                    }
                },
                "legacy": {
                    "in_reply_to_status_id_str": "99",
                    "in_reply_to_screen_name": "other",
                },
            },
            {
                "__typename": "Tweet",
                "rest_id": "2",
                "core": {
                    "user_results": {
                        "result": {
                            "core": {
                                "screen_name": "domingo",
                                "name": "Domingo",
                            }
                        }
                    }
                },
                "legacy": {},
            },
            {
                "__typename": "Tweet",
                "rest_id": "3",
                "core": {
                    "user_results": {
                        "result": {
                            "core": {
                                "screen_name": "someone",
                                "name": "Someone",
                            }
                        }
                    }
                },
                "legacy": {
                    "in_reply_to_status_id_str": "88",
                    "in_reply_to_screen_name": "other",
                },
            },
        ]
    }

    items = xl._reply_items_from_payload(payload, expected_author_handle="@domingo")

    assert [item.url for item in items] == ["https://x.com/domingo/status/1"]
    assert items[0].posted_kind == "reply"
    assert items[0].reply_to_url == "https://x.com/other/status/99"


def _reply_payload(tweet_id, *, author="domingo"):
    return {"__typename": "Tweet", "rest_id": str(tweet_id),
            "core": {"user_results": {"result": {"core": {"screen_name": author}}}},
            "legacy": {"in_reply_to_status_id_str": "99", "in_reply_to_screen_name": "other"}}


class ReplyScrollPage:
    """Deliver simulated X response events without browser or network access."""

    def __init__(self, payload_at, *, growing_articles=False, operation="UserRepliesTimeline"):
        self.payload_at = payload_at
        self.growing_articles = growing_articles
        self.scrolls = 0
        self.mouse = self
        self.operation = operation

    def on(self, event, callback):
        assert event == "response"
        self.callback = callback

    def _respond(self):
        payload = self.payload_at(self.scrolls)
        response = type("Response", (), {
            "url": f"https://x.com/i/api/graphql/example/{self.operation}",
            "json": lambda _self: payload,
        })()
        self.callback(response)

    def goto(self, *_args, **_kwargs):
        self._respond()

    def locator(self, selector):
        assert selector == "article"
        return self

    def count(self):
        return 6 + self.scrolls if self.growing_articles else 6

    def wheel(self, *_args):
        self.scrolls += 1
        assert self.scrolls <= 35, "Replies loop did not terminate"

    def wait_for_timeout(self, _milliseconds):
        self._respond()


def _collect_fake_replies(page, monkeypatch, **kwargs):
    monkeypatch.setattr(xl, "_dismiss_cookie_prompt", lambda _page: None)
    monkeypatch.setattr(xl, "_wait_for_timeline_articles", lambda *_args, **_kwargs: True)
    return xl.collect_reply_items_from_page(
        page, "https://x.com/domingo/with_replies", expected_author_handle="domingo", **kwargs
    )


def test_replies_repeated_payloads_do_not_reset_idle_limit(monkeypatch):
    page = ReplyScrollPage(lambda _scroll: _reply_payload("1", author="other"))
    success, _, items, stop_found, _ = _collect_fake_replies(page, monkeypatch)
    assert success and not items and not stop_found
    assert page.scrolls == 20


def test_replies_continuous_unrelated_payloads_have_total_scroll_limit(monkeypatch, capsys):
    page = ReplyScrollPage(lambda scroll: _reply_payload(scroll, author="other"), growing_articles=True)
    success, _, items, _, _ = _collect_fake_replies(page, monkeypatch)
    assert success and not items
    assert page.scrolls == 30
    output = capsys.readouterr().out
    assert "Replies progress: 5/30 scrolls" in output
    assert "results may be incomplete" in output


def test_replies_process_payload_from_last_allowed_scroll(monkeypatch, capsys):
    page = ReplyScrollPage(
        lambda scroll: _reply_payload(scroll, author="domingo" if scroll == 30 else "other")
    )
    _, _, items, _, _ = _collect_fake_replies(page, monkeypatch, max_tweets=1)
    assert [item.url for item in items] == ["https://x.com/domingo/status/30"]
    assert page.scrolls == 30
    assert "results may be incomplete" not in capsys.readouterr().out


def test_replies_stop_at_checkpoint_without_scrolling(monkeypatch):
    page = ReplyScrollPage(lambda _scroll: _reply_payload("1"))
    _, _, items, stop_found, _ = _collect_fake_replies(
        page, monkeypatch, stop_at_url="https://x.com/domingo/status/1"
    )
    assert stop_found and not items
    assert page.scrolls == 0


def test_replies_detects_previous_external_operation_name(monkeypatch):
    page = ReplyScrollPage(lambda _scroll: _reply_payload("1"), operation="UserTweetsAndReplies")
    _, _, items, _, _ = _collect_fake_replies(page, monkeypatch, max_tweets=1)
    assert [item.url for item in items] == ["https://x.com/domingo/status/1"]


def test_replies_without_matching_payload_is_not_reported_as_success(monkeypatch, capsys):
    page = ReplyScrollPage(lambda _scroll: _reply_payload("1"), operation="UnrelatedTimeline")
    success, _, items, stop_found, _ = _collect_fake_replies(page, monkeypatch)
    assert not success and not items and not stop_found
    assert "replies could not be verified" in capsys.readouterr().out


def test_fetch_reply_items_requires_with_replies_timeline(tmp_path, monkeypatch):
    captured = {}

    class FakeContext:
        def add_init_script(self, script):
            return None

        def new_page(self):
            return object()

        def close(self):
            return None

    class FakeBrowser:
        def new_context(self, **kwargs):
            return FakeContext()

        def close(self):
            return None

    class FakeChromium:
        def launch(self, **kwargs):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    def fake_sync_playwright():
        return FakePlaywright()

    def fake_collect(page, replies_url, **kwargs):
        captured["replies_url"] = replies_url
        captured.update(kwargs)
        return True, 0, [], False, None

    monkeypatch.setattr(xl, "sync_playwright", fake_sync_playwright)
    monkeypatch.setattr(xl, "collect_reply_items_from_page", fake_collect)
    state_path = tmp_path / "state.json"
    state_path.write_text("{}", encoding="utf-8")

    xl.fetch_reply_items_with_state(
        state_path,
        replies_url="https://x.com/domingo/with_replies",
    )

    assert captured["replies_url"] == "https://x.com/domingo/with_replies"
    assert captured["expected_author_handle"] == "@domingo"
