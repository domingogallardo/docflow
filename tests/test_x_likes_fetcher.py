#!/usr/bin/env python3
from utils import x_likes_fetcher as xl


class FakeLink:
    def __init__(self, href: str):
        self.href = href

    def get_attribute(self, name: str):
        if name == "href":
            return self.href
        return None


class FakeArticle:
    def __init__(self, hrefs):
        self.hrefs = hrefs

    def query_selector_all(self, _selector):
        return [FakeLink(href) for href in self.hrefs]


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
