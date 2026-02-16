from pathlib import Path

from utils import highlight_store


def test_save_and_load_canonical_highlights(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    rel = "Posts/Posts 2026/doc.html"

    payload = {
        "title": "Doc",
        "highlights": [{"id": "h1", "text": "hello"}],
    }
    saved = highlight_store.save_highlights_for_path(base, rel, payload)
    assert saved["path"] == rel
    assert len(saved["highlights"]) == 1

    loaded = highlight_store.load_highlights_for_path(base, rel)
    assert loaded["path"] == rel
    assert loaded["highlights"][0]["text"] == "hello"
    assert highlight_store.has_highlights_for_path(base, rel) is True


def test_empty_highlights_remove_canonical_file(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    rel = "Posts/Posts 2026/doc.html"

    highlight_store.save_highlights_for_path(base, rel, {"highlights": [{"text": "x"}]})
    path = highlight_store.highlight_state_path(base, rel)
    assert path.exists()

    highlight_store.save_highlights_for_path(base, rel, {"highlights": []})
    assert not path.exists()
    assert highlight_store.has_highlights_for_path(base, rel) is False


def test_load_does_not_use_legacy_posts_highlights(tmp_path: Path):
    base = tmp_path / "base"
    year_dir = base / "Posts" / "Posts 2026"
    year_dir.mkdir(parents=True)
    rel = "Posts/Posts 2026/Doc (Sample).html"

    highlights_dir = year_dir / "highlights"
    highlights_dir.mkdir(parents=True)

    from urllib.parse import quote

    encoded = quote("Doc (Sample).html")
    legacy = highlights_dir / f"{encoded}.json"
    legacy.write_text('{"highlights": [{"id": "h1", "text": "legacy"}]}\n', encoding="utf-8")

    payload = highlight_store.load_highlights_for_path(base, rel)
    assert payload["path"] == rel
    assert payload["highlights"] == []
    assert highlight_store.has_highlights_for_path(base, rel) is False
