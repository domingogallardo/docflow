#!/bin/bash

# Comprobar que las variables necesarias están definidas
if [[ -z "$REMOTE_USER" || -z "$REMOTE_HOST" ]]; then
  echo "❌ Error: Una o más variables necesarias no están definidas."
  echo "Por favor, asegúrate de que las siguientes variables están configuradas:"
  echo "  REMOTE_USER, REMOTE_HOST"
  exit 1
fi

REMOTE_PATH="/opt/web-domingo"
CONTAINER_NAME="web-domingo"
IMAGE_NAME="web-domingo"

echo "🛠️  Construyendo imagen local..."
docker build -t $IMAGE_NAME .

echo "📦 Empaquetando archivos..."
tar czf deploy.tar.gz \
    Dockerfile \
    nginx.conf \
    public

echo "📁 Preparando servidor remoto..."
ssh $REMOTE_USER@$REMOTE_HOST "mkdir -p $REMOTE_PATH $REMOTE_PATH/dynamic-data"

echo "🚀 Subiendo archivos..."
scp deploy.tar.gz $REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH/

echo "🔧 Desplegando en el servidor..."
ssh $REMOTE_USER@$REMOTE_HOST << 'EOF'
  set -e
  cd /opt/web-domingo
  tar xzf deploy.tar.gz
  rm deploy.tar.gz

  # Permisos para edición (UID/GID 101 = nginx en Alpine)
  chown -R 101:101 /opt/web-domingo/dynamic-data
  chmod -R 755 /opt/web-domingo/dynamic-data

  docker stop web-domingo || true
  docker rm web-domingo || true
  docker build -t web-domingo .

  docker run -d -p 8080:80 \
    -v /opt/web-domingo/dynamic-data:/data:rw \
    -v /opt/web-domingo/nginx/.htpasswd:/etc/nginx/.htpasswd:ro \
    --name web-domingo web-domingo
EOF

rm deploy.tar.gz

echo "✅ Despliegue completo. El contenedor sirve por http://localhost:8080 en el servidor."
echo "🌐 Nginx del host termina HTTPS y hace proxy a este puerto."
echo "📝 Edición en /editor → PUT sobre /data/nota.txt (BasicAuth)."