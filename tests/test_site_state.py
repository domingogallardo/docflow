from pathlib import Path

from utils import site_state


def test_publish_unpublish_roundtrip(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()

    changed = site_state.publish_path(base, "Posts/Posts 2026/doc.html")
    assert changed is True
    assert site_state.is_published(base, "Posts/Posts 2026/doc.html") is True

    changed_again = site_state.publish_path(base, "Posts/Posts 2026/doc.html")
    assert changed_again is False

    removed = site_state.unpublish_path(base, "Posts/Posts 2026/doc.html")
    assert removed is True
    assert site_state.is_published(base, "Posts/Posts 2026/doc.html") is False


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
