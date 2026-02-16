from pathlib import Path
import os
import subprocess
from urllib.parse import quote

def test_gen_index_creates_read_html(tmp_path):
    # Create test files.
    (tmp_path / "a.html").write_text("<p>A</p>", encoding="utf-8")
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4\n")
    tweets_2026 = tmp_path / "tweets" / "2026"
    tweets_2025 = tmp_path / "tweets" / "2025"
    tweets_2026.mkdir(parents=True)
    tweets_2025.mkdir(parents=True)
    (tweets_2026 / "Tweets 2026-01-02.html").write_text("x", encoding="utf-8")
    (tweets_2026 / "Tweets 2026-01-01.html").write_text("x", encoding="utf-8")
    (tweets_2025 / "Tweets 2025-12-31.html").write_text("x", encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[1]
    builder = repo_root / "utils" / "build_read_index.py"
    assert builder.exists(), "utils/build_read_index.py no encontrado"

    # Run generator.
    subprocess.run(["python3", str(builder), str(tmp_path)], check=True)

    # Check results.
    read_file = tmp_path / "read.html"
    assert read_file.exists()
    assert not (tmp_path / "index.html").exists()
    content = read_file.read_text(encoding="utf-8")
    assert "read.html" not in content
    assert "<h2>Tweets</h2>" in content
    assert '<a href="/read/tweets/2026.html">2026</a> (2)' in content
    assert '<a href="/read/tweets/2025.html">2025</a> (1)' in content
    assert "Sections" not in content
    assert 'href="https://domingogallardo.com/"' in content
    for line in content.splitlines():
        if 'href="a.html"' in line:
            assert "📄" in line
            assert "a.html</a> — " in line
            break
    else:
        raise AssertionError("No se encontro la entrada de a.html")
    for line in content.splitlines():
        if 'href="b.pdf"' in line:
            assert "📕" in line
            assert "b.pdf</a> — " in line
            break
    else:
        raise AssertionError("No se encontro la entrada de b.pdf")


def test_build_read_index_marks_highlighted_html():
    import importlib.util
    import pathlib
    path = pathlib.Path('utils/build_read_index.py')
    spec = importlib.util.spec_from_file_location('build_read_index_hl', path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore
    entries = [(0.0, 'doc(1).html')]
    encoded = quote('doc(1).html')
    highlights = {f"{encoded}.json"}
    html = mod.build_html('web/public/read', entries, highlight_files=highlights)
    for line in html.splitlines():
        if 'href="doc(1).html"' in line:
            assert "🟡" in line
            break
    else:
        raise AssertionError("No se encontro la entrada de doc(1).html")


def test_build_read_index_owner_url_override(monkeypatch):
    import importlib.util
    import pathlib
    path = pathlib.Path('utils/build_read_index.py')
    spec = importlib.util.spec_from_file_location('build_read_index_owner', path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore
    monkeypatch.setenv("DOCFLOW_OWNER_URL", "https://example.com/")
    html = mod.build_html('web/public/read', [])
    assert 'href="https://example.com/"' in html
