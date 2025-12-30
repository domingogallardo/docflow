#!/bin/bash

set -euo pipefail

# Check that required variables are defined.
if [[ -z "$REMOTE_USER" || -z "$REMOTE_HOST" ]]; then
  echo "❌ Error: Una o más variables necesarias no están definidas."
  echo "Por favor, asegúrate de que las siguientes variables están configuradas:"
  echo "  REMOTE_USER, REMOTE_HOST"
  exit 1
fi

REMOTE_PATH="/opt/web-domingo"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Generate read.html for /read (combined HTML+PDF) with the repo generator.
echo "🧾 Generando listado estático (mtime desc)…"
PYTHON_BIN="python3"; command -v python3 >/dev/null 2>&1 || PYTHON_BIN=python
"$PYTHON_BIN" "$SCRIPT_DIR/../utils/build_read_index.py" "$SCRIPT_DIR/public/read"

echo "📦 Empaquetando archivos (sin metadatos de macOS)..."
# Avoid xattrs and AppleDouble files (.DS_Store, ._*). On macOS (bsdtar),
# add flags to exclude xattrs and mac metadata.
CREATE_FLAGS=""
if tar --version 2>/dev/null | grep -qi bsdtar; then
  CREATE_FLAGS="--no-xattrs --no-mac-metadata"
fi
COPYFILE_DISABLE=1 tar $CREATE_FLAGS \
  --exclude='.DS_Store' \
  --exclude='._*' \
  -C "$SCRIPT_DIR" \
  -czf "$SCRIPT_DIR/deploy.tar.gz" \
  Dockerfile \
  nginx.conf \
  public

echo "📁 Preparando servidor remoto..."
ssh "$REMOTE_USER@$REMOTE_HOST" "mkdir -p $REMOTE_PATH $REMOTE_PATH/dynamic-data"

# (Optional) Manage BasicAuth credentials (.htpasswd) on the remote host.
# Simple mode: set HTPASSWD_USER and HTPASSWD_PSS in the environment.
# - The password is never shown in argv: it is passed via stdin and base64-encoded for SSH.
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
  # Clean previous "public" to avoid leftovers (e.g., /public/posts)
  rm -rf public
  # Extract while silencing warnings for unknown keywords and future timestamps if supported.
  if tar --help 2>&1 | grep -q -- '--warning'; then
    tar --warning=no-unknown-keyword --warning=no-timestamp -xzf deploy.tar.gz
  else
    tar -xzf deploy.tar.gz
  fi
  rm deploy.tar.gz

  # Edit permissions (nginx on Alpine: uid=100, gid=101)
  chown -R 100:101 /opt/web-domingo/dynamic-data
  chmod -R 755 /opt/web-domingo/dynamic-data

  docker rm -f web-domingo || true
  docker build -t web-domingo .

  docker run -d -p 8080:80 \
    -v /opt/web-domingo/dynamic-data:/data:rw \
    -v /opt/web-domingo/nginx/.htpasswd:/etc/nginx/.htpasswd:ro \
    --name web-domingo web-domingo
EOF

rm -f "$SCRIPT_DIR/deploy.tar.gz"

echo "✅ Despliegue completo. El contenedor sirve por http://localhost:8080 en el servidor."
echo "🌐 Nginx del host termina HTTPS y hace proxy a este puerto."
:
