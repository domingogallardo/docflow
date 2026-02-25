from pathlib import Path
import json

from utils import site_state


def test_done_roundtrip(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()

    changed = site_state.set_done_path(base, "Posts/Posts 2026/doc.html")
    assert changed is True
    assert site_state.is_done(base, "Posts/Posts 2026/doc.html") is True

    changed_again = site_state.set_done_path(base, "Posts/Posts 2026/doc.html")
    assert changed_again is False

    removed = site_state.clear_done_path(base, "Posts/Posts 2026/doc.html")
    assert removed is True
    assert site_state.is_done(base, "Posts/Posts 2026/doc.html") is False


def test_done_entry_keeps_transition_start_timestamps(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    base.mkdir()
    rel = "Posts/Posts 2026/doc.html"
    monkeypatch.setattr(site_state, "_utc_now_iso", lambda: "2026-02-25T09:00:00Z")

    changed = site_state.set_done_path(
        base,
        rel,
        reading_started_at="2026-02-16T21:14:43Z",
        working_started_at="2026-02-18T08:16:36Z",
    )
    assert changed is True

    state = site_state.load_done_state(base)
    entry = state["items"][rel]
    assert entry["done_at"] == "2026-02-25T09:00:00Z"
    assert entry["reading_started_at"] == "2026-02-16T21:14:43Z"
    assert entry["working_started_at"] == "2026-02-18T08:16:36Z"

    changed_again = site_state.set_done_path(
        base,
        rel,
        reading_started_at="2026-01-01T00:00:00Z",
        working_started_at="2026-01-01T00:00:00Z",
    )
    assert changed_again is False

    state_after = site_state.load_done_state(base)
    entry_after = state_after["items"][rel]
    assert entry_after["reading_started_at"] == "2026-02-16T21:14:43Z"
    assert entry_after["working_started_at"] == "2026-02-18T08:16:36Z"


def test_reading_roundtrip(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    rel = "Posts/Posts 2026/doc.html"

    changed = site_state.set_reading_path(base, rel)
    assert changed is True
    assert site_state.is_reading(base, rel) is True

    changed_again = site_state.set_reading_path(base, rel)
    assert changed_again is False

    state = site_state.load_reading_state(base)
    entry = state["items"].get(rel)
    assert entry is not None
    assert isinstance(entry["reading_at"], str)
    assert set(entry.keys()) == {"reading_at"}

    removed = site_state.pop_reading_path(base, rel)
    assert removed is not None
    assert site_state.is_reading(base, rel) is False


def test_working_roundtrip(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    rel = "Posts/Posts 2026/doc.html"

    changed = site_state.set_working_path(base, rel)
    assert changed is True
    assert site_state.is_working(base, rel) is True

    changed_again = site_state.set_working_path(base, rel)
    assert changed_again is False

    removed = site_state.pop_working_path(base, rel)
    assert removed is not None
    assert site_state.is_working(base, rel) is False


def test_load_done_state_migrates_legacy_published_json(tmp_path: Path):
    base = tmp_path / "base"
    state_dir = base / "state"
    state_dir.mkdir(parents=True)
    legacy = state_dir / "published.json"
    payload = {
        "version": 1,
        "items": {
            "Posts/Posts 2026/doc.html": {"done_at": "2026-02-18T10:00:00Z"},
        },
    }
    legacy.write_text(json.dumps(payload), encoding="utf-8")

    loaded = site_state.load_done_state(base)

    assert "Posts/Posts 2026/doc.html" in loaded["items"]
    assert (state_dir / "done.json").exists()
    assert not legacy.exists()
