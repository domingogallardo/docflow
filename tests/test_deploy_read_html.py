from pathlib import Path
import os
import subprocess

def _extract_python_snippet() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    script = (repo_root / "web" / "deploy.sh").read_text(encoding="utf-8")
    start = script.index("<< 'PY'\n") + len("<< 'PY'\n")
    end = script.index("\nPY", start)
    return script[start:end]

def test_gen_index_creates_read_html(tmp_path):
    snippet = _extract_python_snippet()
    (tmp_path / "a.html").write_text("<p>A</p>", encoding="utf-8")
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4\n")
    env = os.environ.copy()
    env.update({
        "DIR_PATH": str(tmp_path),
        "TITLE": "Read",
        "EXT_FILTER": ".html,.pdf",
    })
    subprocess.run(["python3", "-"], input=snippet, text=True, env=env, check=True)
    read_file = tmp_path / "read.html"
    assert read_file.exists()
    assert not (tmp_path / "index.html").exists()
    content = read_file.read_text(encoding="utf-8")
    assert "read.html" not in content
