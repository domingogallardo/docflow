from pathlib import Path
import io
import importlib.util
import time
import urllib.parse


def _load_serve_docs(alias: str):
    repo_root = Path(__file__).resolve().parents[1]
    sd_path = repo_root / "utils" / "serve_docs.py"
    spec = importlib.util.spec_from_file_location(alias, sd_path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _make_dummy_handler(handler_cls):
    """Create a minimal handler instance able to capture list_directory output."""
    class Dummy(handler_cls):
        def __init__(self):
            # Do not call base __init__; we just need minimal fields
            self.path = "/"
            self.wfile = io.BytesIO()
            self._sent = {"status": None, "headers": []}

        # Capture response metadata (avoid socket usage)
        def send_response(self, code, message=None):  # type: ignore[override]
            self._sent["status"] = code

        def send_header(self, key, value):  # type: ignore[override]
            self._sent["headers"].append((key, value))

        def end_headers(self):  # type: ignore[override]
            pass

    return Dummy()


def test_directory_index_marks_published_html(tmp_path, monkeypatch):
    sd = _load_serve_docs("serve_docs")

    # Arrange: temp serve dir with files
    serve_dir = tmp_path / "serve"
    serve_dir.mkdir()
    html_pub = serve_dir / "articulo_publicado.html"
    html_unpub = serve_dir / "articulo_local.html"
    pdf_file = serve_dir / "doc.pdf"
    md_file = serve_dir / "nota.md"
    html_pub.write_text("<html><body>Publicado</body></html>", encoding="utf-8")
    html_unpub.write_text("<html><body>Local</body></html>", encoding="utf-8")
    pdf_file.write_bytes(b"%PDF-1.4\n%...\n")
    md_file.write_text("md", encoding="utf-8")

    # Arrange: temp public reads dir with same-name file to mark as published
    public_reads = tmp_path / "public_reads"
    public_reads.mkdir()
    (public_reads / html_pub.name).write_text("<html>copiado</html>", encoding="utf-8")

    # Monkeypatch the PUBLIC_READS_DIR used by the handler
    monkeypatch.setattr(sd, "PUBLIC_READS_DIR", str(public_reads), raising=False)

    # Act: build directory listing
    h = _make_dummy_handler(sd.HTMLOnlyRequestHandler)
    # For display title
    h.path = "/"
    h.list_directory(str(serve_dir))
    data = h.wfile.getvalue().decode("utf-8")

    # Assert: published file is highlighted (🟢 and class dg-pub)
    assert "🟢" in data, "No se muestra el icono de publicado"
    assert "class=\"dg-pub\"" in data or " dg-pub" in data, "No se aplica la clase CSS de publicado"

    # Assert: unpublished html does not have green marker
    assert "articulo_local.html" in data
    # Buscamos la línea del no publicado y comprobamos que no contiene 🟢
    for line in data.splitlines():
        if "articulo_local.html" in line:
            assert "🟢" not in line and "dg-pub" not in line
            break

    # Los ficheros .md no deben mostrarse
    assert "nota.md" not in data


def test_directory_index_pdf_actions_and_publish_detection(tmp_path, monkeypatch):
    sd = _load_serve_docs("serve_docs_pdf")

    # Estructura: un PDF bumped/no-pub y otro bumped+publicado
    serve_dir = tmp_path / "serve"
    serve_dir.mkdir()
    pdf_pub = serve_dir / "paper_publicado.pdf"
    pdf_local = serve_dir / "paper_local.pdf"
    pdf_pub.write_bytes(b"%PDF-1.4\n")
    pdf_local.write_bytes(b"%PDF-1.4\n")

    # Marcar ambos como bumped (mtime en futuro)
    future = sd.base_epoch_cached() + 10
    at = pdf_local.stat().st_atime
    __import__("os").utime(str(pdf_local), (at, future))
    at_pub = pdf_pub.stat().st_atime
    __import__("os").utime(str(pdf_pub), (at_pub, future))

    # Directorio público de reads temporal con el homónimo publicado
    public_reads = tmp_path / "public_reads"
    public_reads.mkdir()
    (public_reads / pdf_pub.name).write_bytes(b"%PDF-1.4\n")

    # Patch directorio público de reads
    __import__("pytest")
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    mp.setattr(sd, "PUBLIC_READS_DIR", str(public_reads), raising=False)

    # Generar listado
    h = _make_dummy_handler(sd.HTMLOnlyRequestHandler)
    h.path = "/"
    h.list_directory(str(serve_dir))
    html = h.wfile.getvalue().decode("utf-8")

    # El PDF publicado muestra acciones Unbump y Despublicar
    assert "paper_publicado.pdf" in html
    for line in html.splitlines():
        if "paper_publicado.pdf" in line:
            assert "🟢" in line or "dg-pub" in line
            assert "data-dg-act='unbump_now'" in line
            assert "data-dg-act='unpublish'" in line
            assert "data-dg-act='publish'" not in line
            break

    # El PDF local bumped muestra acciones Unbump y una opción de Publicar (reads)
    assert "paper_local.pdf" in html
    for line in html.splitlines():
        if "paper_local.pdf" in line:
            assert "data-dg-act='unbump_now'" in line
            assert "data-dg-act='publish'" in line
            assert "data-dg-target" not in line
            break


def test_unbump_published_file_via_post(tmp_path, monkeypatch):
    sd = _load_serve_docs("serve_docs_post")

    serve_dir = tmp_path / "serve"
    serve_dir.mkdir()
    html_file = serve_dir / "doc.html"
    html_file.write_text("<html></html>", encoding="utf-8")
    future = sd.base_epoch_cached() + 10
    at = html_file.stat().st_atime
    __import__("os").utime(str(html_file), (at, future))

    public_reads = tmp_path / "public_reads"
    public_reads.mkdir()
    (public_reads / html_file.name).write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(sd, "PUBLIC_READS_DIR", str(public_reads), raising=False)
    monkeypatch.setattr(sd, "SERVE_DIR", str(serve_dir), raising=False)

    body = f"path={urllib.parse.quote(html_file.name)}&action=unbump_now"

    class Dummy(sd.HTMLOnlyRequestHandler):
        def __init__(self):
            self.path = "/__bump"
            self.command = "POST"
            self.requestline = "POST /__bump HTTP/1.1"
            self.headers = {"Content-Length": str(len(body))}
            self.rfile = io.BytesIO(body.encode("utf-8"))
            self.wfile = io.BytesIO()
            self._sent = {"status": None}
            self.client_address = ("127.0.0.1", 0)

        def send_response(self, code, message=None):  # type: ignore[override]
            self._sent["status"] = code

        def send_header(self, key, value):  # type: ignore[override]
            pass

        def end_headers(self):  # type: ignore[override]
            pass

    h = Dummy()
    h.do_POST()
    assert h._sent["status"] == 200
    assert html_file.stat().st_mtime <= time.time()

def test_delete_file_and_public_copy(tmp_path, monkeypatch):
    sd = _load_serve_docs("serve_docs_delete")

    serve_dir = tmp_path / "serve"
    serve_dir.mkdir()
    html_file = serve_dir / "doc.html"
    html_file.write_text("<html></html>", encoding="utf-8")

    public_reads = tmp_path / "public_reads"
    public_reads.mkdir()
    public_copy = public_reads / html_file.name
    public_copy.write_text("<html></html>", encoding="utf-8")
    md_file = html_file.with_suffix(".md")
    md_file.write_text("# doc\n", encoding="utf-8")

    monkeypatch.setattr(sd, "PUBLIC_READS_DIR", str(public_reads), raising=False)
    monkeypatch.setattr(sd, "SERVE_DIR", str(serve_dir), raising=False)

    body = f"path={urllib.parse.quote(html_file.name)}&action=delete"

    class Dummy(sd.HTMLOnlyRequestHandler):
        def __init__(self):
            self.path = "/__bump"
            self.command = "POST"
            self.requestline = "POST /__bump HTTP/1.1"
            self.headers = {"Content-Length": str(len(body))}
            self.rfile = io.BytesIO(body.encode("utf-8"))
            self.wfile = io.BytesIO()
            self._sent = {"status": None}
            self.client_address = ("127.0.0.1", 0)

        def send_response(self, code, message=None):  # type: ignore[override]
            self._sent["status"] = code

        def send_header(self, key, value):  # type: ignore[override]
            pass

        def end_headers(self):  # type: ignore[override]
            pass

    h = Dummy()
    h.do_POST()

    assert h._sent["status"] == 200
    assert not html_file.exists()
    assert not public_copy.exists()
    assert not md_file.exists()


def test_publish_sets_public_mtime_without_unbumping(tmp_path, monkeypatch):
    sd = _load_serve_docs("serve_docs_publish_mtime")

    serve_dir = tmp_path / "serve"
    serve_dir.mkdir()
    html_file = serve_dir / "doc.html"
    html_file.write_text("<html><head></head><body></body></html>", encoding="utf-8")

    # Bump local mtime al futuro
    future = sd.base_epoch_cached() + 10
    at = html_file.stat().st_atime
    __import__("os").utime(str(html_file), (at, future))

    public_reads = tmp_path / "public_reads"
    public_reads.mkdir()
    monkeypatch.setattr(sd, "PUBLIC_READS_DIR", str(public_reads), raising=False)
    monkeypatch.setattr(sd, "SERVE_DIR", str(serve_dir), raising=False)

    # Script de deploy simulado (no hace nada)
    deploy = tmp_path / "deploy.sh"
    deploy.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    __import__("os").chmod(deploy, 0o755)
    monkeypatch.setattr(sd, "DEPLOY_SCRIPT", str(deploy), raising=False)

    body = f"path={urllib.parse.quote(html_file.name)}&action=publish"

    class Dummy(sd.HTMLOnlyRequestHandler):
        def __init__(self):
            self.path = "/__bump"
            self.command = "POST"
            self.requestline = "POST /__bump HTTP/1.1"
            self.headers = {"Content-Length": str(len(body))}
            self.rfile = io.BytesIO(body.encode("utf-8"))
            self.wfile = io.BytesIO()
            self._sent = {"status": None}
            self.client_address = ("127.0.0.1", 0)

        def send_response(self, code, message=None):  # type: ignore[override]
            self._sent["status"] = code

        def send_header(self, key, value):  # type: ignore[override]
            pass

        def end_headers(self):  # type: ignore[override]
            pass

    now_before = time.time()
    h = Dummy()
    h.do_POST()
    now_after = time.time()

    assert h._sent["status"] == 200

    src_mtime = html_file.stat().st_mtime
    dst_path = public_reads / html_file.name
    assert dst_path.exists()
    dst_mtime = dst_path.stat().st_mtime

    # Local sigue bumped al futuro; la copia pública queda datada en el momento de publicar
    assert src_mtime > now_after
    assert now_before - 2 <= dst_mtime <= now_after + 2


def test_compute_bump_mtime_uses_current_base(monkeypatch):
    sd = _load_serve_docs("serve_docs_compute")

    bases = [1_000_000_000, 1_000_010_000]

    def fake_base():
        return bases.pop(0)

    monkeypatch.setattr(sd, "_apple_like_base_epoch", fake_base, raising=True)

    first = sd.compute_bump_mtime()
    second = sd.compute_bump_mtime()

    assert first == 1_000_000_000 + 1
    assert second == 1_000_010_000 + 1
