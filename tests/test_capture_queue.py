import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from capture_queue import parse_queue, process_queue
from utils import split_front_matter


def record(raw, note="", added="2026-10-04T23:00:00+02:00"):
    enc = lambda text: base64.b64encode(text.encode()).decode()
    return f"### Capture\n- Added: {added}\n- Input-Base64: {enc(raw)}\n- Note-Base64: {enc(note)}\n"


def setup_queue(tmp_path, raw="https://example.com/article", note=""):
    queue = tmp_path / "cloud/queue.md"
    queue.parent.mkdir()
    queue.write_text(record(raw, note))
    base = tmp_path / "docs"
    return queue, base


def fake_download(url, *, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "clipper-test.md"
    path.write_text(f"---\ndocflow-source-url: {url}\n---\nArticle body\n")
    return SimpleNamespace(output_path=path)


def ingest(base):
    destination = base / "Posts/Posts 2026"
    destination.mkdir(parents=True, exist_ok=True)
    for path in (base / "Incoming").glob("*.md"):
        moved = destination / "Renamed article.md"
        path.rename(moved)
        moved.with_suffix(".html").write_text("<html>Article body</html>")


def test_unread_uses_url_and_preserves_comment_url_and_unicode_note():
    raw = json.dumps({"url": "https://example.com/article", "article_url": "https://news.ycombinator.com/item?id=42", "title": "Título"})
    captures, errors = parse_queue(record(raw, "Para mi boletín\nDos líneas"))
    assert not errors
    assert captures[0].url == "https://example.com/article"
    assert captures[0].metadata["article_url"].endswith("42")
    assert "\n" in captures[0].note


@pytest.mark.parametrize("raw", ["", "hello", "ftp://example.com/file", "https://example.com/a https://example.com/b", '{"url":"javascript:alert(1)"}', '{"url":null}', 'https://user:password@example.com'])
def test_invalid_inputs_stay_unprocessed(raw):
    captures, errors = parse_queue(record(raw))
    assert not captures
    assert errors


def test_truncated_record_does_not_prevent_other_records():
    captures, errors = parse_queue(record("https://example.com/a") + "### Capture\n- Input-Base64: !!!")
    assert len(captures) == 1
    assert errors


def test_dry_run_does_not_write_state_or_download(tmp_path):
    queue, base = setup_queue(tmp_path)
    def unexpected(*args, **kwargs):
        pytest.fail("Dry run attempted a download")
    report = process_queue(queue, base, dry_run=True, downloader=unexpected)
    assert report["pending"] == 1
    assert not base.exists()


def test_successful_capture_is_verified_and_second_run_is_noop(tmp_path):
    queue, base = setup_queue(tmp_path, note="Save this")
    original = queue.read_bytes()
    report = process_queue(queue, base, downloader=fake_download, ingest=lambda: ingest(base))
    assert report["completed"] == 1
    assert queue.read_bytes() == original
    path = base / "Posts/Posts 2026/Renamed article.md"
    meta, _ = split_front_matter(path.read_text())
    assert meta["docflow-capture-note"] == "Save this"
    assert "[x]" in queue.with_name("status.md").read_text()
    def unexpected(*args, **kwargs):
        pytest.fail("Repeated a completed capture")
    assert process_queue(queue, base, downloader=unexpected, ingest=unexpected)["pending"] == 0


def test_failed_download_remains_pending_and_can_be_retried(tmp_path):
    queue, base = setup_queue(tmp_path)
    def fail(*args, **kwargs):
        raise RuntimeError("Login required")
    report = process_queue(queue, base, downloader=fail)
    assert report["failed"] == 1
    assert "Login required" in queue.with_name("status.md").read_text()
    report = process_queue(queue, base, downloader=fake_download, ingest=lambda: ingest(base))
    assert report["completed"] == 1


def test_ingestion_failure_recovers_without_downloading_again(tmp_path):
    queue, base = setup_queue(tmp_path)
    def fail():
        raise RuntimeError("Pipeline interrupted")
    assert process_queue(queue, base, downloader=fake_download, ingest=fail)["failed"] == 1
    def unexpected(*args, **kwargs):
        pytest.fail("Redownloaded the persisted Markdown")
    assert process_queue(queue, base, downloader=unexpected, ingest=lambda: ingest(base))["completed"] == 1


def test_existing_archived_article_is_reused_without_changing_mtime(tmp_path):
    queue, base = setup_queue(tmp_path)
    path = fake_download("https://example.com/article", output_dir=base / "Posts/Posts 2025").output_path
    path.with_suffix(".html").write_text("<html>Saved</html>")
    timestamp = path.stat().st_mtime_ns
    def unexpected(*args, **kwargs):
        pytest.fail("Modified an already archived article")
    assert process_queue(queue, base, downloader=unexpected, ingest=unexpected)["completed"] == 1
    assert path.stat().st_mtime_ns == timestamp


def test_empty_downloader_result_is_not_completed(tmp_path):
    queue, base = setup_queue(tmp_path)
    def bad(url, *, output_dir):
        output_dir.mkdir(parents=True)
        path = output_dir / "empty.md"
        path.touch()
        return SimpleNamespace(output_path=path)
    assert process_queue(queue, base, downloader=bad)["failed"] == 1


def test_capture_appended_during_ingestion_is_preserved_for_next_run(tmp_path):
    queue, base = setup_queue(tmp_path)
    def append_and_ingest():
        with queue.open("a") as stream:
            stream.write(record("https://example.com/later"))
        ingest(base)
    report = process_queue(queue, base, downloader=fake_download, ingest=append_and_ingest)
    assert report["completed"] == 1
    assert process_queue(queue, base, dry_run=True)["pending"] == 1


def test_capture_metadata_survives_real_markdown_ingestion(tmp_path, monkeypatch):
    from markdown_processor import MarkdownProcessor
    import config
    queue, base = setup_queue(tmp_path, note="Capture note")
    monkeypatch.setattr(config, "BASE_DIR", base)
    monkeypatch.setattr("markdown_processor.build_openai_client", lambda *_: None)
    processor = MarkdownProcessor(base / "Incoming", base / "Posts/Posts 2026")
    report = process_queue(queue, base, downloader=fake_download, ingest=processor.process_markdown)
    assert report["completed"] == 1
    receipts = json.loads((base / "state/capture_queue.json").read_text())
    receipt = next(iter(receipts["captures"].values()))
    path = Path(receipt["document"])
    meta, _ = split_front_matter(path.read_text())
    assert meta["docflow-capture-note"] == "Capture note"
    assert meta["docflow-capture-id"] == receipt["id"]
    assert "https://example.com/article" in (base / "Incoming/processed_history.txt").read_text()


def test_safari_uses_extracted_url_when_text_is_a_title():
    text = record("Article title")
    encoded = base64.b64encode(b"https://example.com/article").decode()
    captures, errors = parse_queue(text + f"- URLs-Base64: {encoded}\n")
    assert not errors
    assert captures[0].url == "https://example.com/article"


def test_completed_receipt_with_missing_document_is_retried(tmp_path):
    queue, base = setup_queue(tmp_path)
    process_queue(queue, base, downloader=fake_download, ingest=lambda: ingest(base))
    (base / "Posts/Posts 2026/Renamed article.md").unlink()
    assert process_queue(queue, base, dry_run=True)["pending"] == 1
