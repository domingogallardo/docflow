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
    "#dg-overlay button[disabled]{opacity:.6;cursor:default}"
    "#dg-overlay .meta{color:#666;margin-left:6px}"
    "#dg-overlay .ok{color:#0a0}#dg-overlay .err{color:#a00}"
    "#dg-overlay a{text-decoration:none;color:#06c}"
    "#dg-toast{position:fixed;z-index:2147483647;right:12px;bottom:60px;"
    "background:#0a0;color:#fff;border-radius:10px;padding:8px 12px;"
    "box-shadow:0 6px 20px rgba(0,0,0,.15);opacity:0;transform:translateY(8px);"
    "transition:opacity .15s ease, transform .15s ease;"
    "font:13px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;}"
    "#dg-toast.show{opacity:1;transform:translateY(0)}"
    "#dg-toast.err{background:#a00}#dg-toast.ok{background:#0a0}"
    "#dg-toast a{color:#fff;text-decoration:underline;margin-left:8px}"
).encode("utf-8")

OVERLAY_JS = (
    "(function(){\n"
    "  const script = document.currentScript;\n"
    "  const rel = script.dataset.path || '';\n"
    "  let bumped = (script.dataset.bumped === '1');\n"
    "  let published = (script.dataset.published === '1');\n"
    "  let publishing = false;\n"
    "  let unpublishing = false;\n"
    "  let processing = false;\n"
    "  const publicBase = script.dataset.publicBase || '';\n"
    "  function el(tag, attrs, text){\n"
    "    const e = document.createElement(tag);\n"
    "    if(attrs){ for(const k in attrs){ e.setAttribute(k, attrs[k]); } }\n"
    "    if(text){ e.textContent = text; }\n"
    "    return e;\n"
    "  }\n"
    "  function toast(kind, text, href){\n"
    "    let t = document.getElementById('dg-toast');\n"
    "    if(!t){ t = el('div', {id:'dg-toast'}, ''); document.body.appendChild(t); }\n"
    "    t.className = kind ? kind + ' show' : 'show';\n"
    "    t.textContent = text || '';\n"
    "    if(href){ const a = el('a', {href, target:'_blank', rel:'noopener'}, 'Ver'); t.appendChild(a); }\n"
    "    clearTimeout(window.__dg_toast_timer);\n"
    "    window.__dg_toast_timer = setTimeout(()=>{ t.classList.remove('show'); }, 2200);\n"
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
    "  async function publish(){\n"
    "    if(publishing || !bumped || published) return;\n"
    "    publishing = true; render(); msg.textContent = '⏳ publicando…'; msg.className = 'meta';\n"
    "    const ok = await call('publish');\n"
    "    msg.textContent = ok ? '✓ publicado' : '× error';\n"
    "    msg.className = ok ? 'meta ok' : 'meta err';\n"
    "    if(ok){\n"
    "      published = true; render();\n"
    "      const fname = rel.split('/').pop();\n"
    "      const base = publicBase ? (publicBase.endsWith('/') ? publicBase : publicBase + '/') : '';\n"
    "      const url = base ? (base + encodeURIComponent(fname)) : '';\n"
    "      toast('ok', 'Publicado', url);\n"
    "    } else {\n"
    "      publishing = false; render();\n"
    "      toast('err', 'Error publicando');\n"
    "    }\n"
    "  }\n"
    "  async function processed(){\n"
    "    if(processing || !bumped || !published) return;\n"
    "    processing = true; render(); msg.textContent = 'procesando…';\n"
    "    const ok = await call('processed');\n"
    "    msg.textContent = ok ? '✓ procesado' : '× error';\n"
    "    msg.className = ok ? 'meta ok' : 'meta err';\n"
    "    if(ok){\n"
    "      bumped = false; processing = false; render();\n"
    "      toast('ok', 'Procesado');\n"
    "    } else {\n"
    "      processing = false; render();\n"
    "      toast('err', 'Error en procesado');\n"
    "    }\n"
    "  }\n"
    "  async function unpublish(){\n"
    "    if(unpublishing || !published) return;\n"
    "    unpublishing = true; render(); msg.textContent = '⏳ despublicando…'; msg.className = 'meta';\n"
    "    const ok = await call('unpublish');\n"
    "    msg.textContent = ok ? '✓ despublicado' : '× error';\n"
    "    msg.className = ok ? 'meta ok' : 'meta err';\n"
    "    if(ok){\n"
    "      published = false; unpublishing = false; render();\n"
    "      toast('ok', 'Despublicado');\n"
    "    } else {\n"
    "      unpublishing = false; render();\n"
    "      toast('err', 'Error despublicando');\n"
    "    }\n"
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
    "    bar.appendChild(btn);\n"
    "    if(bumped && !published){\n"
    "      const pub = el('button', null, 'Publicar');\n"
    "      pub.title = 'Copiar a /web/public/read y desplegar';\n"
    "      if(publishing){ pub.textContent = 'Publicando…'; pub.setAttribute('disabled',''); }\n"
    "      pub.addEventListener('click', publish);\n"
    "      bar.appendChild(pub);\n"
    "    }\n"
    "    if(published){\n"
    "      const unp = el('button', null, 'Despublicar');\n"
    "      unp.title = 'Eliminar de /web/public/read y desplegar';\n"
    "      if(unpublishing){ unp.textContent = 'Despublicando…'; unp.setAttribute('disabled',''); }\n"
    "      unp.addEventListener('click', unpublish);\n"
    "      bar.appendChild(unp);\n"
    "      if(bumped){\n"
    "        const done = el('button', null, 'Procesado');\n"
    "        done.title = 'Unbump + añadir a read_posts.md + desplegar';\n"
    "        if(processing){ done.textContent = 'Procesando…'; done.setAttribute('disabled',''); }\n"
    "        done.addEventListener('click', processed);\n"
    "        bar.appendChild(done);\n"
    "      }\n"
    "    }\n"
    "    const raw = el('a', {href:'?raw=1', title:'Ver sin overlay'}, 'raw');\n"
    "    bar.appendChild(raw); bar.appendChild(msg);\n"
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
    "    if(k==='p' && bumped && !published && !publishing){ e.preventDefault(); publish(); }\n"
    "    if(k==='d' && published && !unpublishing){ e.preventDefault(); unpublish(); }\n"
    "    if(k==='x' && bumped && published && !processing){ e.preventDefault(); processed(); }\n"
    "  });\n"
    "  document.addEventListener('DOMContentLoaded', ()=>{ document.body.appendChild(bar); render(); });\n"
    "})();\n"
).encode("utf-8")

