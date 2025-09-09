#!/bin/bash

set -euo pipefail

# Comprobar que las variables necesarias están definidas
if [[ -z "$REMOTE_USER" || -z "$REMOTE_HOST" ]]; then
  echo "❌ Error: Una o más variables necesarias no están definidas."
  echo "Por favor, asegúrate de que las siguientes variables están configuradas:"
  echo "  REMOTE_USER, REMOTE_HOST"
  exit 1
fi

REMOTE_PATH="/opt/web-domingo"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Generador de listados estáticos (lista simple con fecha, sin CSS)
gen_index() {
  local DIR_PATH="$1"; local TITLE="$2"; local EXT_FILTER="$3"
  if [[ -d "$DIR_PATH" ]]; then
    echo "🧾 Generando listado estático de ${TITLE} (mtime desc)..."
    PYTHON_BIN="python3"; command -v python3 >/dev/null 2>&1 || PYTHON_BIN=python
    DIR_PATH="$DIR_PATH" TITLE="$TITLE" EXT_FILTER="$EXT_FILTER" "$PYTHON_BIN" - << 'PY'
import os, sys, time, html
from urllib.parse import quote

dir_path = os.environ.get('DIR_PATH')
title = os.environ.get('TITLE', 'Index')
ext_filter = os.environ.get('EXT_FILTER', '')
allowed = tuple([e.strip().lower() for e in ext_filter.split(',') if e.strip()]) if ext_filter else None
if not dir_path:
    print('DIR_PATH no definido', file=sys.stderr); sys.exit(1)

entries = []
for name in os.listdir(dir_path):
    if name.startswith('.'): continue
    path = os.path.join(dir_path, name)
    if not os.path.isfile(path): continue
    low = name.lower()
    if low in ('read.html','index.html','index.htm'): continue
    if allowed and not low.endswith(allowed): continue
    st = os.stat(path)
    entries.append((st.st_mtime, name))

entries.sort(key=lambda x: x[0], reverse=True)  # mtime DESC

MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
def fmt_date(ts: float) -> str:
    t = time.localtime(ts); return f"{t.tm_year}-{MONTHS[t.tm_mon-1]}-{t.tm_mday:02d} {t.tm_hour:02d}:{t.tm_min:02d}"

def load_read_posts_md(base_dir: str) -> list[str]:
    """Carga nombres de posts desde read_posts.md si existe.
    Acepta líneas no vacías (ignora comentarios y viñetas '- ' o '* ').
    Devuelve una lista en orden de aparición.
    """
    md_path = os.path.join(base_dir, 'read_posts.md')
    if not os.path.isfile(md_path):
        return []
    picked: list[str] = []
    with open(md_path, 'r', encoding='utf-8') as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('- '):
                line = line[2:].strip()
            elif line.startswith('* '):
                line = line[2:].strip()
            # Mantener tal cual: nombres de archivo esperados (con extensión)
            picked.append(line)
    return picked

# Construir listas: principales (no seleccionados) y destacados (desde read_posts.md)
picked_names = load_read_posts_md(dir_path)
picked_set = set(picked_names)

items_main: list[str] = []
items_picked: list[str] = []

# Índice rápido de metadatos por nombre
by_name = {name: mtime for (mtime, name) in entries}

for mtime, name in entries:
    href = quote(name); esc = html.escape(name); d = fmt_date(mtime)
    li = f'<li><a href="{href}" title="{esc}">{esc}</a> — {d}</li>'
    if name in picked_set:
        # Evitar duplicados: se mostrará en la sección inferior
        continue
    items_main.append(li)

# Añadir la sección destacada respetando el orden de read_posts.md
for name in picked_names:
    if name not in by_name:
        # Ignorar entradas que no existan en el directorio
        continue
    mtime = by_name[name]
    href = quote(name); esc = html.escape(name); d = fmt_date(mtime)
    items_picked.append(f'<li><a href="{href}" title="{esc}">{esc}</a> — {d}</li>')

    # (el ASCII art se define fuera del bucle)

ascii_open = r'''<style>
  .ascii-head { margin-top: 28px; color: #666; font-size: 14px; }
  pre.ascii-logo {
    margin: 10px 0 0;
    color: #666;
    line-height: 1.05;
    font-size: 12px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    white-space: pre;
  }
</style>
<div class="ascii-head"><a href="https://github.com/domingogallardo/docflow" target="_blank" rel="noopener">Docflow</a></div>
<pre class="ascii-logo" aria-hidden="true">         _
        /^\
        |-|
        |D|
        |O|
        |C|
        |F|
        |L|
        |O|
        |W|
       /| |\
      /_| |_\
        /_\
       /___\
      /_/ \_\
</pre>'''

html_doc = (
'<!DOCTYPE html><html><head><meta charset="utf-8">'
'<meta name="viewport" content="width=device-width">'
f'<title>{html.escape(title)}</title></head><body>'
f'<h1>{html.escape(title)}</h1>'
"<ul>" + "\n".join(items_main) + "</ul>" +
 ("<hr/>" + "<ul>" + "\n".join(items_picked) + "</ul>" if items_picked else "") +
 ascii_open +
'</body></html>'
)

out = os.path.join(dir_path, 'read.html')
with open(out, 'w', encoding='utf-8') as f: f.write(html_doc)
print(f"✓ Generado {out}")
PY
  fi
}

