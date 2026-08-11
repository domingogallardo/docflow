import json
from datetime import datetime

import pytest

from utils import x_weekly_review as weekly


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

    def fake_like_attempt(playwright, candidate, state):
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

    def always_fail(playwright, candidate, state):
        calls.append(candidate["id"])
        raise RuntimeError("login wall")

    monkeypatch.setattr(weekly, "sync_playwright", _FakePlaywrightContext)
    monkeypatch.setattr(weekly, "_perform_like_attempt", always_fail)
    monkeypatch.setattr(weekly.cfg, "TWEET_LIKES_STATE", browser_state)

    with pytest.raises(RuntimeError, match="remain without a confirmed Like"):
        weekly.apply_likes(state_path)

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["application"]["status"] == "failed"
    assert payload["application"]["failure_reason"].startswith("Stopped after 3")
    assert len(calls) == 6
