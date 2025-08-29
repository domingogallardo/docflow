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

# Generador de índices estáticos (lista simple con fecha, sin CSS)
gen_index() {
  local DIR_PATH="$1"; local TITLE="$2"; local EXT_FILTER="$3"
  if [[ -d "$DIR_PATH" ]]; then
    echo "🧾 Generando índice estático de ${TITLE} (mtime desc)..."
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
    if low in ('index.html','index.htm'): continue
    if allowed and not low.endswith(allowed): continue
    st = os.stat(path)
    entries.append((st.st_mtime, name))

entries.sort(key=lambda x: x[0], reverse=True)  # mtime DESC

MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
def fmt_date(ts: float) -> str:
    t = time.localtime(ts); return f"{t.tm_year}-{MONTHS[t.tm_mon-1]}-{t.tm_mday:02d} {t.tm_hour:02d}:{t.tm_min:02d}"

items = []
for mtime, name in entries:
    href = quote(name); esc = html.escape(name); d = fmt_date(mtime)
    items.append(f'<li><a href="{href}" title="{esc}">{esc}</a> — {d}</li>')

html_doc = (
    '<!DOCTYPE html><html><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width">'
    f'<title>{html.escape(title)}</title></head><body>'
    f'<h1>{html.escape(title)}</h1>'
    '<ul>' + "\n".join(items) + '</ul>'
    '</body></html>'
)

out = os.path.join(dir_path, 'index.html')
with open(out, 'w', encoding='utf-8') as f: f.write(html_doc)
print(f"✓ Generado {out}")
PY
  fi
}

# Generar índice para /read (HTML+PDF combinados)
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
# Usa una (y solo una) de estas formas, habilitando MANAGE_HTPASSWD=1:
#  - HTPASSWD_FILE: ruta local a un archivo .htpasswd para copiar tal cual
#  - HTPASSWD_ENTRY: línea completa 'usuario:hash_bcrypt' (no plaintext)
#  - HTPASSWD_USER + HTPASSWD_PASS: el script generará bcrypt en remoto (requiere apache2-utils)
if [[ "${MANAGE_HTPASSWD:-0}" == "1" ]]; then
  echo "🔐 Actualizando .htpasswd en el host remoto (modo seguro)…"
  # Asegurar carpeta nginx
  ssh "$REMOTE_USER@$REMOTE_HOST" "mkdir -p $REMOTE_PATH/nginx"
  if [[ -n "${HTPASSWD_FILE:-}" ]]; then
    scp "$HTPASSWD_FILE" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH/nginx/.htpasswd"
  elif [[ -n "${HTPASSWD_ENTRY:-}" ]]; then
    # Evita problemas de quoting enviando por stdin
    printf '%s' "$HTPASSWD_ENTRY" | ssh "$REMOTE_USER@$REMOTE_HOST" "cat > $REMOTE_PATH/nginx/.htpasswd"
  elif [[ -n "${HTPASSWD_USER:-}" && -n "${HTPASSWD_PASS:-}" ]]; then
    # Generar con bcrypt en remoto sin exponer la contraseña en argv (usa -i)
    PASS_B64=$(printf '%s' "$HTPASSWD_PASS" | base64)
    ssh "$REMOTE_USER@$REMOTE_HOST" bash -s << 'EOSSH'
set -euo pipefail
if ! command -v htpasswd >/dev/null 2>&1; then
  apt-get update -y >/dev/null && apt-get install -y apache2-utils >/dev/null
fi
mkdir -p /opt/web-domingo/nginx
umask 027
printf '%s' "$PASS_B64" | base64 -d | htpasswd -iB -C "${HTPASSWD_BCRYPT_COST:-12}" -c /opt/web-domingo/nginx/.htpasswd "$HTPASSWD_USER"
chown root:root /opt/web-domingo/nginx/.htpasswd
chmod 640 /opt/web-domingo/nginx/.htpasswd
EOSSH
    unset PASS_B64
  else
    echo "ℹ️ MANAGE_HTPASSWD=1 pero no se proporcionó HTPASSWD_FILE, HTPASSWD_ENTRY ni HTPASSWD_USER+HTPASSWD_PASS. Se omite." >&2
  fi
fi

echo "🚀 Subiendo archivos..."
scp "$SCRIPT_DIR/deploy.tar.gz" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH/"

echo "🔧 Desplegando en el servidor..."
ssh $REMOTE_USER@$REMOTE_HOST << 'EOF'
  set -e
  cd /opt/web-domingo
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
