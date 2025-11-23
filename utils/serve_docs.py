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
- Bump y publicación son estados independientes; se puede (des)bump aunque esté
  publicado.

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
import stat
from typing import Optional

# Paths relativos al repo (para publicar)
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
DEPLOY_SCRIPT = os.getenv(
    "DEPLOY_SCRIPT",
    os.path.join(REPO_ROOT, "web", "deploy.sh"),
)
PUBLIC_READS_URL_BASE = os.getenv("PUBLIC_READS_URL_BASE", "")
PUBLIC_READS_DIR = os.getenv(
    "PUBLIC_READS_DIR",
    os.path.join(REPO_ROOT, "web", "public", "read"),
)
STATIC_DIR = os.path.join(SCRIPT_DIR, "static")

# --------- CONFIG ---------
PORT = int(os.getenv("PORT", "8000"))
SERVE_DIR = os.getenv("SERVE_DIR", "/Users/domingo/⭐️ Documentación")
BUMP_YEARS = int(os.getenv("BUMP_YEARS", "100"))
 

# Contador de la sesión (equivale al "counter" del AppleScript en un run)
_BUMP_COUNTER = 0
_LAST_BASE_EPOCH: Optional[int] = None  # recuerda la última base para reiniciar el contador


# --------- STATIC ASSETS (externos) ---------

def _load_static_bytes(filename: str) -> bytes:
    path = os.path.join(STATIC_DIR, filename)
    with open(path, "rb") as fh:
        return fh.read()


OVERLAY_CSS = _load_static_bytes("overlay.css")
OVERLAY_JS = _load_static_bytes("overlay.js")
INDEX_JS = _load_static_bytes("index.js")


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
    """Formato estilo /read/: YYYY-Mon-DD HH:MM (mes en inglés abreviado)."""
    t = time.localtime(ts)
    MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    return f"{t.tm_year}-{MONTHS[t.tm_mon-1]}-{t.tm_mday:02d} {t.tm_hour:02d}:{t.tm_min:02d}"


def _entry_classes(bumped: bool, published: bool) -> str:
    classes: list[str] = []
    if bumped:
        classes.append("dg-bump")
    if published:
        classes.append("dg-pub")
    return f" class=\"{' '.join(classes)}\"" if classes else ""


def _is_published_filename(name: str) -> bool:
    try:
        if name.lower().endswith((".html", ".htm", ".pdf")):
            return os.path.exists(os.path.join(PUBLIC_READS_DIR, name))
    except Exception:
        return False
    return False


def _pdf_actions_html(rel_from_root: str, bumped: bool, published: bool) -> str:
    actions: list[str] = []
    if bumped:
        actions.append(
            f"<a href='#' class='dg-act' data-dg-act='unbump_now' data-dg-path='{html.escape(rel_from_root)}'>Unbump</a>"
        )
    else:
        actions.append(
            f"<a href='#' class='dg-act' data-dg-act='bump' data-dg-path='{html.escape(rel_from_root)}'>Bump</a>"
        )
    if published:
        actions.append(
            f"<a href='#' class='dg-act' data-dg-act='unpublish' data-dg-path='{html.escape(rel_from_root)}'>Despublicar</a>"
        )
    elif bumped:
        actions.append(
            f"<a href='#' class='dg-act' data-dg-act='publish' data-dg-path='{html.escape(rel_from_root)}'>Publicar</a>"
        )
    if not actions:
        return ""
    return f"<span class='dg-actions'>{' '.join(actions)}</span>"


def _render_list_entry(entry: os.DirEntry[str], now: float, st: os.stat_result) -> str | None:
    mtime = st.st_mtime
    bumped = mtime > now
    published = _is_published_filename(entry.name)
    is_dir = stat.S_ISDIR(st.st_mode)
    display_name = entry.name + ("/" if is_dir else "")
    link = urllib.parse.quote(display_name)
    rel_from_root = os.path.relpath(entry.path, SERVE_DIR)
    type_icon = ""
    if not is_dir:
        lowered = entry.name.lower()
        if lowered.endswith((".html", ".htm")):
            type_icon = "📄 "
        elif lowered.endswith(".pdf"):
            type_icon = "📕 "
        else:
            return None  # ignoramos ficheros que no sean HTML/PDF

    prefix = ("🔥 " if bumped else "") + ("🟢 " if published else "") + type_icon
    date_html = f"<span class='dg-date'> — {fmt_ts(mtime)}</span>"
    actions_html = ""
    if entry.name.lower().endswith(".pdf"):
        actions_html = _pdf_actions_html(rel_from_root, bumped, published)
    cls_attr = _entry_classes(bumped, published)
    return f"<li{cls_attr}><span>{prefix}<a href=\"{link}\">{html.escape(display_name)}</a>{date_html}</span>{actions_html}</li>"


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
    """Obtiene la base futura (ahora + BUMP_YEARS años).

    Antes se cacheaba para toda la sesión, pero ahora se recalcula en
    cada acceso para que el bump siempre parta del momento actual.
    """
    return _apple_like_base_epoch()


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
    """Calcula el mtime futuro sumando años respecto al momento del bump."""
    global _BUMP_COUNTER, _LAST_BASE_EPOCH
    base_epoch = base_epoch_cached()
    if base_epoch != _LAST_BASE_EPOCH:
        _LAST_BASE_EPOCH = base_epoch
        _BUMP_COUNTER = 0
    _BUMP_COUNTER += 1
    return base_epoch + _BUMP_COUNTER


 


