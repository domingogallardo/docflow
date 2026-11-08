"""HTTP access checks with a fake application; no document operations."""
import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from utils.docflow_server import make_handler


PUBLIC = "https://nuevo-macbook-air-de-domingo.tail9bf5a2.ts.net"


class FakeApp:
    def __init__(self):
        self.calls = []

    def resolve_site_file(self, path):
        return None

    def handle_api(self, action, payload):
        self.calls.append((action, payload))
        return {"accepted": True}

    def api_put_highlights(self, path, payload):
        self.calls.append((path, payload))
        return {"ok": True}


@pytest.fixture
def server():
    app = FakeApp()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app, PUBLIC))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_port, app
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=2)


def request(server, method="POST", headers=None, path="/api/to-done"):
    port, app = server
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        values = {"Content-Type": "application/json", **(headers or {})}
        connection.request(method, path, body=json.dumps({"path": "fake-document"}), headers=values)
        response = connection.getresponse()
        response.read()
        return response.status, dict(response.getheaders())
    finally:
        connection.close()


@pytest.mark.parametrize("host", ["attacker.invalid", "attacker.invalid:8080", "127.0.0.1.attacker.invalid"])
def test_rejects_foreign_host_before_application(server, host):
    assert request(server, headers={"Host": host})[0] == 403
    assert server[1].calls == []


@pytest.mark.parametrize("method,path", [("POST", "/api/delete"), ("PUT", "/api/highlights?path=fake")])
@pytest.mark.parametrize("origin", ["https://attacker.invalid", "null", PUBLIC + ".attacker.invalid"])
def test_rejects_foreign_origin_before_application(server, method, path, origin):
    assert request(server, method, {"Origin": origin}, path)[0] == 403
    assert server[1].calls == []


def test_rejects_cross_site_fetch_without_origin(server):
    assert request(server, headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert server[1].calls == []


def test_plain_text_form_cannot_trigger_json_action(server):
    assert request(server, headers={"Content-Type": "text/plain"})[0] == 415
    assert server[1].calls == []


def test_body_limit_is_checked_before_reading_or_calling_application(server):
    assert request(server, headers={"Content-Length": str(2 * 1024 * 1024 + 1)})[0] == 413
    assert server[1].calls == []


def test_negative_content_length_is_rejected(server):
    assert request(server, headers={"Content-Length": "-1"})[0] == 400
    assert server[1].calls == []


def test_local_json_client_remains_supported(server):
    assert request(server)[0] == 200
    assert len(server[1].calls) == 1


def test_tailscale_https_origin_and_host_remain_supported(server):
    assert request(server, headers={"Host": PUBLIC.removeprefix("https://"), "Origin": PUBLIC})[0] == 200
    assert len(server[1].calls) == 1


def test_same_origin_highlights_remain_supported(server):
    assert request(server, "PUT", {"Host": PUBLIC.removeprefix("https://"), "Origin": PUBLIC},
                   "/api/highlights?path=fake")[0] == 200
    assert len(server[1].calls) == 1


def test_foreign_host_cannot_read_pages(server):
    assert request(server, "GET", {"Host": "attacker.invalid"}, "/")[0] == 403


def test_defensive_response_headers(server):
    _, headers = request(server, "GET", {"Host": "attacker.invalid"}, "/")
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "SAMEORIGIN"
    assert headers["Referrer-Policy"] == "no-referrer"


@pytest.mark.parametrize("origin", ["https://user:password@example.com", "https://example.com/path", "file:///tmp"])
def test_public_origin_configuration_cannot_include_credentials_or_path(origin):
    with pytest.raises(ValueError):
        make_handler(FakeApp(), origin)
