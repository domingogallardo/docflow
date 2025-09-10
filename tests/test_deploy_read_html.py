from pathlib import Path
import os
import subprocess

def test_gen_index_creates_read_html(tmp_path):
    # Crear ficheros de prueba
    (tmp_path / "a.html").write_text("<p>A</p>", encoding="utf-8")
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4\n")

    repo_root = Path(__file__).resolve().parents[1]
    builder = repo_root / "utils" / "build_read_index.py"
    assert builder.exists(), "utils/build_read_index.py no encontrado"

    # Ejecutar generador
    subprocess.run(["python3", str(builder), str(tmp_path)], check=True)

    # Comprobar resultados
    read_file = tmp_path / "read.html"
    assert read_file.exists()
    assert not (tmp_path / "index.html").exists()
    content = read_file.read_text(encoding="utf-8")
    assert "read.html" not in content
