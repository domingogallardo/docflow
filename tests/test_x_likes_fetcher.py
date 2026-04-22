#!/usr/bin/env python3
from utils import x_likes_fetcher as xl


class FakeLink:
    def __init__(self, href: str):
        self.href = href

    def get_attribute(self, name: str):
        if name == "href":
            return self.href
        return None


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
        time_href: str | None = None,
        time_text: str | None = None,
        time_datetime: str | None = None,
    ):
        self.hrefs = hrefs
        self.spans = spans or []
        self.time_href = time_href
        self.time_text = time_text
        self.time_datetime = time_datetime

    def query_selector_all(self, selector):
        if selector == "a[href*='/status/']":
            return [FakeLink(href) for href in self.hrefs]
        if selector == "span":
            return [FakeSpan(text) for text in self.spans]
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


def test_extract_tweet_urls_collects_multiple_links_per_article():
    articles = [
        FakeArticle(["/user1/status/1"]),
        FakeArticle(
            [
                "/user2/status/2",
                "/user2/status/2",  # duplicated link inside same article
                "https://x.com/user3/status/3",
                "/user4/not-a-status",
            ]
        ),
    ]
    page = FakePage(articles)
    urls = xl._extract_tweet_urls(page, set())
    assert urls == [
        "https://x.com/user1/status/1",
        "https://x.com/user2/status/2",
        "https://x.com/user3/status/3",
    ]


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