def inject_overlay(html_text: str, rel_fs: str, bumped: bool, published: bool) -> bytes:
    tags = (
        '<link rel="stylesheet" href="/__overlay.css">'
        f'<script src="/__overlay.js" defer data-path="{html.escape(rel_fs)}" '
        f'data-bumped="{"1" if bumped else "0"}" '
        f' data-published="{"1" if published else "0"}"'
        f' data-public-base="{html.escape(PUBLIC_READS_URL_BASE)}"></script>'
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
            if action in ("bump", "unbump_now"):
                st = os.stat(abs_path)
                atime = st.st_atime  # conservamos atime

                if action == "bump":
                    mtime = compute_bump_mtime()
                else:  # unbump_now
                    cre = get_creation_epoch(abs_path)
                    if cre is not None:
                        mtime = cre
                    else:
                        mtime = st.st_mtime if st.st_mtime <= time.time() else time.time() - 60

                os.utime(abs_path, (atime, mtime))
                self._send_bytes(b'{"ok":true}', "application/json; charset=utf-8")
                return

            if action == "delete":
                if os.path.isdir(abs_path):
                    self.send_error(400, "No se pueden borrar directorios")
                    return
                try:
                    os.remove(abs_path)
                except FileNotFoundError:
                    self.send_error(404, "File not found")
                    return
                except Exception as e:
                    self.send_error(500, f"No se pudo borrar: {e}")
                    return

                # Borrar Markdown asociado (mismo nombre)
                try:
                    stem, _ = os.path.splitext(abs_path)
                    md_path = f"{stem}.md"
                    if os.path.isfile(md_path):
                        os.remove(md_path)
                except Exception as e:
                    self.send_error(500, f"No se pudo borrar Markdown asociado: {e}")
                    return

                # También eliminar copia publicada si existe
                try:
                    pub_path = os.path.join(PUBLIC_READS_DIR, os.path.basename(abs_path))
                    if os.path.isfile(pub_path):
                        os.remove(pub_path)
                except Exception as e:
                    self.send_error(500, f"No se pudo borrar copia pública: {e}")
                    return

                self._send_bytes(b'{"ok":true}', "application/json; charset=utf-8")
                return

            if action == "publish":
                # Requiere que el fichero esté bumped (defensa extra)
                try:
                    st_src = os.stat(abs_path)
                except Exception as e:
                    self.send_error(500, f"No se pudo leer el fichero: {e}")
                    return
                if not is_bumped(st_src.st_mtime):
                    self.send_error(400, "No publicado: el fichero no está bumped")
                    return
                # 1) Copiar a directorio público READS siempre
                if not os.path.isdir(PUBLIC_READS_DIR):
                    try:
                        os.makedirs(PUBLIC_READS_DIR, exist_ok=True)
                    except Exception as e:
                        self.send_error(500, f"No se pudo crear destino: {e}")
                        return
                dst_dir = PUBLIC_READS_DIR
                try:
                    os.makedirs(dst_dir, exist_ok=True)
                except Exception as e:
                    self.send_error(500, f"No se pudo crear destino: {e}")
                    return

                dst_path = os.path.join(dst_dir, os.path.basename(abs_path))
                try:
                    src_stat = st_src
                    name_low = os.path.basename(abs_path).lower()
                    if name_low.endswith((".html", ".htm")):
                        # Inyectar script base de artículos antes de </head> si no está presente
                        with open(abs_path, 'r', encoding='utf-8', errors='ignore') as src:
                            text = src.read()
                        if "/read/article.js" not in text:
                            low = text.lower()
                            idx = low.rfind("</head>")
                            if idx != -1:
                                text = text[:idx] + "<script src='/read/article.js' defer></script>" + text[idx:]
                        with open(dst_path, 'w', encoding='utf-8') as dst:
                            dst.write(text)
                    else:
                        # Copia binaria para otros tipos (p.ej. PDFs)
                        with open(abs_path, 'rb') as src, open(dst_path, 'wb') as dst:
                            while True:
                                chunk = src.read(1024 * 1024)
                                if not chunk:
                                    break
                                dst.write(chunk)
                    # Preservar tiempos (especialmente mtime para mantener bumps)
                    try:
                        os.utime(dst_path, (src_stat.st_atime, src_stat.st_mtime))
                    except Exception:
                        pass
                except Exception as e:
                    self.send_error(500, f"Error copiando: {e}")
                    return

                # 2) Lanzar deploy
                if not os.path.isfile(DEPLOY_SCRIPT) or not os.access(DEPLOY_SCRIPT, os.X_OK):
                    self.send_error(500, f"Deploy no disponible: {DEPLOY_SCRIPT}")
                    return

                try:
                    # heredamos entorno (requiere REMOTE_USER/REMOTE_HOST configurados)
                    subprocess.run([DEPLOY_SCRIPT], check=True)
                except subprocess.CalledProcessError as e:
                    self.send_error(500, f"Fallo en deploy ({e.returncode})")
                    return

                self._send_bytes(b'{"ok":true}', "application/json; charset=utf-8")
                return

            if action == "unpublish":
                # Elimina el archivo del directorio público READS y despliega
                removed = False
                try:
                    dst_path = os.path.join(PUBLIC_READS_DIR, os.path.basename(abs_path))
                    if os.path.exists(dst_path):
                        os.remove(dst_path)
                        removed = True
                except Exception as e:
                    self.send_error(500, f"Error despublicando: {e}")
                    return

                # Lanzar deploy
                if not os.path.isfile(DEPLOY_SCRIPT) or not os.access(DEPLOY_SCRIPT, os.X_OK):
                    self.send_error(500, f"Deploy no disponible: {DEPLOY_SCRIPT}")
                    return
                try:
                    subprocess.run([DEPLOY_SCRIPT], check=True)
                except subprocess.CalledProcessError as e:
                    self.send_error(500, f"Fallo en deploy ({e.returncode})")
                    return

                self._send_bytes(b'{"ok":true}', "application/json; charset=utf-8")
                return

            self.send_error(400, "Unknown action")
        except OSError as e:
            self.send_error(500, str(e))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        # Assets del overlay (externos para evitar CSP inline)
        if parsed.path == "/__overlay.css":
            return self._send_bytes(OVERLAY_CSS, "text/css; charset=utf-8")

        if parsed.path == "/__overlay.js":
            return self._send_bytes(OVERLAY_JS, "application/javascript; charset=utf-8")
        if parsed.path == "/__index.js":
            return self._send_bytes(INDEX_JS, "application/javascript; charset=utf-8")

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
                # Publicado si ya existe un archivo con el mismo nombre en read/
                published = False
                try:
                    published = os.path.exists(os.path.join(PUBLIC_READS_DIR, os.path.basename(abs_path)))
                except Exception:
                    published = False
                out = inject_overlay(text, rel_fs, is_bumped(st.st_mtime), published)
                return self._send_bytes(out, "text/html; charset=utf-8", {"X-Overlay": "1"})

        # Resto: comportamiento normal
        return super().do_GET()

    # --------- DIRECTORY LISTING ----------
    def list_directory(self, path):
        try:
            entries: list[tuple[float, os.DirEntry[str], os.stat_result]] = []
            with os.scandir(path) as it:
                for entry in it:
                    try:
                        st = entry.stat()
                    except FileNotFoundError:
                        continue
                    entries.append((st.st_mtime, entry, st))
        except OSError:
            self.send_error(404, "No permission to list directory")
            return None

        entries.sort(key=lambda item: item[0], reverse=True)

        displaypath = urllib.parse.unquote(self.path)
        head_html = (
            f"<html><head><meta charset='utf-8'><title>Index of {html.escape(displaypath)}</title>"
            "<style>"
            "body{margin:14px 18px;font:14px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;color:#222}"
            "h2{margin:6px 0 10px;font-weight:600}"
            "hr{border:0;border-top:1px solid #e6e6e6;margin:8px 0}"
            "ul.dg-index{list-style:none;padding-left:0}"
            ".dg-index li{padding:2px 6px;border-radius:6px;margin:2px 0;display:flex;justify-content:space-between;align-items:center}"
            ".dg-bump{background:#fff6e5}"
            ".dg-pub a{color:#0a7;font-weight:600}"
            ".dg-legend{color:#666;font:13px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;margin-bottom:6px}"
            ".dg-actions{display:inline-flex;gap:6px}"
            ".dg-actions button, .dg-actions a{padding:2px 6px;border:1px solid #ccc;border-radius:6px;background:#f7f7f7;text-decoration:none;color:#333;font:12px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial}"
            ".dg-actions button[disabled], .dg-actions a[disabled]{opacity:.6;pointer-events:none}"
            ".dg-date{color:#666;margin-left:10px;white-space:nowrap}"
            "</style>"
            "<script src='/__index.js' defer></script>"
            "</head><body>"
        )

        rows: list[str] = [head_html, f"<h2>Index of {html.escape(displaypath)}</h2>"]
        rows.append("<div class='dg-legend'>🔥 bumped · 🟢 publicado</div><hr><ul class='dg-index'>")

        if displaypath != "/":
            parent = os.path.dirname(displaypath.rstrip("/"))
            rows.append(f'<li><a href="{parent or "/"}">../</a></li>')

        now = time.time()
        for _, entry, st in entries:
            rendered = _render_list_entry(entry, now, st)
            if rendered:
                rows.append(rendered)

        rows.append("</ul><hr></body></html>")
        encoded = "\n".join(rows).encode("utf-8", "surrogateescape")
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
