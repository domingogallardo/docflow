from pathlib import Path

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


def test_bump_state_keeps_original_mtime(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    rel = "Posts/Posts 2026/doc.html"

    site_state.set_bumped_path(base, rel, original_mtime=100.0, bumped_mtime=1000.0)
    site_state.set_bumped_path(base, rel, original_mtime=200.0, bumped_mtime=2000.0)

    entry = site_state.get_bumped_entry(base, rel)
    assert entry is not None
    assert entry["original_mtime"] == 100.0
    assert entry["bumped_mtime"] == 2000.0

    removed = site_state.pop_bumped_path(base, rel)
    assert removed is not None
    assert site_state.get_bumped_entry(base, rel) is None


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
