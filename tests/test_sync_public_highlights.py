import json
from pathlib import Path


def test_extract_links_from_autoindex():
    import sync_public_highlights as sph

    html = """
    <html><body>
      <a href="../">../</a>
      <a href="doc.json">doc.json</a>
      <a href="nested/skip.json">skip.json</a>
      <a href="read.html">read.html</a>
      <a href="doc.json?x=1">doc.json</a>
    </body></html>
    """
    links = sph.extract_links_from_autoindex(html)
    assert "doc.json" in links
    assert "skip.json" in links
    assert all(link.endswith(".json") for link in links)


def test_pick_year_for_basename_uses_latest(tmp_path):
    import sync_public_highlights as sph

    base_dir = tmp_path / "Library"
    (base_dir / "Posts" / "Posts 2024").mkdir(parents=True)
    (base_dir / "Tweets" / "Tweets 2025").mkdir(parents=True)
    (base_dir / "Posts" / "Posts 2024" / "doc.html").write_text("<html></html>", encoding="utf-8")
    (base_dir / "Tweets" / "Tweets 2025" / "doc.html").write_text("<html></html>", encoding="utf-8")

    year_index, known = sph.build_local_html_index(base_dir)
    year, has_local = sph.pick_year_for_basename(
        "doc.html",
        year_index=year_index,
        known_names=known,
        default_year=2023,
    )

    assert has_local is True
    assert year == 2025


def test_sync_public_highlights_writes_state_and_json(tmp_path):
    import sync_public_highlights as sph

    base_dir = tmp_path / "Library"
    local_dir = base_dir / "Tweets" / "Tweets 2025"
    local_dir.mkdir(parents=True)
    (local_dir / "Foo Bar.html").write_text("<html></html>", encoding="utf-8")

    remote_name = "Foo%20Bar.html.json"
    payload = {
        "version": 1,
        "updated_at": "2025-01-01T10:00:00Z",
        "highlights": [],
    }
    raw_text = json.dumps(payload)

    def fake_listing(_: str) -> str:
        return f'<a href="{remote_name}">{remote_name}</a>'

    def fake_json(_: str) -> tuple[str, dict, str | None]:
        return raw_text, payload, '"etag-1"'

    summary = sph.sync_public_highlights(
        base_url="https://example.com",
        highlights_path="/data/highlights/",
        base_dir=base_dir,
        default_year=2024,
        listing_fetcher=fake_listing,
        json_fetcher=fake_json,
    )

    highlights_dir = base_dir / "Posts" / "Posts 2025" / "highlights"
    stored = highlights_dir / remote_name
    state_path = highlights_dir / "sync_state.json"

    assert summary.downloaded == 1
    assert stored.exists()
    assert json.loads(stored.read_text(encoding="utf-8"))["updated_at"] == payload["updated_at"]

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["year"] == 2025
    assert remote_name in state["files"]
    assert state["files"][remote_name]["remote_updated_at"] == payload["updated_at"]
