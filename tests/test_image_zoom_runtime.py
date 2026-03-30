from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

import pytest

from utils import docflow_server


def _start_server(base_dir: Path) -> tuple[ThreadingHTTPServer, int]:
    app = docflow_server.DocflowApp(base_dir)
    app.rebuild()
    handler_cls = docflow_server.make_handler(app)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def _svg_data_uri(label: str, fill: str) -> str:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">'
        f'<rect width="64" height="64" fill="{fill}"/>'
        f'<text x="32" y="38" text-anchor="middle" font-size="24" fill="#fff">{label}</text>'
        '</svg>'
    )
    return f"data:image/svg+xml;charset=utf-8,{quote(svg)}"


def _legacy_image_viewer_script() -> str:
    return (
        '<script id="image-viewer">(function(){'
        'function ensureOverlay(){'
        'var overlay=document.getElementById("image-viewer-overlay");'
        'if(!overlay){'
        'overlay=document.createElement("div");'
        'overlay.id="image-viewer-overlay";'
        'overlay.style.cssText="position:fixed;inset:0;display:flex;align-items:center;justify-content:center;background:#111;z-index:9999;";'
        'var img=document.createElement("img");'
        'overlay.appendChild(img);'
        'document.body.appendChild(overlay);'
        '}'
        'return overlay;'
        '}'
        'function showOverlay(src,alt){'
        'var overlay=ensureOverlay();'
        'var img=overlay.querySelector("img");'
        'img.src=src;'
        'img.alt=alt||"";'
        '}'
        'document.addEventListener("click",function(e){'
        'var link=e.target.closest("a.image-zoom");'
        'if(!link){return;}'
        'var src=link.getAttribute("href");'
        'if(!src){return;}'
        'var img=link.querySelector("img");'
        'var alt=img?(img.getAttribute("alt")||""):"";'
        'e.preventDefault();'
        'showOverlay(src,alt);'
        '});'
        '})();</script>'
    )


def test_raw_route_clicking_second_image_uses_clicked_source(tmp_path: Path):
    playwright = pytest.importorskip("playwright.sync_api")
    sync_playwright = playwright.sync_playwright

    base = tmp_path / "base"
    posts = base / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)

    first = _svg_data_uri("1", "#aa2233")
    second = _svg_data_uri("2", "#2255aa")
    html = (
        "<html><head>"
        f"{_legacy_image_viewer_script()}"
        "</head><body><p>"
        f'<a class="image-zoom" href="{first}">'
        f'<img alt="image 1" src="{first}">'
        "<br>"
        f'<img alt="image 2" src="{second}">'
        "</a>"
        "</p></body></html>"
    )
    (posts / "doc.html").write_text(html, encoding="utf-8")

    server, port = _start_server(base)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{port}/posts/raw/Posts%202026/doc.html", wait_until="domcontentloaded")
            page.wait_for_selector("#dg-overlay")
            page.locator('img[alt="image 2"]').click()
            page.wait_for_function(
                """
                (expectedSrc) => {
                  const overlayImg = document.querySelector('#image-viewer-overlay img');
                  return !!overlayImg && overlayImg.getAttribute('src') === expectedSrc;
                }
                """,
                arg=second,
            )
            page.wait_for_function(
                """
                (expectedHref) => {
                  const link = document.querySelector('a.image-zoom');
                  return !!link && link.getAttribute('href') === expectedHref;
                }
                """,
                arg=first,
            )
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
