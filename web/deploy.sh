#!/bin/bash

set -euo pipefail

# Check that required variables are defined.
if [[ -z "$REMOTE_USER" || -z "$REMOTE_HOST" ]]; then
  echo "❌ Error: One or more required variables are not defined."
  echo "Please make sure the following variables are set:"
  echo "  REMOTE_USER, REMOTE_HOST"
  exit 1
fi

REMOTE_PATH="/opt/web-domingo"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PERSONAL_WEB_DIR="${PERSONAL_WEB_DIR:-}"
DOCFLOW_PUBLIC_DIR="$SCRIPT_DIR/public"
DOCFLOW_READ_DIR="$DOCFLOW_PUBLIC_DIR/read"

cleanup() {
  if [[ -n "${STAGING_DIR:-}" && -d "$STAGING_DIR" ]]; then
    rm -rf "$STAGING_DIR"
  fi
}
trap cleanup EXIT

copy_tree() {
  local src="$1"
  local dest="$2"

  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete "$src"/ "$dest"/
  else
    rm -rf "$dest"
    mkdir -p "$dest"
    cp -R "$src"/. "$dest"/
  fi
}

# Generate read.html for /read (combined HTML+PDF) with the repo generator.
echo "🧾 Generating static listing (mtime desc)…"
PYTHON_BIN="python3"; command -v python3 >/dev/null 2>&1 || PYTHON_BIN=python
"$PYTHON_BIN" "$SCRIPT_DIR/../utils/sync_tweets_public.py" --output-dir "$DOCFLOW_READ_DIR/tweets"
"$PYTHON_BIN" "$SCRIPT_DIR/../utils/build_tweets_index.py" --output-dir "$DOCFLOW_READ_DIR/tweets"
"$PYTHON_BIN" "$SCRIPT_DIR/../utils/build_read_index.py" "$DOCFLOW_READ_DIR"

STAGING_DIR="$(mktemp -d)"
PUBLIC_STAGING="$STAGING_DIR/public"
mkdir -p "$PUBLIC_STAGING"

if [[ -n "$PERSONAL_WEB_DIR" ]]; then
  PERSONAL_PUBLIC_DIR="$PERSONAL_WEB_DIR/public"
  if [[ ! -d "$PERSONAL_PUBLIC_DIR" ]]; then
    echo "❌ Error: PERSONAL_WEB_DIR does not contain a public/ directory."
    echo "  PERSONAL_WEB_DIR=$PERSONAL_WEB_DIR"
    exit 1
  fi

  echo "📁 Staging personal site from $PERSONAL_PUBLIC_DIR..."
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete --exclude 'read/' "$PERSONAL_PUBLIC_DIR"/ "$PUBLIC_STAGING"/
  else
    copy_tree "$PERSONAL_PUBLIC_DIR" "$PUBLIC_STAGING"
    rm -rf "$PUBLIC_STAGING/read"
  fi
else
  echo "ℹ️ PERSONAL_WEB_DIR not set; using $DOCFLOW_PUBLIC_DIR as base."
  copy_tree "$DOCFLOW_PUBLIC_DIR" "$PUBLIC_STAGING"
fi

echo "📚 Staging /read from docflow..."
rm -rf "$PUBLIC_STAGING/read"
mkdir -p "$PUBLIC_STAGING/read"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete "$DOCFLOW_READ_DIR"/ "$PUBLIC_STAGING/read"/
else
  copy_tree "$DOCFLOW_READ_DIR" "$PUBLIC_STAGING/read"
fi

cp "$SCRIPT_DIR/Dockerfile" "$STAGING_DIR/Dockerfile"
cp "$SCRIPT_DIR/nginx.conf" "$STAGING_DIR/nginx.conf"

echo "📦 Packaging files (without macOS metadata)..."
# Avoid xattrs and AppleDouble files (.DS_Store, ._*). On macOS (bsdtar),
# add flags to exclude xattrs and mac metadata.
CREATE_FLAGS=""
if tar --version 2>/dev/null | grep -qi bsdtar; then
  CREATE_FLAGS="--no-xattrs --no-mac-metadata"
fi
COPYFILE_DISABLE=1 tar $CREATE_FLAGS \
  --exclude='.DS_Store' \
  --exclude='._*' \
  -C "$STAGING_DIR" \
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
  echo "🔐 Updating .htpasswd on the remote host (user: $HTPASSWD_USER)…"
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

echo "🚀 Uploading files..."
scp "$SCRIPT_DIR/deploy.tar.gz" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH/"

echo "🔧 Deploying on the server..."
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

echo "✅ Deploy complete. The container serves at http://localhost:8080 on the server."
echo "🌐 Host Nginx terminates HTTPS and proxies to this port."
:
