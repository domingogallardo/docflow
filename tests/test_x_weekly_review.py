import json
from datetime import datetime

import pytest

from utils import x_weekly_review as weekly


@pytest.fixture(autouse=True)
def no_real_delays(monkeypatch):
    monkeypatch.setattr(weekly, "_pause", lambda seconds: None)


def _test_corpus():
    return [
        {"handle": f"@user{index:02d}", "weight": 100 if index < 5 else 60}
        for index in range(weekly.SELECTION_SIZE)
    ]


def _write_test_corpus(base_dir):
    path = base_dir / "state" / "x_weekly" / weekly.CORPUS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_test_corpus()), encoding="utf-8")
    return path


def test_load_corpus_validates_size_weights_and_unique_handles(tmp_path):
    corpus = weekly.load_corpus(_write_test_corpus(tmp_path))

    assert len(corpus) == weekly.SELECTION_SIZE
    assert len({handle for handle, _ in corpus}) == weekly.SELECTION_SIZE
    assert corpus[0] == ("user00", 100)
    assert corpus[-1] == ("user49", 60)


def test_week_bounds_are_madrid_calendar_week():
    start, end, week_id = weekly._week_bounds("2026-08-03")

    assert start == datetime(2026, 8, 3, tzinfo=weekly.MADRID)
    assert end == datetime(2026, 8, 10, tzinfo=weekly.MADRID)
    assert week_id == "2026-W32"


def test_week_bounds_for_scheduled_august_17_run():
    start, end, week_id = weekly._week_bounds("2026-08-10")

    assert start == datetime(2026, 8, 10, tzinfo=weekly.MADRID)
    assert end == datetime(2026, 8, 17, tzinfo=weekly.MADRID)
    assert week_id == "2026-W33"


def test_weighted_review_pool_is_deterministic_and_keeps_all_weight_100_candidates():
    payload = {
        "week": "2026-W33",
        "candidates": [
            {"id": str(index), "weight": 100 if index < 10 else 55}
            for index in range(100)
        ],
    }

    first_count = weekly._prepare_review_pool(payload)
    first_flags = [candidate["sampled_for_review"] for candidate in payload["candidates"]]
    second_count = weekly._prepare_review_pool(payload)

    assert first_count == second_count
    assert first_count >= weekly.SELECTION_SIZE
    assert all(first_flags[:10])
    assert first_flags == [candidate["sampled_for_review"] for candidate in payload["candidates"]]


def test_write_state_is_atomic_and_leaves_no_temporary_file(tmp_path):
    state_path = tmp_path / "week.json"

    weekly._write_state(state_path, {"week": "2026-W33"})

    assert json.loads(state_path.read_text(encoding="utf-8")) == {"week": "2026-W33"}
    assert list(tmp_path.glob(".*.tmp")) == []


def test_merge_candidates_preserves_editorial_and_like_state():
    existing = [{
        "id": "1",
        "text": "old",
        "selected": True,
        "rank": 1,
        "summary": "Summary",
        "topic": "Topic",
        "like_status": "liked",
    }]

    merged = weekly._merge_candidates(
        existing,
        [{"id": "1", "text": "new", "selected": False, "like_status": "pending"}],
    )

    assert merged[0]["text"] == "new"
    assert merged[0]["selected"] is True
    assert merged[0]["like_status"] == "liked"


def test_apply_selection_marks_exactly_50_ranked_candidates(tmp_path):
    state_path = tmp_path / "state.json"
    selection_path = tmp_path / "selection.json"
    candidates = [
        {"id": str(index), "selected": False, "summary": "old", "topic": "old"}
        for index in range(51)
    ]
    state_path.write_text(json.dumps({"candidates": candidates}), encoding="utf-8")
    selection_path.write_text(
        json.dumps(
            [
                {"id": str(index), "summary": f"Summary {index}", "topic": "Topic"}
                for index in range(50)
            ]
        ),
        encoding="utf-8",
    )

    weekly.apply_selection(state_path, selection_path)

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    selected = [candidate for candidate in payload["candidates"] if candidate["selected"]]
    assert len(selected) == 50
    assert [candidate["rank"] for candidate in selected] == list(range(1, 51))
    assert payload["candidates"][50] == {"id": "50", "selected": False}


