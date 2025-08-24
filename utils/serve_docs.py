#!/usr/bin/env python3
"""
Servidor local de HTML/PDF con "bump" desde la propia página leída.

- Índice ordenado por mtime desc y resaltado de ficheros bump (🔥 + fondo).
- Overlay en páginas .html para hacer Bump/Unbump del fichero abierto.
- Sin botones en el índice.
- CSS/JS del overlay servidos como archivos externos (evita bloqueos CSP).
- "Bump" calcado a AppleScript:
    baseEpoch = /bin/date -v+{BUMP_YEARS}y +%s
    mtime := baseEpoch + i (i empieza en 1 y crece en cada bump de la sesión)
- Botón "inteligente": solo Bump o Unbump según mtime > now.
- Atajos: b / u / l y ⌘B / ⌘U (o Ctrl+B / Ctrl+U).
  · 'l' navega al listado (carpeta padre) del archivo actual.

Variables de entorno:
  PORT        (por defecto 8000)
  SERVE_DIR   (por defecto "/Users/domingo/⭐️ Documentación")
  BUMP_YEARS  (por defecto 100)
"""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
import time
import html
import urllib.parse
from datetime import datetime
import subprocess
import calendar as _cal
from typing import Optional

# --------- CONFIG ---------
PORT = int(os.getenv("PORT", "8000"))
SERVE_DIR = os.getenv("SERVE_DIR", "/Users/domingo/⭐️ Documentación")
BUMP_YEARS = int(os.getenv("BUMP_YEARS", "100"))

# Contador de la sesión (equivale al "counter" del AppleScript en un run)
_BUMP_COUNTER = 0
_BASE_EPOCH: Optional[int] = None  # cacheado en primer uso


# --------- STATIC ASSETS (externos) ---------
OVERLAY_CSS = (
    "#dg-overlay{position:fixed;z-index:2147483647;right:12px;bottom:12px;"
    "background:#fff;border:1px solid #ddd;border-radius:12px;"
    "box-shadow:0 4px 18px rgba(0,0,0,.1);padding:8px 10px;"
    "font:13px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;"
    "display:flex;gap:8px;align-items:center}"
    "#dg-overlay button{padding:6px 10px;border:1px solid #ccc;"
    "border-radius:8px;background:#f9f9f9;cursor:pointer}"
    "#dg-overlay .meta{color:#666;margin-left:6px}"
    "#dg-overlay .ok{color:#0a0}#dg-overlay .err{color:#a00}"
    "#dg-overlay a{text-decoration:none;color:#06c}"
).encode("utf-8")

OVERLAY_JS = (
    "(function(){\n"
    "  const script = document.currentScript;\n"
    "  const rel = script.dataset.path || '';\n"
    "  let bumped = (script.dataset.bumped === '1');\n"
    "  function el(tag, attrs, text){\n"
    "    const e = document.createElement(tag);\n"
    "    if(attrs){ for(const k in attrs){ e.setAttribute(k, attrs[k]); } }\n"
    "    if(text){ e.textContent = text; }\n"
    "    return e;\n"
    "  }\n"
    "  async function call(action){\n"
    "    const body = new URLSearchParams({path: rel, action}).toString();\n"
    "    const res = await fetch('/__bump', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body});\n"
    "    return res.ok;\n"
    "  }\n"
    "  function goList(){\n"
    "    const p = window.location.pathname;\n"
    "    const parent = p.endsWith('/') ? p : p.substring(0, p.lastIndexOf('/') + 1);\n"
    "    window.location.href = parent || '/';\n"
    "  }\n"
    "  function render(){\n"
    "    bar.innerHTML = '';\n"
    "    bar.appendChild(el('strong', null, '📄 ' + rel));\n"
    "    const btn = el('button', null, bumped ? 'Unbump' : 'Bump');\n"
    "    btn.addEventListener('click', async ()=>{\n"
    "      const ok = await call(bumped ? 'unbump_now' : 'bump');\n"
    "      msg.textContent = ok ? '✓ hecho' : '× error'; msg.className = ok ? 'meta ok' : 'meta err';\n"
    "      if(ok){ bumped = !bumped; render(); }\n"
    "    });\n"
    "    const raw = el('a', {href:'?raw=1', title:'Ver sin overlay'}, 'raw');\n"
    "    bar.appendChild(btn); bar.appendChild(raw); bar.appendChild(msg);\n"
    "  }\n"
    "  function isEditingTarget(t){ return t && (t.tagName==='INPUT' || t.tagName==='TEXTAREA' || t.isContentEditable); }\n"
    "  const bar = el('div', {id:'dg-overlay'});\n"
    "  const msg = el('span', {class:'meta', id:'dg-msg'}, '');\n"
    "  document.addEventListener('keydown', async (e)=>{\n"
    "    if(isEditingTarget(document.activeElement)) return;\n"
    "    const k = (e.key || '').toLowerCase();\n"
    "    if(k==='b'){\n"
    "      e.preventDefault(); const ok = await call('bump'); if(ok){ bumped=true; render(); msg.textContent='✓ hecho'; msg.className='meta ok'; }\n"
    "    }\n"
    "    if(k==='u'){\n"
    "      e.preventDefault(); const ok = await call('unbump_now'); if(ok){ bumped=false; render(); msg.textContent='✓ hecho'; msg.className='meta ok'; }\n"
    "    }\n"
    "    if(k==='l' && !e.metaKey && !e.ctrlKey && !e.altKey){ e.preventDefault(); goList(); }\n"
    "  });\n"
    "  document.addEventListener('DOMContentLoaded', ()=>{ document.body.appendChild(bar); render(); });\n"
    "})();\n"
).encode("utf-8")