# Generar read.html para /read (HTML+PDF combinados)
gen_index "$SCRIPT_DIR/public/read" "Read" ".html,.htm,.pdf"

echo "📦 Empaquetando archivos (sin metadatos de macOS)..."
# Evita xattrs y archivos AppleDouble (.DS_Store, ._*) que provocan warnings en GNU tar
COPYFILE_DISABLE=1 tar \
  --exclude='.DS_Store' \
  --exclude='._*' \
  -C "$SCRIPT_DIR" \
  -czf "$SCRIPT_DIR/deploy.tar.gz" \
  Dockerfile \
  nginx.conf \
  public

echo "📁 Preparando servidor remoto..."
ssh "$REMOTE_USER@$REMOTE_HOST" "mkdir -p $REMOTE_PATH $REMOTE_PATH/dynamic-data"

# (Opcional) Gestionar credenciales BasicAuth (.htpasswd) en el host remoto
# Modo único y simple: definir HTPASSWD_USER y HTPASSWD_PSS en el entorno.
# - La contraseña nunca se muestra en argv: se pasa por stdin y se codifica base64 para el salto SSH.
if [[ -n "${HTPASSWD_USER:-}" && -n "${HTPASSWD_PSS:-}" ]]; then
  echo "🔐 Actualizando .htpasswd en el host remoto (usuario: $HTPASSWD_USER)…"
  ssh "$REMOTE_USER@$REMOTE_HOST" "mkdir -p $REMOTE_PATH/nginx"
  PASS_B64=$(printf '%s' "$HTPASSWD_PSS" | base64)
  ssh "$REMOTE_USER@$REMOTE_HOST" HTPASSWD_USER="$HTPASSWD_USER" PASS_B64="$PASS_B64" bash -s << 'EOSSH'
set -euo pipefail
if ! command -v htpasswd >/dev/null 2>&1; then
  apt-get update -y >/dev/null && apt-get install -y apache2-utils >/dev/null
fi
umask 027
printf '%s' "$PASS_B64" | base64 -d | htpasswd -iB -c /opt/web-domingo/nginx/.htpasswd "$HTPASSWD_USER"
chown root:root /opt/web-domingo/nginx/.htpasswd
chmod 644 /opt/web-domingo/nginx/.htpasswd
EOSSH
  unset PASS_B64
fi

echo "🚀 Subiendo archivos..."
scp "$SCRIPT_DIR/deploy.tar.gz" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH/"

echo "🔧 Desplegando en el servidor..."
ssh $REMOTE_USER@$REMOTE_HOST << 'EOF'
  set -e
  cd /opt/web-domingo
  # Limpiar "public" previo para evitar residuos (p.ej. /public/posts)
  rm -rf public
  # Extrae silenciando warnings por keywords desconocidos y timestamps futuros si está soportado
  if tar --help 2>&1 | grep -q -- '--warning'; then
    tar --warning=no-unknown-keyword --warning=no-timestamp -xzf deploy.tar.gz
  else
    tar -xzf deploy.tar.gz
  fi
  rm deploy.tar.gz

  # Permisos para edición (nginx en Alpine: uid=100, gid=101)
  chown -R 100:101 /opt/web-domingo/dynamic-data
  chmod -R 755 /opt/web-domingo/dynamic-data

  docker stop web-domingo || true
  docker rm web-domingo || true
  docker build -t web-domingo .

  docker run -d -p 8080:80 \
    -v /opt/web-domingo/dynamic-data:/data:rw \
    -v /opt/web-domingo/nginx/.htpasswd:/etc/nginx/.htpasswd:ro \
    --name web-domingo web-domingo
EOF

rm -f "$SCRIPT_DIR/deploy.tar.gz"

echo "✅ Despliegue completo. El contenedor sirve por http://localhost:8080 en el servidor."
echo "🌐 Nginx del host termina HTTPS y hace proxy a este puerto."
echo "📝 Edición en /editor → PUT sobre /data/nota.txt (BasicAuth)."

:
