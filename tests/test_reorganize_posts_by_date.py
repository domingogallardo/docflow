from pathlib import Path

from bs4 import BeautifulSoup

from utils.markdown_utils import split_front_matter
from utils.reorganize_posts_by_date import effective_post_year, reorganize_posts_by_date


def test_effective_post_year_prefers_ingested_at_over_original_published_at():
    year, reason = effective_post_year(
        {
            "docflow_ingested_at": "2026-05-01T10:00:00Z",
            "docflow_original_published_at": "2014-01-02",
        },
        current_folder_year=1990,
    )

    assert year == 2026
    assert reason == "docflow_ingested_at"


def test_effective_post_year_falls_back_to_original_published_at():
    year, reason = effective_post_year(
        {"docflow_original_published_at": "2014-01-02"},
        current_folder_year=1990,
    )

    assert year == 2014
    assert reason == "docflow_original_published_at"


def test_reorganize_posts_by_date_moves_pair_updates_paths_and_preserves_mtime(tmp_path: Path):
    base = tmp_path / "base"
    source_dir = base / "Posts" / "Posts 1990"
    source_dir.mkdir(parents=True)
    md = source_dir / "Article.md"
    html = source_dir / "Article.html"
    md.write_text(
        "---\n"
        "docflow_id: existing-id\n"
        "docflow_markdown_path: Posts/Posts 1990/Article.md\n"
        "docflow_html_path: Posts/Posts 1990/Article.html\n"
        "docflow_render_status: paired_html\n"
        "docflow_original_published_at: 2014-01-02\n"
        "---\n\n# Article\n",
        encoding="utf-8",
    )
    html.write_text(
        "<html><head><meta name=\"docflow-markdown-path\" content=\"Posts/Posts 1990/Article.md\"></head><body></body></html>",
        encoding="utf-8",
    )
    md_mtime_ns = md.stat().st_mtime_ns
    html_mtime_ns = html.stat().st_mtime_ns

    result = reorganize_posts_by_date(base)

    assert result.scanned == 1
    assert result.planned == 1
    assert result.moved == 1
    new_md = base / "Posts" / "Posts 2014" / "Article.md"
    new_html = base / "Posts" / "Posts 2014" / "Article.html"
    assert new_md.is_file()
    assert new_html.is_file()
    assert not md.exists()
    assert not html.exists()
    assert new_md.stat().st_mtime_ns == md_mtime_ns
    assert new_html.stat().st_mtime_ns == html_mtime_ns

    meta, _ = split_front_matter(new_md.read_text(encoding="utf-8"))
    assert meta["docflow_markdown_path"] == "Posts/Posts 2014/Article.md"
    assert meta["docflow_html_path"] == "Posts/Posts 2014/Article.html"
    assert meta["docflow_render_status"] == "paired_html"

    soup = BeautifulSoup(new_html.read_text(encoding="utf-8"), "html.parser")
    assert (
        soup.find("meta", attrs={"name": "docflow-markdown-path"})["content"]
        == "Posts/Posts 2014/Article.md"
    )
    assert (
        soup.find("meta", attrs={"name": "docflow-html-path"})["content"]
        == "Posts/Posts 2014/Article.html"
    )


def test_reorganize_posts_by_date_dry_run_does_not_move(tmp_path: Path):
    base = tmp_path / "base"
    source_dir = base / "Posts" / "Posts 1990"
    source_dir.mkdir(parents=True)
    md = source_dir / "Article.md"
    md.write_text("---\ndocflow_original_published_at: 2014-01-02\n---\n\n# Article\n", encoding="utf-8")

    result = reorganize_posts_by_date(base, dry_run=True)

    assert result.planned == 1
    assert result.moved == 0
    assert md.is_file()
    assert not (base / "Posts" / "Posts 2014" / "Article.md").exists()


def test_reorganize_posts_by_date_skips_conflicts(tmp_path: Path):
    base = tmp_path / "base"
    source_dir = base / "Posts" / "Posts 1990"
    target_dir = base / "Posts" / "Posts 2014"
    source_dir.mkdir(parents=True)
    target_dir.mkdir(parents=True)
    md = source_dir / "Article.md"
    md.write_text("---\ndocflow_original_published_at: 2014-01-02\n---\n\n# Article\n", encoding="utf-8")
    (target_dir / "Article.md").write_text("# Existing\n", encoding="utf-8")

    result = reorganize_posts_by_date(base)

    assert result.planned == 1
    assert result.conflicts == 1
    assert result.moved == 0
    assert md.is_file()
