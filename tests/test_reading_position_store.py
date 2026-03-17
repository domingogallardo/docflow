from pathlib import Path

from utils import reading_position_store


def test_save_and_load_canonical_reading_position(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    rel = "Posts/Posts 2026/doc.html"

    payload = {
        "title": "Doc",
        "updated_at": "2026-03-17T10:00:00Z",
        "scroll_y": 420,
        "max_scroll": 1200,
        "progress": 0.35,
        "viewport_height": 900,
        "document_height": 2100,
    }

    saved = reading_position_store.save_reading_position_for_path(base, rel, payload)
    assert saved["path"] == rel
    assert saved["scroll_y"] == 420
    assert saved["progress"] == 0.35

    loaded = reading_position_store.load_reading_position_for_path(base, rel)
    assert loaded["path"] == rel
    assert loaded["scroll_y"] == 420
    assert loaded["progress"] == 0.35


def test_top_position_removes_canonical_reading_position_file(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    rel = "Posts/Posts 2026/doc.html"

    reading_position_store.save_reading_position_for_path(
        base,
        rel,
        {"updated_at": "2026-03-17T10:00:00Z", "scroll_y": 300, "max_scroll": 1000, "progress": 0.3},
    )
    path = reading_position_store.reading_position_state_path(base, rel)
    assert path.exists()

    reading_position_store.save_reading_position_for_path(
        base,
        rel,
        {"updated_at": "2026-03-17T10:01:00Z", "scroll_y": 0, "max_scroll": 1000, "progress": 0},
    )
    assert not path.exists()
    assert not path.parent.exists()


def test_clear_reading_position_keeps_hash_dir_when_not_empty(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    rel = "Posts/Posts 2026/doc.html"

    reading_position_store.save_reading_position_for_path(
        base,
        rel,
        {"updated_at": "2026-03-17T10:00:00Z", "scroll_y": 300, "max_scroll": 1000, "progress": 0.3},
    )
    path = reading_position_store.reading_position_state_path(base, rel)
    assert path.exists()

    marker = path.parent / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    assert reading_position_store.clear_reading_position_for_path(base, rel) is True
    assert not path.exists()
    assert path.parent.exists()
    assert marker.exists()


def test_load_missing_reading_position_returns_empty_payload(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    rel = "Posts/Posts 2026/doc.html"

    payload = reading_position_store.load_reading_position_for_path(base, rel)
    assert payload["path"] == rel
    assert payload["scroll_y"] is None
    assert payload["progress"] is None