def test_apply_selection_rejects_candidates_outside_ready_review_pool(tmp_path):
    state_path = tmp_path / "state.json"
    selection_path = tmp_path / "selection.json"
    candidates = [
        {"id": str(index), "selected": False, "sampled_for_review": index != 49}
        for index in range(50)
    ]
    state_path.write_text(
        json.dumps({"candidates": candidates, "review_pool_ready": True}),
        encoding="utf-8",
    )
    selection_path.write_text(
        json.dumps([
            {"id": str(index), "summary": "Summary", "topic": "Topic"}
            for index in range(50)
        ]),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="outside the weighted review pool"):
        weekly.apply_selection(state_path, selection_path)


def test_apply_selection_cannot_change_after_a_like_is_confirmed(tmp_path):
    state_path = tmp_path / "state.json"
    selection_path = tmp_path / "selection.json"
    candidates = [
        {
            "id": str(index),
            "selected": index < 50,
            "like_status": "liked" if index == 0 else "pending",
        }
        for index in range(51)
    ]
    state_path.write_text(json.dumps({"candidates": candidates}), encoding="utf-8")
    selection_path.write_text(
        json.dumps([
            {"id": str(index), "summary": "Summary", "topic": "Topic"}
            for index in range(1, 51)
        ]),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Cannot change the selection"):
        weekly.apply_selection(state_path, selection_path)


class _FakePlaywrightContext:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, traceback):
        return False


class _FakePage:
    def wait_for_timeout(self, milliseconds):
        return None


class _FakeBrowserContext:
    def add_init_script(self, script):
        return None

    def new_page(self):
        return _FakePage()

    def close(self):
        return None


class _FakeBrowser:
    def new_context(self, **kwargs):
        return _FakeBrowserContext()

    def close(self):
        return None


class _FakeChromium:
    def __init__(self):
        self.launch_count = 0

    def launch(self, **kwargs):
        self.launch_count += 1
        return _FakeBrowser()


class _FakeCollectionPlaywright:
    def __init__(self):
        self.chromium = _FakeChromium()


class _FakeCollectionContext:
    def __init__(self, playwright):
        self.playwright = playwright

    def __enter__(self):
        return self.playwright

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_collect_week_retries_a_profile_and_prepares_weighted_pool(
    tmp_path, monkeypatch
):
    browser_state = tmp_path / "x-state.json"
    browser_state.write_text("{}", encoding="utf-8")
    fake_playwright = _FakeCollectionPlaywright()
    attempts = {}
    corpus = tuple(
        (item["handle"].lstrip("@"), item["weight"])
        for item in _test_corpus()
    )
    index_by_handle = {
        f"@{handle}": index for index, (handle, _) in enumerate(corpus, 1)
    }

    def fake_collect(page, url, *, expected_author_handle, **kwargs):
        attempts[expected_author_handle] = attempts.get(expected_author_handle, 0) + 1
        if expected_author_handle == "@user25" and attempts[expected_author_handle] == 1:
            return False, 0, [], False, None
        tweet_id = str(3000000000000000000 + index_by_handle[expected_author_handle])
        item = weekly.TimelineTweet(
            url=f"https://x.com/{expected_author_handle.lstrip('@')}/status/{tweet_id}",
            author_handle=expected_author_handle,
            author_name=expected_author_handle.lstrip("@"),
            time_datetime="2026-08-12T12:00:00.000Z",
            text="A useful weekly tweet",
        )
        return True, 1, [item], False, None

    monkeypatch.setattr(weekly.cfg, "BASE_DIR", tmp_path)
    monkeypatch.setattr(weekly.cfg, "TWEET_LIKES_STATE", browser_state)
    _write_test_corpus(tmp_path)
    monkeypatch.setattr(
        weekly, "sync_playwright", lambda: _FakeCollectionContext(fake_playwright)
    )
    monkeypatch.setattr(weekly, "collect_timeline_items_from_page", fake_collect)

    state_path = weekly.collect_week("2026-08-10")

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["collection"]["status"] == "complete"
    assert payload["review_pool_ready"] is True
    assert len(payload["completed_handles"]) == len(corpus)
    assert len(payload["candidates"]) == len(corpus)
    assert payload["errors"] == []
    assert attempts["@user25"] == 2
    assert fake_playwright.chromium.launch_count == len(corpus) + 1


