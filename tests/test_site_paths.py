from pathlib import Path

import pytest

from utils import site_paths


def test_normalize_rel_path_accepts_clean_values():
    assert site_paths.normalize_rel_path("Posts/Posts 2026/doc.html") == "Posts/Posts 2026/doc.html"
    assert site_paths.normalize_rel_path("/Posts/Posts 2026/doc.html") == "Posts/Posts 2026/doc.html"
    assert site_paths.normalize_rel_path("Posts\\Posts 2026\\doc.html") == "Posts/Posts 2026/doc.html"


def test_normalize_rel_path_rejects_traversal():
    with pytest.raises(site_paths.PathValidationError):
        site_paths.normalize_rel_path("../etc/passwd")

    with pytest.raises(site_paths.PathValidationError):
        site_paths.normalize_rel_path("  ")


def test_resolve_library_path_stays_inside_base(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    target = base / "Posts" / "Posts 2026" / "doc.html"
    target.parent.mkdir(parents=True)
    target.write_text("ok", encoding="utf-8")

    resolved = site_paths.resolve_library_path(base, "Posts/Posts 2026/doc.html")
    assert resolved == target.resolve()

    with pytest.raises(site_paths.PathValidationError):
        site_paths.resolve_library_path(base, "../../escape.txt")


def test_raw_url_for_rel_path_uses_bucket_prefixes():
    assert site_paths.raw_url_for_rel_path("Pdfs/Pdfs 2026/a.pdf").startswith("/pdfs/raw/")
    assert site_paths.raw_url_for_rel_path("Images/Images 2026/a.png").startswith("/images/raw/")
    assert site_paths.raw_url_for_rel_path("Posts/Posts 2026/a.html").startswith("/posts/raw/")


def test_resolve_base_dir_prefers_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv(site_paths.BASE_DIR_ENV, str(tmp_path))
    assert site_paths.resolve_base_dir() == tmp_path
