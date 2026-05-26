from pathlib import Path

from utils import split_front_matter
from utils.backfill_pdf_sidecars import backfill_pdf_sidecars


def test_backfill_pdf_sidecars_creates_missing_sidecars(tmp_path: Path):
    base = tmp_path / "base"
    pdfs = base / "Pdfs" / "Pdfs 2026"
    pdfs.mkdir(parents=True)
    (pdfs / "paper.pdf").write_bytes(b"%PDF-1.4\n")

    result = backfill_pdf_sidecars(base)

    assert result.total_pdfs == 1
    assert result.created == 1
    assert result.updated == 0
    assert result.unchanged == 0

    md = pdfs / "paper.md"
    meta, body = split_front_matter(md.read_text(encoding="utf-8"))
    assert meta["docflow_pdf_path"] == "Pdfs/Pdfs 2026/paper.pdf"
    assert meta["docflow_markdown_path"] == "Pdfs/Pdfs 2026/paper.md"
    assert meta["docflow_render_status"] == "markdown_only"
    assert meta["docflow_source_type"] == "pdf"
    assert meta["docflow_ingested_at"].endswith("Z")
    assert "Associated PDF: `paper.pdf`" in body


def test_backfill_pdf_sidecars_dry_run_does_not_write(tmp_path: Path):
    base = tmp_path / "base"
    pdfs = base / "Pdfs" / "Pdfs 2026"
    pdfs.mkdir(parents=True)
    (pdfs / "paper.pdf").write_bytes(b"%PDF-1.4\n")

    result = backfill_pdf_sidecars(base, dry_run=True)

    assert result.total_pdfs == 1
    assert result.created == 1
    assert not (pdfs / "paper.md").exists()


def test_backfill_pdf_sidecars_completes_existing_sidecar_without_mtime_change(tmp_path: Path):
    base = tmp_path / "base"
    pdfs = base / "Pdfs" / "Pdfs 2026"
    pdfs.mkdir(parents=True)
    (pdfs / "paper.pdf").write_bytes(b"%PDF-1.4\n")
    md = pdfs / "paper.md"
    md.write_text("---\ntitle: Existing\n---\n\n# Existing\n", encoding="utf-8")
    original_mtime = md.stat().st_mtime

    result = backfill_pdf_sidecars(base)

    assert result.total_pdfs == 1
    assert result.created == 0
    assert result.updated == 1
    assert abs(md.stat().st_mtime - original_mtime) < 0.001

    meta, body = split_front_matter(md.read_text(encoding="utf-8"))
    assert meta["title"] == "Existing"
    assert meta["docflow_pdf_path"] == "Pdfs/Pdfs 2026/paper.pdf"
    assert "docflow_ingested_at" not in meta
    assert body.lstrip().startswith("# Existing")
