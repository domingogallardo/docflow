"""Weekly file membership, retries and reuse of the daily consolidation engine."""
import json
from pathlib import Path

import pytest

from utils import build_daily_tweet_consolidated as daily
from utils import weekly_tweet_consolidation as weekly
from tests.test_build_daily_tweet_consolidated import _write_tweet_pair


def _state(base: Path, candidates: list[dict]) -> Path:
    folder = base / "state/x_weekly"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "2026-W40.json"
    path.write_text(json.dumps({
        "week": "2026-W40", "start": "2026-09-28T00:00:00+02:00",
        "end": "2026-10-05T00:00:00+02:00", "candidates": candidates,
        "application": {"status": "complete"},
    }))
    return path


def _candidate(tweet_id: str, target: str | None = None) -> dict:
    return {"id": tweet_id, "selected": True, "like_status": "liked",
            "like_target_id": target or tweet_id}


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setattr(weekly, "SELECTION_SIZE", 2)
    folder = tmp_path / "Tweets/Tweets 2026"
    folder.mkdir(parents=True)
    return tmp_path, folder


def _tweet(folder, name, tweet_id, **kwargs):
    return _write_tweet_pair(
        folder, f"Tweet - {name}", "2026-10-05", hour=10,
        extra_front_matter=f"tweet_id: {tweet_id}\n" + kwargs.pop("extra_front_matter", ""),
        **kwargs,
    )


def test_pending_retry_reserves_sources_and_excludes_unrelated_same_day(corpus):
    base, folder = corpus
    state = _state(base, [_candidate("1"), _candidate("2", "20")])
    original_state = state.read_bytes()
    first, first_html = _tweet(folder, "selected", "1")
    unrelated, unrelated_html = _tweet(folder, "unrelated", "9", body="Unrelated [quote](https://x.com/a/status/2)")
    mtime = first.stat().st_mtime

    assert not weekly.consolidate_week(state, base)
    assert first_html.exists()
    assert first.stat().st_mtime == mtime
    assert daily._collect_daily_source_markdown(folder, "2026-10-05") == [unrelated]
    assert not (folder / "Tweets semana 2026-W40.html").exists()

    second, _ = _tweet(folder, "thread", "20", body="Thread content and image", extra_front_matter="tweet_thread: true\n")
    assert weekly.consolidate_week(state, base)
    text = (folder / "Tweets semana 2026-W40.md").read_text()
    assert "Thread content and image" in text
    assert "Unrelated" not in text
    assert unrelated_html.exists()
    assert not first_html.exists()
    assert first.exists() and second.exists()
    assert first.stat().st_mtime == mtime
    manifest = json.loads(state.with_name("2026-W40-downloads.json").read_text())
    assert manifest["missing_ids"] == []
    assert set(manifest["selected_files"]) == {"1", "2"}
    assert state.read_bytes() == original_state
    output = folder / "Tweets semana 2026-W40.html"
    output_mtime = output.stat().st_mtime
    assert weekly.consolidate_week(state, base)
    assert output.stat().st_mtime == output_mtime


def test_weekly_articles_stay_in_posts_with_a_link_in_consolidated(corpus):
    base, folder = corpus
    state = _state(base, [_candidate("1"), _candidate("2")])
    _tweet(folder, "regular", "1")
    posts = base / "Posts/Posts 2026"
    posts.mkdir(parents=True)
    article, html = _tweet(posts, "article", "2", body="Full article remains here", extra_front_matter="tweet_content_type: article\n")
    article_mtime = article.stat().st_mtime
    assert weekly.consolidate_week(state, base)
    output = (folder / "Tweets semana 2026-W40.html").read_text()
    assert "Leer artículo en Posts" in output
    assert "/posts/raw/Posts%202026/" in output
    assert "Full article remains here" not in output
    assert article.exists() and html.exists()
    assert article.stat().st_mtime == article_mtime


def test_two_selected_tweets_in_same_captured_thread_use_one_entry(corpus):
    base, folder = corpus
    state = _state(base, [_candidate("1", "20"), _candidate("2", "20")])
    _tweet(folder, "shared thread", "20")
    assert weekly.consolidate_week(state, base)
    output = (folder / "Tweets semana 2026-W40.html").read_text()
    assert output.count('<article ') == 1
    manifest = json.loads(state.with_name("2026-W40-downloads.json").read_text())
    assert len(set(manifest["selected_files"].values())) == 1


def test_duplicate_capture_blocks_consolidation_before_modifying_sources(corpus):
    base, folder = corpus
    state = _state(base, [_candidate("1"), _candidate("2")])
    first, html = _tweet(folder, "first", "1")
    _tweet(folder, "duplicate", "1")
    with pytest.raises(ValueError, match="Multiple downloaded files"):
        weekly.consolidate_week(state, base)
    assert html.exists()
    assert "tweet_weekly_week" not in first.read_text()


def test_prefer_downloaded_full_thread_to_earlier_standalone_capture(corpus):
    base, folder = corpus
    state = _state(base, [_candidate("1", "20"), _candidate("2", "20")])
    earlier, _ = _tweet(folder, "earlier standalone", "1")
    full_thread, _ = _tweet(folder, "full thread", "20")
    assert weekly.consolidate_week(state, base, dry_run=True)
    assert "tweet_weekly_week" not in full_thread.read_text()
    assert not state.with_name("2026-W40-downloads.json").exists()
    assert weekly.consolidate_week(state, base)
    manifest = json.loads(state.with_name("2026-W40-downloads.json").read_text())
    assert set(manifest["selected_files"].values()) == {full_thread.relative_to(base).as_posix()}
    assert "tweet_weekly_week: 2026-W40" in earlier.read_text()
    assert daily._collect_daily_source_markdown(folder, "2026-10-05") == []