def test_apply_likes_retries_uncertain_clicks_and_confirms_all(
    tmp_path, monkeypatch
):
    state_path = tmp_path / "state.json"
    browser_state = tmp_path / "x-state.json"
    browser_state.write_text("{}", encoding="utf-8")
    candidates = [
        {
            "id": str(index),
            "url": f"https://x.com/user/status/{index}",
            "selected": True,
            "rank": index + 1,
            "like_status": "pending",
        }
        for index in range(weekly.SELECTION_SIZE)
    ]
    state_path.write_text(json.dumps({"candidates": candidates}), encoding="utf-8")
    calls = {}
    order = []

    def fake_like_attempt(session, candidate):
        order.append(candidate["rank"])
        calls[candidate["id"]] = calls.get(candidate["id"], 0) + 1
        if calls[candidate["id"]] == 1:
            raise RuntimeError("confirmation timeout")
        return "already_liked"

    monkeypatch.setattr(weekly, "sync_playwright", _FakePlaywrightContext)
    monkeypatch.setattr(weekly, "_perform_like_attempt", fake_like_attempt)
    monkeypatch.setattr(weekly.cfg, "TWEET_LIKES_STATE", browser_state)

    weekly.apply_likes(state_path)

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["application"]["status"] == "complete"
    assert payload["application"]["confirmed_count"] == weekly.SELECTION_SIZE
    assert all(candidate["like_attempts"] == 2 for candidate in payload["candidates"])
    assert all(candidate["like_status"] == "already_liked" for candidate in payload["candidates"])
    assert order[:2] == [50, 50]


def test_resolve_like_target_uses_last_tweet_in_thread(monkeypatch):
    candidate = {
        "id": "100",
        "url": "https://x.com/author/status/100",
        "author_handle": "@author",
    }
    monkeypatch.setattr(
        weekly,
        "_last_self_thread_status_id",
        lambda payload, status_id, author_handle: "102",
    )

    target_id, target_url = weekly._resolve_like_target(candidate, {"thread": True})

    assert target_id == "102"
    assert target_url == "https://x.com/author/status/102"


