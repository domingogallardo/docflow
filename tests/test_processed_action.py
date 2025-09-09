from pathlib import Path
import io
import importlib.util
import time
import urllib.parse
import os


def _load_serve_docs(mod_name: str):
    repo_root = Path(__file__).resolve().parents[1]
    sd_path = repo_root / "utils" / "serve_docs.py"
    spec = importlib.util.spec_from_file_location(mod_name, sd_path)
    sd = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(sd)  # type: ignore[union-attr]
    return sd


def _make_post_handler(sd, body: str):
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

    return Dummy()


def test_processed_action_unbumps_adds_to_md_and_deploys(tmp_path, monkeypatch):
    sd = _load_serve_docs("serve_docs_processed")

    # Setup serve dir and public reads
    serve_dir = tmp_path / "serve"
    public_reads = tmp_path / "public_reads"
    serve_dir.mkdir()
    public_reads.mkdir()

    # Create bumped and published HTML
    html_file = serve_dir / "doc.html"
    html_file.write_text("<html></html>", encoding="utf-8")
    future = sd.base_epoch_cached() + 10
    at = html_file.stat().st_atime
    os.utime(str(html_file), (at, future))
    (public_reads / html_file.name).write_text("<html>pub</html>", encoding="utf-8")

    # Monkeypatch paths and deploy script
    monkeypatch.setattr(sd, "SERVE_DIR", str(serve_dir), raising=False)
    monkeypatch.setattr(sd, "PUBLIC_READS_DIR", str(public_reads), raising=False)
    deploy = tmp_path / "deploy.sh"
    deploy.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    os.chmod(deploy, 0o755)
    monkeypatch.setattr(sd, "DEPLOY_SCRIPT", str(deploy), raising=False)

    # POST processed
    body = f"path={urllib.parse.quote(html_file.name)}&action=processed"
    h = _make_post_handler(sd, body)
    h.do_POST()

    # Status OK
    assert h._sent["status"] == 200
    # Unbumped
    assert html_file.stat().st_mtime <= time.time()
    # read_posts.md created with filename as first entry
    md = (public_reads / "read_posts.md").read_text(encoding="utf-8")
    assert md.splitlines()[0].strip().endswith("doc.html")

