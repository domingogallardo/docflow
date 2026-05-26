from pathlib import Path
from types import SimpleNamespace

from pipeline_manager import DocumentProcessor


def prepare_processor(tmp_path: Path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    processor = DocumentProcessor(tmp_path, 2026)
    return processor, incoming


def test_process_web_urls_downloads_markdown_and_removes_attempted_links(tmp_path, monkeypatch):
    processor, incoming = prepare_processor(tmp_path)
    ok_url = "https://example.com/good"
    bad_url = "https://example.com/bad"
    processor.links_file.write_text(
        "\n".join(
            [
                "# queue",
                ok_url,
                bad_url,
                "",
            ]
        ),
        encoding="utf-8",
    )

    def fake_download(url, *, output_dir):
        if url == bad_url:
            raise RuntimeError("extractor failed")
        output_path = output_dir / "clipper-good.md"
        output_path.write_text("---\nsource: x\n---\nBody\n", encoding="utf-8")
        return SimpleNamespace(output_path=output_path)

    monkeypatch.setattr("pipeline_manager.download_url_to_markdown", fake_download)

    generated = processor.process_web_urls()

    assert generated == [incoming / "clipper-good.md"]
    assert processor.links_file.read_text(encoding="utf-8") == "# queue\n"
    assert ok_url in processor.processed_history.read_text(encoding="utf-8")
    failed_text = processor.links_failed.read_text(encoding="utf-8")
    assert bad_url in failed_text
    assert "extractor failed" in failed_text


def test_process_web_urls_removes_failed_links_from_queue(tmp_path, monkeypatch):
    processor, _ = prepare_processor(tmp_path)
    url = "https://example.com/bad"
    processor.links_file.write_text(f"# queue\n{url}\n", encoding="utf-8")

    def fake_download(url, *, output_dir):
        raise RuntimeError("network failed")

    monkeypatch.setattr("pipeline_manager.download_url_to_markdown", fake_download)

    generated = processor.process_web_urls()

    assert generated == []
    assert processor.links_file.read_text(encoding="utf-8") == "# queue\n"
    assert not processor.processed_history.exists()
    assert "network failed" in processor.links_failed.read_text(encoding="utf-8")


def test_remove_urls_from_links_file_removes_lines_containing_processed_urls(tmp_path):
    links = tmp_path / "links.txt"
    links.write_text(
        "\n".join(
            [
                "# queue",
                "- https://example.com/one).",
                "https://example.com/two",
                "plain note",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    DocumentProcessor._remove_urls_from_links_file(links, ["https://example.com/one"])

    assert links.read_text(encoding="utf-8") == "# queue\nhttps://example.com/two\nplain note\n"
