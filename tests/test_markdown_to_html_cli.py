"""Tests para el comando standalone de conversión Markdown → HTML."""
from pathlib import Path

import pytest

pytest.importorskip("markdown")
pytest.importorskip("bs4")
pytest.importorskip("openai")

from utils.standalone_markdown_to_html import main


def _disable_ai(monkeypatch):
    monkeypatch.setattr(
        "utils.standalone_markdown_to_html.build_openai_client",
        lambda *_args, **_kwargs: None,
    )


def test_cli_converts_markdown_and_applies_repo_style(tmp_path, monkeypatch):
    _disable_ai(monkeypatch)
    markdown_dir = tmp_path / "notas"
    markdown_dir.mkdir()
    md_file = markdown_dir / "demo.md"
    md_file.write_text("Linea uno\n\nVisita https://example.com", encoding="utf-8")

    output_dir = tmp_path / "salida"
    exit_code = main(["--output-dir", str(output_dir), str(md_file)])

    assert exit_code == 0
    html_file = output_dir / "demo.html"
    html_content = html_file.read_text(encoding="utf-8")

    assert "body { margin-left: 6%; margin-right: 6%; }" in html_content
    assert '<a href="https://example.com">https://example.com</a>' in html_content
    assert "<p>Linea uno</p>" in html_content


def test_cli_respects_existing_html_unless_forced(tmp_path, monkeypatch):
    _disable_ai(monkeypatch)
    md_file = tmp_path / "nota.md"
    md_file.write_text("contenido", encoding="utf-8")
    html_file = tmp_path / "nota.html"
    html_file.write_text("previo", encoding="utf-8")

    main([str(md_file)])
    assert html_file.read_text(encoding="utf-8") == "previo"

    main(["--force", str(md_file)])
    updated = html_file.read_text(encoding="utf-8")
    assert "previo" not in updated
    assert "contenido" in updated


def test_cli_updates_margins_on_existing_html(tmp_path, monkeypatch):
    _disable_ai(monkeypatch)
    md_file = tmp_path / "nota.md"
    md_file.write_text("contenido", encoding="utf-8")
    html_file = tmp_path / "nota.html"
    html_file.write_text("<html><body>previo</body></html>", encoding="utf-8")

    main([str(md_file)])

    html_content = html_file.read_text(encoding="utf-8")
    assert "body { margin-left: 6%; margin-right: 6%; }" not in html_content
    assert html_content == "<html><body>previo</body></html>"