# JS para acciones rápidas en el índice (PDFs: bump/publicar/despublicar)
INDEX_JS = (
    "(()=>{\n"
    "  function send(action, rel, target){\n"
    "    const params = {path: rel, action};\n"
    "    if(target){ params.target = target; }\n"
    "    const body = new URLSearchParams(params).toString();\n"
    "    return fetch('/__bump', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body});\n"
    "  }\n"
    "  document.addEventListener('click', (e)=>{\n"
    "    const a = e.target.closest('[data-dg-act]');\n"
    "    if(!a) return;\n"
    "    e.preventDefault();\n"
    "    const action = a.getAttribute('data-dg-act');\n"
    "    const rel = a.getAttribute('data-dg-path');\n"
    "    const tgt = a.getAttribute('data-dg-target');\n"
    "    if(!action || !rel) return;\n"
    "    a.textContent = '…'; a.setAttribute('disabled','');\n"
    "    send(action, rel, tgt).then(r=>{ if(r.ok){ location.reload(); } else { alert('Error'); a.removeAttribute('disabled'); } });\n"
    "  });\n"
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
    """Formato estilo /read/: YYYY-Mon-DD HH:MM (mes en inglés abreviado)."""
    t = time.localtime(ts)
    MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    return f"{t.tm_year}-{MONTHS[t.tm_mon-1]}-{t.tm_mday:02d} {t.tm_hour:02d}:{t.tm_min:02d}"


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

            if action == "processed":
                # Validaciones: debe estar publicado y bumped
                name = os.path.basename(abs_path)
                is_published = os.path.exists(os.path.join(PUBLIC_READS_DIR, name))
                st = os.stat(abs_path)
                if not is_published or not is_bumped(st.st_mtime):
                    self.send_error(400, "Requiere 'bumped' y 'publicado'")
                    return

                # Unbump (como unbump_now)
                atime = st.st_atime
                cre = get_creation_epoch(abs_path)
                if cre is not None:
                    mtime = cre
                else:
                    mtime = st.st_mtime if st.st_mtime <= time.time() else time.time() - 60
                os.utime(abs_path, (atime, int(mtime)))

                # Añadir a read_posts.md (prepend idempotente)
                try:
                    md_path = os.path.join(PUBLIC_READS_DIR, "read_posts.md")
                    # Cargar existentes normalizados (quitando viñetas)
                    existing: list[str] = []
                    if os.path.isfile(md_path):
                        with open(md_path, "r", encoding="utf-8") as f:
                            for raw in f:
                                s = raw.strip()
                                if not s or s.startswith('#'):
                                    continue
                                if s.startswith('- ') or s.startswith('* '):
                                    s = s[2:].strip()
                                existing.append(s)
                    if name not in existing:
                        tmp = md_path + ".tmp"
                        os.makedirs(os.path.dirname(md_path), exist_ok=True)
                        with open(tmp, "w", encoding="utf-8") as w:
                            w.write(f"- {name}\n")
                            if os.path.isfile(md_path):
                                with open(md_path, "r", encoding="utf-8") as r:
                                    w.write(r.read())
                        os.replace(tmp, md_path)
                except Exception as e:
                    self.send_error(500, f"Error actualizando read_posts.md: {e}")
                    return

                # Desplegar para regenerar read.html en el servidor
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
            with os.scandir(path) as it:
                entries = [e for e in it]
        except OSError:
            self.send_error(404, "No permission to list directory")
            return None

        # Ordenar por mtime desc
        entries.sort(key=lambda e: e.stat().st_mtime, reverse=True)

        r = []
        displaypath = urllib.parse.unquote(self.path)
        r.append(
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
        r.append(f"<h2>Index of {html.escape(displaypath)}</h2>")
        r.append("<div class='dg-legend'>🔥 bumped · 🟢 publicado</div><hr><ul class='dg-index'>")

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
            # Consideramos publicado si existe en READS
            published = False
            try:
                if name.lower().endswith((".html", ".htm", ".pdf")):
                    if os.path.exists(os.path.join(PUBLIC_READS_DIR, name)):
                        published = True
            except Exception:
                published = False
            icon_pub = '🟢 ' if published else ''
            prefix = ("🔥 " if bumped else "") + icon_pub
            is_dir = e.is_dir()
            disp = name + ("/" if is_dir else "")
            link = urllib.parse.quote(name + ("/" if is_dir else ""))
            li_classes = []
            if bumped:
                li_classes.append("dg-bump")
            if published:
                li_classes.append("dg-pub")
            cls = f" class=\"{' '.join(li_classes)}\"" if li_classes else ""
            # Acciones para PDFs (no podemos inyectar overlay en visor)
            actions_html = ""
            rel_from_root = os.path.relpath(fullname, SERVE_DIR)
            if name.lower().endswith(".pdf"):
                parts = []
                if bumped:
                    parts.append(
                        f"<a href='#' class='dg-act' data-dg-act='unbump_now' data-dg-path='{html.escape(rel_from_root)}'>Unbump</a>"
                    )
                else:
                    parts.append(
                        f"<a href='#' class='dg-act' data-dg-act='bump' data-dg-path='{html.escape(rel_from_root)}'>Bump</a>"
                    )
                if published:
                    parts.append(
                        f"<a href='#' class='dg-act' data-dg-act='unpublish' data-dg-path='{html.escape(rel_from_root)}'>Despublicar</a>"
                    )
                elif bumped:
                    parts.append(
                        f"<a href='#' class='dg-act' data-dg-act='publish' data-dg-path='{html.escape(rel_from_root)}'>Publicar</a>"
                    )
                if parts:
                    actions_html = f"<span class='dg-actions'>{' '.join(parts)}</span>"

            date_html = f"<span class='dg-date'> — {fmt_ts(mtime)}</span>"
            if is_dir:
                r.append(f'<li{cls}><span>{prefix}<a href="{link}">{html.escape(disp)}</a>{date_html}</span>{actions_html}</li>')
            elif name.lower().endswith(".html"):
                r.append(f'<li{cls}><span>{prefix}📄 <a href="{link}">{html.escape(disp)}</a>{date_html}</span>{actions_html}</li>')
            elif name.lower().endswith(".pdf"):
                r.append(f'<li{cls}><span>{prefix}📕 <a href="{link}">{html.escape(disp)}</a>{date_html}</span>{actions_html}</li>')

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
