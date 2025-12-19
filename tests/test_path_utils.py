from path_utils import unique_pair, unique_path


def test_unique_path_returns_original_when_available(tmp_path):
    target = tmp_path / "file.txt"
    assert unique_path(target) == target


def test_unique_path_appends_counter(tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")
    candidate = unique_path(target)
    assert candidate.name == "file (1).txt"
    candidate.write_text("y", encoding="utf-8")
    candidate2 = unique_path(target)
    assert candidate2.name == "file (2).txt"


def test_unique_pair_keeps_existing_when_allowed(tmp_path):
    md_path = tmp_path / "note.md"
    html_path = tmp_path / "note.html"
    md_path.write_text("x", encoding="utf-8")
    html_path.write_text("y", encoding="utf-8")

    primary, secondary = unique_pair(
        md_path,
        html_path,
        allow_existing_primary=md_path,
        allow_existing_secondary=html_path,
    )
    assert primary == md_path
    assert secondary == html_path


def test_unique_pair_appends_counter(tmp_path):
    md_path = tmp_path / "note.md"
    html_path = tmp_path / "note.html"
    md_path.write_text("x", encoding="utf-8")
    html_path.write_text("y", encoding="utf-8")

    primary, secondary = unique_pair(md_path, html_path)
    assert primary.name == "note (1).md"
    assert secondary.name == "note (1).html"