# --------- HELPERS ---------
def safe_join(rel_path: str) -> str | None:
    """Asegura que la ruta objetivo esté dentro de SERVE_DIR (evita path traversal)."""
    rel_path = rel_path.lstrip("/")
    base = os.path.normpath(SERVE_DIR)
    target = os.path.normpath(os.path.join(base, rel_path))
    if target == base or target.startswith(base + os.sep):
        return target
    return None


def is_bumped(ts: float) -> bool:
    return ts > time.time()


def fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _apple_like_base_epoch() -> int:
    """Epoch de (ahora + BUMP_YEARS años), imitando `/bin/date -v+{BUMP_YEARS}y +%s`."""
    try:
        cmd = ["/bin/date", f"-v+{BUMP_YEARS}y", "+%s"]
        out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()
        return int(out)
    except Exception:
        # Fallback: sumar años respetando calendario
        now = datetime.now()
        tgt_year = now.year + BUMP_YEARS
        y, m, d = tgt_year, now.month, now.day
        last_day = _cal.monthrange(y, m)[1]
        if d > last_day:
            d = last_day
        dt2 = datetime(y, m, d, now.hour, now.minute, now.second, now.microsecond)
        return int(time.mktime(dt2.timetuple()))


def base_epoch_cached() -> int:
    global _BASE_EPOCH
    if _BASE_EPOCH is None:
        _BASE_EPOCH = _apple_like_base_epoch()
    return _BASE_EPOCH


def get_creation_epoch(abs_path: str) -> int | None:
    """Intenta obtener fecha de creación (APFS/Spotlight)."""
    try:
        st = os.stat(abs_path)
        birth = getattr(st, "st_birthtime", None)
        if birth and birth > 0:
            return int(birth)
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["/usr/bin/mdls", "-raw", "-name", "kMDItemFSCreationDate", abs_path],
            check=True, capture_output=True, text=True
        ).stdout.strip()
        if out and out.lower() != "(null)":
            try:
                dt = datetime.strptime(out, "%Y-%m-%d %H:%M:%S %z")
                return int(dt.timestamp())
            except Exception:
                for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
                    try:
                        dt = datetime.strptime(out, fmt)
                        if dt.tzinfo is None:
                            return int(time.mktime(dt.timetuple()))
                        return int(dt.timestamp())
                    except Exception:
                        continue
    except Exception:
        pass
    return None


def compute_bump_mtime() -> int:
    """
    Emula el AppleScript:
      baseEpoch = date -v+{BUMP_YEARS}y +%s (cacheado)
      i = i + 1
      mtime = baseEpoch + i
    """
    global _BUMP_COUNTER
    _BUMP_COUNTER += 1
    return base_epoch_cached() + _BUMP_COUNTER


def inject_overlay(html_text: str, rel_fs: str, bumped: bool) -> bytes:
    tags = (
        '<link rel="stylesheet" href="/__overlay.css">'
        f'<script src="/__overlay.js" defer data-path="{html.escape(rel_fs)}" '
        f'data-bumped="{"1" if bumped else "0"}"></script>'
    )
    low = html_text.lower()
    idx = low.rfind("</body>")
    injected = (html_text + tags) if idx == -1 else (html_text[:idx] + tags + html_text[idx:])
    return injected.encode("utf-8", "surrogateescape")


