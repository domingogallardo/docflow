import utils.clipboard_cleaner as cleaner
from collections import deque
import base64
import plistlib


def test_compact_unordered_list():
    html = "<ul><li><p>Uno</p></li><li><p>Dos</p></li></ul>"
    assert cleaner.html_to_compact_markdown(html) == "- Uno\n- Dos"


def test_preserves_spacing_after_list():
    html = "<ul><li>Uno</li><li>Dos</li></ul><p>Texto final</p>"
    expected = "- Uno\n- Dos\n\nTexto final"
    assert cleaner.html_to_compact_markdown(html) == expected


def test_compact_numbered_list():
    html = "<ol><li>Primero</li><li>Segundo</li></ol>"
    assert cleaner.html_to_compact_markdown(html) == "1. Primero\n2. Segundo"


def test_list_item_with_multiple_paragraphs():
    html = "<ul><li><p>Uno</p><p>Extra</p></li><li>Dos</li></ul>"
    expected = "- Uno\n\n  Extra\n- Dos"
    assert cleaner.html_to_compact_markdown(html) == expected


def test_read_macos_html_clipboard_prefers_pbpaste(monkeypatch):
    monkeypatch.setattr(
        cleaner,
        "_run_command_capture",
        lambda cmd: "<div>Item</div>" if "-Prefer" in cmd else "",
    )
    monkeypatch.setattr(cleaner, "_run_osascript", lambda script: "")
    assert cleaner._read_macos_html_clipboard() == "<div>Item</div>"


def test_read_macos_html_clipboard_public_html_fallback(monkeypatch):
    monkeypatch.setattr(cleaner, "_run_command_capture", lambda cmd: "")
    def responder(script: str) -> str:
        if "public.html" in script:
            return "<ul><li>Item</li></ul>"
        return ""

    monkeypatch.setattr(cleaner, "_run_osascript", responder)
    assert cleaner._read_macos_html_clipboard() == "<ul><li>Item</li></ul>"


def test_read_macos_html_clipboard_webarchive_fallback(monkeypatch):
    monkeypatch.setattr(cleaner, "_run_command_capture", lambda cmd: "")
    webarchive = plistlib.dumps(
        {
            "WebMainResource": {
                "WebResourceData": b"<ol><li>Item</li></ol>",
            }
        }
    )
    responses = deque(
        [
            "",
            base64.b64encode(webarchive).decode("ascii"),
        ]
    )
    monkeypatch.setattr(cleaner, "_run_osascript", lambda script: responses.popleft())
    assert cleaner._read_macos_html_clipboard() == "<ol><li>Item</li></ol>"


def test_flattens_tables_to_plain_markdown():
    html = (
        "<table>"
        "<tr><td><p>Titulo</p></td></tr>"
        "<tr><td>Texto con <a href='https://example.com'>enlace</a></td></tr>"
        "</table>"
    )
    assert cleaner.html_to_compact_markdown(html) == "Titulo\n\nTexto con [enlace](https://example.com)"


def test_converts_apple_converted_space_to_plain_space():
    html = '<p>Hola<span class="Apple-converted-space">\u00a0</span>mundo</p>'
    assert cleaner.html_to_compact_markdown(html) == "Hola mundo"


def test_email_like_html_flattens_and_keeps_contents():
    html = """
    <head><meta charset='UTF-8'></head>
    <table><tr><td>
      <table><tr><td>
        <p>Title</p>
        <p>AUTHOR</p>
        <img src='https://example.com/img.jpg' alt='Foto del artículo'>
        <p>Texto con <a href='https://example.com'>enlace</a> y <span class='Apple-converted-space'>\u00a0</span>espacio.</p>
      </td></tr></table>
    </td></tr></table>
    """
    expected = (
        "Title\n\n"
        "AUTHOR\n\n"
        "![Foto del artículo](https://example.com/img.jpg)\n\n"
        "Texto con [enlace](https://example.com) y espacio."
    )
    assert cleaner.html_to_compact_markdown(html) == expected
