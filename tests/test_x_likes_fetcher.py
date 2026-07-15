#!/usr/bin/env python3
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
    ):
        self.hrefs = hrefs
        self.spans = spans or []
        self.social_contexts = social_contexts or []
        self.time_href = time_href
        self.time_text = time_text
        self.time_datetime = time_datetime

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