# --------- REQUEST HANDLER ---------
class HTMLOnlyRequestHandler(SimpleHTTPRequestHandler):
    def _send_bytes(self, data: bytes, content_type: str, extra_headers: dict | None = None):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    # --------- ROUTES ----------
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/__bump":
            self.send_error(404, "Unknown POST")
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", "surrogateescape")
        data = urllib.parse.parse_qs(body)
        rel = urllib.parse.unquote(data.get("path", [""])[0])
        action = data.get("action", ["bump"])[0]
        abs_path = safe_join(rel)
        if not abs_path or not os.path.exists(abs_path):
            self.send_error(404, "File not found")
            return

        try:
            st = os.stat(abs_path)
            atime = st.st_atime  # conservamos atime

            if action == "bump":
                mtime = compute_bump_mtime()
            elif action == "unbump_now":
                cre = get_creation_epoch(abs_path)
                if cre is not None:
                    mtime = cre
                else:
                    mtime = st.st_mtime if st.st_mtime <= time.time() else time.time() - 60
            else:
                self.send_error(400, "Unknown action")
                return

            os.utime(abs_path, (atime, mtime))
            self._send_bytes(b'{"ok":true}', "application/json; charset=utf-8")
        except OSError as e:
            self.send_error(500, str(e))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        # Assets del overlay (externos para evitar CSP inline)
        if parsed.path == "/__overlay.css":
            return self._send_bytes(OVERLAY_CSS, "text/css; charset=utf-8")

        if parsed.path == "/__overlay.js":
            return self._send_bytes(OVERLAY_JS, "application/javascript; charset=utf-8")

        # Páginas HTML: inyectar overlay salvo ?raw=1
        rel_path = parsed.path.lstrip("/")
        qs = urllib.parse.parse_qs(parsed.query)
        raw = qs.get("raw", ["0"])[0] == "1"

        if rel_path and rel_path.lower().endswith(".html") and not raw:
            rel_fs = urllib.parse.unquote(rel_path)
            abs_path = safe_join(rel_fs)
            if abs_path and os.path.exists(abs_path):
                try:
                    with open(abs_path, "rb") as f:
                        original = f.read()
                    text = original.decode("utf-8", "surrogateescape")
                except Exception:
                    return super().do_GET()

                st = os.stat(abs_path)
                out = inject_overlay(text, rel_fs, is_bumped(st.st_mtime))
                return self._send_bytes(out, "text/html; charset=utf-8", {"X-Overlay": "1"})

        # Resto: comportamiento normal
        return super().do_GET()

    # --------- DIRECTORY LISTING ----------
    def list_directory(self, path):
        try:
            with os.scandir(path) as it:
                entries = [e for e in it]
        except OSError:
            self.send_error(404, "No permission to list directory")
            return None

        # Ordenar por mtime desc
        entries.sort(key=lambda e: e.stat().st_mtime, reverse=True)

        r = []
        displaypath = urllib.parse.unquote(self.path)
        r.append(f"<html><head><meta charset='utf-8'><title>Index of {html.escape(displaypath)}</title></head><body>")
        r.append(f"<h2>Index of {html.escape(displaypath)}</h2><hr><ul>")

        if displaypath != "/":
            parent = os.path.dirname(displaypath.rstrip("/"))
            r.append(f'<li><a href="{parent or "/"}">../</a></li>')

        now = time.time()
        for e in entries:
            name = e.name
            fullname = e.path
            try:
                mtime = e.stat().st_mtime
            except FileNotFoundError:
                continue
            bumped = (mtime > now)
            prefix = '🔥 ' if bumped else ''
            is_dir = e.is_dir()
            disp = name + ("/" if is_dir else "")
            link = urllib.parse.quote(name + ("/" if is_dir else ""))
            if is_dir:
                r.append(f'<li>{prefix}<a href="{link}">{html.escape(disp)}</a></li>')
            elif name.lower().endswith(".html"):
                r.append(f'<li>{prefix}📄 <a href="{link}">{html.escape(disp)}</a></li>')
            elif name.lower().endswith(".pdf"):
                r.append(f'<li>{prefix}📕 <a href="{link}">{html.escape(disp)}</a></li>')

        r.append("</ul><hr></body></html>")
        encoded = "\n".join(r).encode("utf-8", "surrogateescape")
        self._send_bytes(encoded, "text/html; charset=utf-8")
        return None

    # --------- PATH MAP ----------
    def translate_path(self, path):
        path = urllib.parse.unquote(urllib.parse.urlparse(path).path)
        if path == "/":
            return SERVE_DIR
        safe = safe_join(path)
        return safe if safe else SERVE_DIR


def main():
    os.chdir(SERVE_DIR)
    with ThreadingHTTPServer(("", PORT), HTMLOnlyRequestHandler) as httpd:
        print(f"Serving ONLY .html/.pdf (and folders) from: {SERVE_DIR}")
        print(f"Access at: http://localhost:{PORT}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
