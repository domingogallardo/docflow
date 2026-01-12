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


def test_pick_local_html_info_uses_latest(tmp_path):
    import sync_public_highlights as sph

    base_dir = tmp_path / "Library"
    (base_dir / "Posts" / "Posts 2024").mkdir(parents=True)
    (base_dir / "Tweets" / "Tweets 2025").mkdir(parents=True)
    (base_dir / "Posts" / "Posts 2024" / "doc.html").write_text("<html></html>", encoding="utf-8")
    (base_dir / "Tweets" / "Tweets 2025" / "doc.html").write_text("<html></html>", encoding="utf-8")

    year_index, fallback_paths, known = sph.build_local_html_index(base_dir)
    year, path, has_local = sph.pick_local_html_info(
        "doc.html",
        year_index=year_index,
        fallback_paths=fallback_paths,
        known_names=known,
        default_year=2023,
    )

    assert has_local is True
    assert year == 2025
    assert path is not None


def test_sync_public_highlights_writes_state_and_json(tmp_path):
    import sync_public_highlights as sph

    base_dir = tmp_path / "Library"
    local_dir = base_dir / "Tweets" / "Tweets 2025"
    local_dir.mkdir(parents=True)
    (local_dir / "Foo Bar.html").write_text("<html></html>", encoding="utf-8")
    (local_dir / "Foo Bar.md").write_text("Intro Highlight one fin\n", encoding="utf-8")

    remote_name = "Foo%20Bar.html.json"
    payload = {
        "version": 1,
        "updated_at": "2025-01-01T10:00:00Z",
        "highlights": [{"text": "Highlight one", "created_at": "2025-01-01T10:00:00Z"}],
    }
    raw_text = json.dumps(payload)

    def fake_listing(_: str) -> str:
        return f'<a href="{remote_name}">{remote_name}</a>'

    def fake_json(_: str) -> tuple[str, dict, str | None]:
        return raw_text, payload, '"etag-1"'

    def fake_head(_: str) -> tuple[str | None, str | None]:
        return "etag-1", "Wed, 01 Jan 2025 10:00:00 GMT"

    summary = sph.sync_public_highlights(
        base_url="https://example.com",
        highlights_path="/data/highlights/",
        base_dir=base_dir,
        default_year=2024,
        listing_fetcher=fake_listing,
        json_fetcher=fake_json,
        html_head_fetcher=fake_head,
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
    md_text = (local_dir / "Foo Bar.md").read_text(encoding="utf-8")
    assert "Highlight one" in md_text
    assert "<!-- docflow:highlight" in md_text
    assert summary.md_updated == 1


def test_sync_updates_markdown_when_html_changes(tmp_path):
    import sync_public_highlights as sph

    base_dir = tmp_path / "Library"
    local_dir = base_dir / "Posts" / "Posts 2024"
    local_dir.mkdir(parents=True)
    html_path = local_dir / "Doc.html"
    html_path.write_text("<html></html>", encoding="utf-8")
    md_path = local_dir / "Doc.md"
    md_path.write_text(
        "Texto <!-- docflow:highlight id=h_old -->viejo<!-- /docflow:highlight --> Nuevo\n",
        encoding="utf-8",
    )

    remote_name = "Doc.html.json"
    payload = {
        "version": 1,
        "updated_at": "2025-01-01T10:00:00Z",
        "highlights": [{"text": "Nuevo", "created_at": "2025-01-02T12:00:00Z"}],
    }
    raw_text = json.dumps(payload)

    highlights_dir = base_dir / "Posts" / "Posts 2024" / "highlights"
    highlights_dir.mkdir(parents=True, exist_ok=True)
    (highlights_dir / remote_name).write_text(raw_text + "\n", encoding="utf-8")
    state_path = highlights_dir / "sync_state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "year": 2024,
                "source": {"base_url": "https://example.com", "highlights_path": "/data/highlights/"},
                "last_run_at": "2025-01-01T11:00:00Z",
                "files": {
                    remote_name: {
                        "remote_updated_at": payload["updated_at"],
                        "html_etag": "etag-old",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    def fake_listing(_: str) -> str:
        return f'<a href="{remote_name}">{remote_name}</a>'

    def fake_json(_: str) -> tuple[str, dict, str | None]:
        return raw_text, payload, '"etag-1"'

    def fake_head(_: str) -> tuple[str | None, str | None]:
        return "etag-new", "Wed, 02 Jan 2025 12:00:00 GMT"

    summary = sph.sync_public_highlights(
        base_url="https://example.com",
        highlights_path="/data/highlights/",
        base_dir=base_dir,
        default_year=2024,
        listing_fetcher=fake_listing,
        json_fetcher=fake_json,
        html_head_fetcher=fake_head,
    )

    updated = md_path.read_text(encoding="utf-8")
    assert "Nuevo" in updated
    assert "<!-- docflow:highlight" in updated
    assert summary.md_updated == 1


def test_sync_updates_markdown_when_markers_missing(tmp_path):
    import sync_public_highlights as sph

    base_dir = tmp_path / "Library"
    local_dir = base_dir / "Posts" / "Posts 2024"
    local_dir.mkdir(parents=True)
    html_path = local_dir / "Doc.html"
    html_path.write_text("<html></html>", encoding="utf-8")
    md_path = local_dir / "Doc.md"
    md_path.write_text("Texto Nuevo\n", encoding="utf-8")

    remote_name = "Doc.html.json"
    payload = {
        "version": 1,
        "updated_at": "2025-01-01T10:00:00Z",
        "highlights": [{"text": "Nuevo"}],
    }
    raw_text = json.dumps(payload)

    highlights_dir = base_dir / "Posts" / "Posts 2024" / "highlights"
    highlights_dir.mkdir(parents=True, exist_ok=True)
    (highlights_dir / remote_name).write_text(raw_text + "\n", encoding="utf-8")
    state_path = highlights_dir / "sync_state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "year": 2024,
                "source": {"base_url": "https://example.com", "highlights_path": "/data/highlights/"},
                "last_run_at": "2025-01-01T11:00:00Z",
                "files": {
                    remote_name: {
                        "remote_updated_at": payload["updated_at"],
                        "html_etag": "etag-1",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    def fake_listing(_: str) -> str:
        return f'<a href="{remote_name}">{remote_name}</a>'

    def fake_json(_: str) -> tuple[str, dict, str | None]:
        return raw_text, payload, '"etag-1"'

    def fake_head(_: str) -> tuple[str | None, str | None]:
        return "etag-1", None

    summary = sph.sync_public_highlights(
        base_url="https://example.com",
        highlights_path="/data/highlights/",
        base_dir=base_dir,
        default_year=2024,
        listing_fetcher=fake_listing,
        json_fetcher=fake_json,
        html_head_fetcher=fake_head,
    )

    updated = md_path.read_text(encoding="utf-8")
    assert "<!-- docflow:highlight" in updated
    assert summary.md_updated == 1


def test_sync_updates_markdown_when_marker_ids_missing(tmp_path):
    import sync_public_highlights as sph

    base_dir = tmp_path / "Library"
    local_dir = base_dir / "Posts" / "Posts 2024"
    local_dir.mkdir(parents=True)
    html_path = local_dir / "Doc.html"
    html_path.write_text("<html></html>", encoding="utf-8")
    md_path = local_dir / "Doc.md"
    md_path.write_text(
        "<!-- docflow:highlight id=h1 -->Alpha<!-- /docflow:highlight --> Beta\n",
        encoding="utf-8",
    )

    remote_name = "Doc.html.json"
    payload = {
        "version": 1,
        "updated_at": "2025-01-01T10:00:00Z",
        "highlights": [
            {"id": "h1", "text": "Alpha"},
            {"id": "h2", "text": "Alpha Beta"},
        ],
    }
    raw_text = json.dumps(payload)

    highlights_dir = base_dir / "Posts" / "Posts 2024" / "highlights"
    highlights_dir.mkdir(parents=True, exist_ok=True)
    (highlights_dir / remote_name).write_text(raw_text + "\n", encoding="utf-8")
    state_path = highlights_dir / "sync_state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "year": 2024,
                "source": {"base_url": "https://example.com", "highlights_path": "/data/highlights/"},
                "last_run_at": "2025-01-01T11:00:00Z",
                "files": {
                    remote_name: {
                        "remote_updated_at": payload["updated_at"],
                        "html_etag": "etag-1",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    def fake_listing(_: str) -> str:
        return f'<a href="{remote_name}">{remote_name}</a>'

    def fake_json(_: str) -> tuple[str, dict, str | None]:
        return raw_text, payload, '"etag-1"'

    def fake_head(_: str) -> tuple[str | None, str | None]:
        return "etag-1", None

    summary = sph.sync_public_highlights(
        base_url="https://example.com",
        highlights_path="/data/highlights/",
        base_dir=base_dir,
        default_year=2024,
        listing_fetcher=fake_listing,
        json_fetcher=fake_json,
        html_head_fetcher=fake_head,
    )

    updated = md_path.read_text(encoding="utf-8")
    assert "ids=h1,h2" in updated
    assert updated.count("<!-- docflow:highlight") == 1
    assert summary.md_updated == 1


def test_apply_highlight_markers_handles_links():
    import sync_public_highlights as sph

    md_text = (
        "Intro\n\n"
        "They're trying to drum up outrage [because a Waymo killed a cat](https://example.com), "
        "a one-of-a-kind mascot.\n"
    )
    highlights = [
        {
            "id": "h1",
            "text": "They're trying to drum up outrage because a Waymo killed a cat, a one-of-a-kind mascot.",
        }
    ]

    updated = sph.apply_highlight_markers(md_text, highlights)
    expected = (
        "<!-- docflow:highlight id=h1 -->"
        "They're trying to drum up outrage [because a Waymo killed a cat](https://example.com), "
        "a one-of-a-kind mascot."
        "<!-- /docflow:highlight -->"
    )
    assert expected in updated


def test_apply_highlight_markers_consolidates_overlaps():
    import sync_public_highlights as sph

    md_text = "Bravo Charlie\n"
    highlights = [
        {"id": "h2", "text": "Bravo Charlie"},
        {"id": "h1", "text": "Bravo"},
    ]

    updated = sph.apply_highlight_markers(md_text, highlights)
    assert updated.count("<!-- docflow:highlight") == 1
    assert "ids=h2,h1" in updated or "ids=h1,h2" in updated


def test_extract_marker_ids_parses_ids_list():
    import sync_public_highlights as sph

    md_text = (
        "<!-- docflow:highlight ids=h1,h2 id=h2 -->Alpha<!-- /docflow:highlight -->\n"
        "<!-- docflow:highlight id=h3 -->Beta<!-- /docflow:highlight -->\n"
    )
    assert sph.extract_marker_ids(md_text) == {"h1", "h2", "h3"}