def test_apply_likes_stops_after_repeated_failures(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    browser_state = tmp_path / "x-state.json"
    browser_state.write_text("{}", encoding="utf-8")
    candidates = [
        {
            "id": str(index),
            "url": f"https://x.com/user/status/{index}",
            "selected": True,
            "rank": index + 1,
            "like_status": "pending",
        }
        for index in range(weekly.SELECTION_SIZE)
    ]
    state_path.write_text(json.dumps({"candidates": candidates}), encoding="utf-8")
    calls = []

    def always_fail(session, candidate):
        calls.append(candidate["id"])
        raise RuntimeError("login wall")

    monkeypatch.setattr(weekly, "sync_playwright", _FakePlaywrightContext)
    monkeypatch.setattr(weekly, "_perform_like_attempt", always_fail)
    monkeypatch.setattr(weekly.cfg, "TWEET_LIKES_STATE", browser_state)

    with pytest.raises(RuntimeError, match="remain without a confirmed Like"):
        weekly.apply_likes(state_path)

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["application"]["status"] == "failed"
    assert "Authentication" in payload["application"]["failure_reason"]
    assert len(calls) == 1


def _application_state(tmp_path, monkeypatch):
    state = tmp_path / 'session.json'
    state.write_text('{}')
    monkeypatch.setattr(weekly.cfg, 'TWEET_LIKES_STATE', state)
    monkeypatch.setattr(weekly, 'sync_playwright', _FakePlaywrightContext)
    path = tmp_path / 'week.json'
    candidates = [dict(id=str(i), url=f'https://x.com/user/status/{i}',
                       selected=True, rank=i + 1, like_status='already_liked')
                  for i in range(50)]
    candidates[-1]['like_status'] = 'pending'
    path.write_text(json.dumps({'candidates': candidates}))
    return path


def test_automatic_recovery_waits_and_skips_confirmed_likes(tmp_path, monkeypatch):
    path = _application_state(tmp_path, monkeypatch)
    calls, pauses = [], []

    def attempt(session, candidate):
        calls.append(candidate['id'])
        if len(calls) <= 2:
            candidate['like_click_uncertain'] = True
            raise RuntimeError('confirmation timeout')
        return 'already_liked'

    monkeypatch.setattr(weekly, '_perform_like_attempt', attempt)
    monkeypatch.setattr(weekly, '_pause', pauses.append)
    weekly.apply_likes(path)
    payload = json.loads(path.read_text())
    assert calls == ['49'] * 3
    assert pauses == [30, 180, 12]
    assert payload['application']['confirmed_count'] == 50
    assert 'retry_not_before' not in payload['application']
    assert 'like_click_uncertain' not in payload['candidates'][-1]


def test_rate_limit_cools_down_without_immediate_retry(tmp_path, monkeypatch):
    path = _application_state(tmp_path, monkeypatch)
    calls, pauses = [], []

    def attempt(session, candidate):
        calls.append(candidate['id'])
        if len(calls) == 1:
            raise weekly.LikeAttemptError('rate_limit', 'HTTP 429')
        return 'liked'

    monkeypatch.setattr(weekly, '_perform_like_attempt', attempt)
    monkeypatch.setattr(weekly, '_pause', pauses.append)
    weekly.apply_likes(path)
    assert calls == ['49', '49']
    assert pauses == [180, 12]


def test_recovery_exhaustion_is_bounded_and_persists_cooldown(tmp_path, monkeypatch):
    path = _application_state(tmp_path, monkeypatch)
    calls = []

    def attempt(session, candidate):
        calls.append(candidate['id'])
        raise RuntimeError('article timeout')

    monkeypatch.setattr(weekly, '_perform_like_attempt', attempt)
    with pytest.raises(RuntimeError, match='1 selected tweets remain'):
        weekly.apply_likes(path)
    payload = json.loads(path.read_text())
    assert calls == ['49'] * 4
    assert payload['application']['status'] == 'failed'
    assert payload['application']['confirmed_count'] == 49
    assert payload['application']['retry_not_before']
    # A separate invocation must also respect the saved deadline.
    pauses = []
    monkeypatch.setattr(weekly, '_pause', pauses.append)
    monkeypatch.setattr(weekly, '_perform_like_attempt', lambda session, candidate: 'already_liked')
    weekly.apply_likes(path)
    assert 0 < pauses[0] <= 180


class _LikeLocator:
    def __init__(self, page, kind):
        self.page, self.kind = page, kind
        self.first = self

    def locator(self, selector):
        return _LikeLocator(self.page, 'unlike' if "'unlike'" in selector else 'like')

    def count(self):
        return int(self.page.challenge if self.kind == 'challenge' else
                   self.page.liked if self.kind == 'unlike' else True)

    def is_visible(self):
        return bool(self.count())

    def wait_for(self, **kwargs):
        if (self.kind == 'article' and self.page.missing) or (
            self.kind == 'unlike' and self.page.fail_confirmation
        ):
            raise RuntimeError('Timeout waiting for exact target')

    def click(self):
        self.page.clicks += 1
        self.page.liked = True


class _LikePage:
    def __init__(self, *, missing=False, fail_confirmation=False, challenge=False):
        self.missing, self.fail_confirmation = missing, fail_confirmation
        self.challenge = challenge
        self.liked, self.clicks = False, 0
        self.url = 'https://x.com/user/status/100'
        self.selectors, self.handlers = [], []
        self.closed = False

    def on(self, event, callback):
        self.handlers.append(callback)

    def goto(self, url, **kwargs):
        self.url = url

    def locator(self, selector):
        self.selectors.append(selector)
        if selector.startswith('article:has'):
            assert selector == "article:has(a[href$='/status/100'] time)"
            return _LikeLocator(self, 'article')
        assert selector.startswith('iframe')
        return _LikeLocator(self, 'challenge')

    def screenshot(self, *, path, **kwargs):
        from pathlib import Path
        Path(path).write_bytes(b'fake screenshot')

    def close(self):
        self.closed = True


def _like_attempt_setup(tmp_path, monkeypatch, page):
    from types import SimpleNamespace
    monkeypatch.setattr(weekly, '_dismiss_cookie_prompt', lambda page: None)
    monkeypatch.setattr(weekly, '_attach_tweet_detail_listener', lambda page: {'payload': None})
    session = SimpleNamespace(new_page=lambda: page, state_path=tmp_path / 'week.json')
    candidate = dict(id='100', url=page.url, like_target_id='100', like_target_url=page.url)
    return session, candidate


def test_missing_exact_tweet_never_clicks_another_article(tmp_path, monkeypatch):
    page = _LikePage(missing=True)
    session, candidate = _like_attempt_setup(tmp_path, monkeypatch, page)
    with pytest.raises(RuntimeError, match='exact target'):
        weekly._perform_like_attempt(session, candidate)
    assert page.clicks == 0 and page.closed
    assert 'article' not in page.selectors
    assert candidate['like_diagnostic']['phase'] == 'exact_tweet'
    assert (tmp_path / 'week-diagnostics/100-0.png').exists()


def test_uncertain_click_is_checked_before_any_second_click(tmp_path, monkeypatch):
    page = _LikePage(fail_confirmation=True)
    session, candidate = _like_attempt_setup(tmp_path, monkeypatch, page)
    with pytest.raises(RuntimeError, match='exact target'):
        weekly._perform_like_attempt(session, candidate)
    assert candidate['like_click_uncertain'] is True
    page.fail_confirmation = False
    assert weekly._perform_like_attempt(session, candidate) == 'already_liked'
    assert page.clicks == 1


def test_unresolved_thread_detail_never_marks_the_anchor(tmp_path, monkeypatch):
    page = _LikePage()
    session, candidate = _like_attempt_setup(tmp_path, monkeypatch, page)
    candidate.pop('like_target_id')
    monkeypatch.setattr(weekly, '_wait_for_tweet_detail', lambda page, timeout: {'errors': []})
    with pytest.raises(weekly.LikeAttemptError, match='thread target not resolved'):
        weekly._perform_like_attempt(session, candidate)
    assert page.clicks == 0


@pytest.mark.parametrize('status,kind', [(401, 'authentication'), (403, 'authentication'),
                                         (429, 'rate_limit'), (503, 'server')])
def test_http_failures_are_classified(tmp_path, monkeypatch, status, kind):
    from types import SimpleNamespace
    page = _LikePage()
    session, candidate = _like_attempt_setup(tmp_path, monkeypatch, page)
    def navigate(url, **kwargs):
        response = SimpleNamespace(url='https://x.com/i/api/graphql/key/TweetDetail?secret=hidden',
                                   status=status, request=SimpleNamespace(resource_type='xhr'))
        for handler in page.handlers:
            handler(response)
    page.goto = navigate
    with pytest.raises(weekly.LikeAttemptError) as error:
        weekly._perform_like_attempt(session, candidate)
    assert error.value.kind == kind
    assert page.clicks == 0
    assert candidate['like_diagnostic']['http_errors'] == [
        {'path': '/i/api/graphql/key/TweetDetail', 'status': status}]
    assert 'secret' not in json.dumps(candidate['like_diagnostic'])


def test_captcha_stops_before_clicking(tmp_path, monkeypatch):
    page = _LikePage(challenge=True)
    session, candidate = _like_attempt_setup(tmp_path, monkeypatch, page)
    with pytest.raises(weekly.LikeAttemptError) as error:
        weekly._perform_like_attempt(session, candidate)
    assert error.value.kind == 'authentication'
    assert page.clicks == 0


def test_like_session_reuses_browser_context_between_pages(tmp_path):
    playwright = _FakeCollectionPlaywright()
    session = weekly._LikeSession(playwright, tmp_path / 'session.json', tmp_path / 'week.json')
    first = session.new_page()
    second = session.new_page()
    assert first is not second
    assert playwright.chromium.launch_count == 1
    session.close()


def test_consecutive_transient_failures_stop_each_pass(tmp_path, monkeypatch):
    path = _application_state(tmp_path, monkeypatch)
    payload = json.loads(path.read_text())
    for candidate in payload['candidates'][-5:]:
        candidate['like_status'] = 'pending'
    path.write_text(json.dumps(payload))
    calls = []

    def fail(session, candidate):
        calls.append(candidate['id'])
        raise RuntimeError('article timeout')

    monkeypatch.setattr(weekly, '_perform_like_attempt', fail)
    with pytest.raises(RuntimeError, match='5 selected tweets remain'):
        weekly.apply_likes(path)
    assert calls == ['49', '49', '48', '48', '47', '47'] * 2
    payload = json.loads(path.read_text())
    assert payload['candidates'][-4]['like_status'] == 'pending'
    assert payload['candidates'][-5]['like_status'] == 'pending'
    assert payload['application']['confirmed_count'] == 45


def test_uncertain_status_survives_failed_run(tmp_path, monkeypatch):
    path = _application_state(tmp_path, monkeypatch)

    def fail(session, candidate):
        candidate['like_click_uncertain'] = True
        raise RuntimeError('confirmation timeout')

    monkeypatch.setattr(weekly, '_perform_like_attempt', fail)
    with pytest.raises(RuntimeError, match='1 selected tweets remain'):
        weekly.apply_likes(path, recovery_rounds=0)
    payload = json.loads(path.read_text())
    assert payload['candidates'][-1]['like_status'] == 'uncertain'
    assert weekly.status_payload(path)['unresolved_count'] == 1


def test_valid_thread_detail_resolves_before_clicking(tmp_path, monkeypatch):
    page = _LikePage()
    session, candidate = _like_attempt_setup(tmp_path, monkeypatch, page)
    candidate.pop('like_target_id')
    tweet = {'__typename': 'Tweet', 'rest_id': '100'}
    monkeypatch.setattr(weekly, '_wait_for_tweet_detail', lambda page, timeout: {'result': tweet})
    assert weekly._perform_like_attempt(session, candidate) == 'liked'
    assert candidate['like_target_id'] == '100'
    assert page.clicks == 1
