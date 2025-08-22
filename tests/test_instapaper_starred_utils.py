import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
import utils


def test_is_instapaper_starred_file_html_instapaper_template_starred(tmp_path):
    """Usa el mismo HTML que genera InstapaperProcessor cuando está starred."""
    html = tmp_path / "starred_instapaper.html"
    content = (
        "<!DOCTYPE html>\n"
        "<!-- instapaper_starred: true method=read_or_list -->\n"
        '<html data-instapaper-starred="true">\n'
        "<head>\n"
        '<meta charset="UTF-8">\n'
        '<meta name="instapaper-starred" content="true">\n'
        "<title>Starred Sample</title>\n"
        "</head>\n<body>\n"
        "<h1>Starred Sample</h1>\n"
        "<div id='origin'>Example.com · 12345</div>\n"
        "<p>Body</p>\n"
        "</body>\n</html>"
    )
    html.write_text(content, encoding="utf-8")
    assert utils.is_instapaper_starred_file(html) is True


def test_is_instapaper_starred_file_html_data_attr(tmp_path):
    html = tmp_path / "star_attr.html"
    html.write_text(
        '<html data-instapaper-starred="true"><head></head><body></body></html>',
        encoding="utf-8",
    )
    assert utils.is_instapaper_starred_file(html) is True


def test_is_instapaper_starred_file_html_instapaper_template_not_starred(tmp_path):
    """Usa el HTML que genera InstapaperProcessor cuando NO está starred."""
    html = tmp_path / "not_starred_instapaper.html"
    content = (
        "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"UTF-8\">\n"
        "<title>Normal Sample</title>\n"
        "</head>\n<body>\n"
        "<h1>Normal Sample</h1>\n"
        "<div id='origin'>Example.com · 12345</div>\n"
        "<p>Body</p>\n"
        "</body>\n</html>"
    )
    html.write_text(content, encoding="utf-8")
    assert utils.is_instapaper_starred_file(html) is False


def test_is_instapaper_starred_file_md_front_matter(tmp_path):
    md = tmp_path / "front_matter.md"
    md.write_text(
        "---\ninstapaper_starred: true\n---\n# Title\nBody\n",
        encoding="utf-8",
    )
    assert utils.is_instapaper_starred_file(md) is True


def test_is_instapaper_starred_file_md_plain_line(tmp_path):
    md = tmp_path / "plain_line.md"
    md.write_text(
        "instapaper_starred: true\n\n# Title\nBody\n",
        encoding="utf-8",
    )
    assert utils.is_instapaper_starred_file(md) is True


def test_is_instapaper_starred_file_unsupported_extension(tmp_path):
    txt = tmp_path / "note.txt"
    txt.write_text("instapaper_starred: true", encoding="utf-8")
    assert utils.is_instapaper_starred_file(txt) is False

