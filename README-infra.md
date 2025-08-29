# docflow Infra: Ubuntu Host (Nginx TLS) + Docker App (Nginx)

_Public-facing guide for deploying a simple, secure web stack with a reverse-proxy on the **host** and an **app container** serving static content and date-ordered listings (static indexes), plus a minimal WebDAV-like editing endpoint guarded by BasicAuth._

Production site: https://domingogallardo.com

> **Scope & safety**
> - No secrets or sensitive values are included here. Replace placeholders like `<YOUR_DOMAIN>` and create credentials locally.
> - Keep `.htpasswd` and any private files **out of the repo**. Use bind-mounts at deploy time.

> **Repo specifics (docflow)**
> - The infra lives under `web/` in this repo (not `infra/`).
> - Provided files: `web/Dockerfile`, `web/nginx.conf`, `web/docker-compose.yml`, `web/deploy.sh`.
> - Names/paths used here: container name `web-domingo`, remote path `/opt/web-domingo` (match `web/deploy.sh`).
> - Local compose mounts `/data` read‑only (safe default); the deploy script mounts `/data` read‑write on the server.
> - The bundled `web/nginx.conf` serves `/read/` (HTML+PDF). Static `index.html` files are generated at deploy time. The container uses `server_name localhost`.
> - Public assets under `web/public/` are not tracked in the public repo (ignored via `.gitignore`).

---

## 1) Architecture

- **[PROXY] Nginx on the host (Ubuntu)**  
  - Terminates **HTTPS** (Let’s Encrypt), redirects HTTP→HTTPS, and reverse‑proxies to the app on `localhost:8080`.
- **[APP] Nginx in Docker container**  
  - Serves **static** content from the image (`/usr/share/nginx/html`).  
- Exposes **/read** (HTML+PDF) with static index ordered by **mtime desc** (ideal for “bumps”).
  - Provides **/data** for simple edits via **HTTP PUT** (no delete) protected by **BasicAuth** using a host‑mounted `.htpasswd`.

**Why mtime sorting?**  
Setting a file’s modification time (mtime) lets you “bump” items so they float to the top in the directory listing. The deploy script generates indexes sorted by date descending, which pairs nicely with this workflow.

---

## 2) Prerequisites

- Ubuntu LTS host with root/SSH access.
- DNS A/AAAA records for `<YOUR_DOMAIN>` and `www.<YOUR_DOMAIN>` pointing to your server.
- A Git repo with your static site under `public/`, plus the Docker and Nginx configs in this README.

> Keep your host’s packages updated regularly: `sudo apt update && sudo apt -y upgrade`.

---

## 3) Host setup (Ubuntu)

### 3.1 Install base packages

```bash
sudo apt -y install ca-certificates curl gnupg ufw nginx
```

### 3.2 Firewall (UFW)

```bash
sudo ufw allow "Nginx HTTP"     # 80
sudo ufw allow "Nginx HTTPS"    # 443
sudo ufw allow "OpenSSH"        # 22
sudo ufw enable
sudo ufw status
```

### 3.3 Install Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
# (Optional) run docker as your user:
# sudo usermod -aG docker $USER && newgrp docker
```

### 3.4 Persistent directories on the host

```bash
sudo mkdir -p /opt/web-domingo/dynamic-data
sudo mkdir -p /opt/web-domingo/nginx
# Allow writes from Nginx in Alpine (nginx defaults: uid=100, gid=101)
sudo chown -R 100:101 /opt/web-domingo/dynamic-data
sudo chmod -R 755 /opt/web-domingo/dynamic-data
```

### 3.5 BasicAuth credentials (host-only)

```bash
sudo apt -y install apache2-utils
sudo htpasswd -B -c /opt/web-domingo/nginx/.htpasswd <YOUR_USER>
sudo chown root:root /opt/web-domingo/nginx/.htpasswd
sudo chmod 640 /opt/web-domingo/nginx/.htpasswd
```

> Do **not** commit `.htpasswd`. Create/update it directly on the host.

---

## 4) Nginx on the host (Reverse‑Proxy + TLS)

Create `/etc/nginx/sites-available/webapp`:

```nginx
server {
    listen 80;
    server_name <YOUR_DOMAIN> www.<YOUR_DOMAIN>;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name <YOUR_DOMAIN> www.<YOUR_DOMAIN>;

    ssl_certificate     /etc/letsencrypt/live/<YOUR_DOMAIN>/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/<YOUR_DOMAIN>/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers EECDH+AESGCM:EECDH+CHACHA20;
    add_header Strict-Transport-Security "max-age=31536000" always;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;

    location / {
        proxy_pass http://localhost:8080/;
    }
}
```

Enable and reload:

```bash
sudo ln -s /etc/nginx/sites-available/webapp /etc/nginx/sites-enabled/webapp
sudo nginx -t && sudo systemctl reload nginx
```

### HTTPS with Let’s Encrypt (Certbot)

```bash
sudo apt update
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d <YOUR_DOMAIN> -d www.<YOUR_DOMAIN> --redirect
```

Renewal:

```bash
sudo systemctl list-timers | grep certbot
sudo certbot renew --dry-run
```

(Optional) reload hook `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh`:

```bash
#!/bin/bash
/usr/bin/systemctl reload nginx
```
```bash
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

---

## 5) App container (Docker Nginx)

### 5.1 Project layout

```
web/
├─ Dockerfile
├─ nginx.conf             # inside the container
├─ docker-compose.yml     # local dev only
└─ public/                # your static site (index.html, /read, etc.)
```

### 5.2 Dockerfile (Alpine + TZ)

```dockerfile
# [APP] NGINX-App (CONTENEDOR)
# Imagen que sirve la web estática y los listados ordenados por fecha.
# - Base: Alpine 3.20. Se instalan NGINX y tzdata desde apk. Zona horaria: Europe/Madrid.
# - Función [APP]: servir / (HTML/PDF), exponer /read con índice estático por mtime desc
#   (generados en el deploy), y habilitar WebDAV en /data (PUT) con BasicAuth usando un .htpasswd montado.
#
# Despliegue con doble NGINX:
# - [PROXY] Host: termina TLS (Let’s Encrypt), redirige 80→443 y
#   hace proxy a http://localhost:8080.
# - [APP] Contenedor: escucha en :80 y se publica como host:8080.
#   Montajes:
#     - /opt/web-domingo/dynamic-data  → /data  (rw)   ← ficheros editables vía WebDAV
#     - /opt/web-domingo/nginx/.htpasswd → /etc/nginx/.htpasswd (ro) ← credenciales BasicAuth
#   La configuración de [APP] está en /etc/nginx/nginx.conf.
#
# Nota: el índice de /read se genera en `web/deploy.sh`.
# El [PROXY] solo enruta; la autenticación de escritura se aplica en [APP].

FROM alpine:3.20

# NGINX y tzdata
RUN apk add --no-cache nginx tzdata \
    && mkdir -p /run/nginx

ENV TZ=Europe/Madrid

COPY public /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### 5.3 `nginx.conf` inside the container

```nginx
# Load dynamic modules installed via apk (none required for static indexes)
include /etc/nginx/modules/*.conf;

user nginx;

worker_processes 1;

events { worker_connections 1024; }

http {
    include       mime.types;
    default_type  application/octet-stream;
    charset       utf-8;
    client_max_body_size 100m;

    server {
        listen 80;
        server_name _;

        root /usr/share/nginx/html;

        # Editor page (static)
        location = /editor { try_files /editor.html =404; }

        # Host-mounted data (PUT via WebDAV-like DAV)
        location /data/ {
            alias /data/;

            # Optional directory listing in /data (remove if not desired)
            autoindex on;
            autoindex_exact_size off;
            autoindex_localtime on;

            # IMPORTANT: Do not use try_files here, to allow PUT for new files
            create_full_put_path on;
            dav_methods PUT;
            dav_access user:rw group:r all:r;

            limit_except GET HEAD {
                auth_basic "Protected edit area";
                auth_basic_user_file /etc/nginx/.htpasswd;
            }
        }

        # Read: static index (mtime desc, generated at deploy)
        location = /read { return 301 /read/; }
        location /read/ {
            alias /usr/share/nginx/html/read/;
            index index.html;
            try_files $uri $uri/ /read/index.html;
        }

        # Fallback for other static assets
        location / { try_files $uri $uri/ =404; }

        add_header X-Content-Type-Options nosniff always;
        add_header X-Frame-Options DENY always;
    }
}
```

### 5.4 docker-compose (local dev only)

```yaml
version: "3.8"
services:
  web:
    build: .
    ports:
      - "8080:80"
    volumes:
      - ./public:/usr/share/nginx/html:ro
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./dynamic-data:/data:ro
```

---

## 6) Deploy script (example)

Minimal `deploy.sh` that bundles and deploys via `scp` and restarts the container on the host. **Parameterize** your remote and avoid committing secrets.

```bash
#!/usr/bin/env bash
set -euo pipefail

: "${REMOTE_USER:?Set REMOTE_USER}"
: "${REMOTE_HOST:?Set REMOTE_HOST}"
REMOTE_PATH="/opt/web-domingo"

echo "Packing…"
tar czf deploy.tar.gz Dockerfile nginx.conf public

echo "Preparing remote…"
ssh "$REMOTE_USER@$REMOTE_HOST" "mkdir -p $REMOTE_PATH $REMOTE_PATH/dynamic-data $REMOTE_PATH/nginx"

echo "Uploading…"
scp deploy.tar.gz "$REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH/"

echo "Deploying…"
ssh "$REMOTE_USER@$REMOTE_HOST" <<'EOF'
  set -e
  cd /opt/web-domingo
  tar xzf deploy.tar.gz && rm deploy.tar.gz

  chown -R 101:101 /opt/web-domingo/dynamic-data
  chmod -R 755 /opt/web-domingo/dynamic-data

  docker stop web-domingo || true
  docker rm web-domingo || true
  docker build -t web-domingo .

  HTPASSWD_MOUNT=""
  if [ -f /opt/web-domingo/nginx/.htpasswd ]; then
    HTPASSWD_MOUNT="-v /opt/web-domingo/nginx/.htpasswd:/etc/nginx/.htpasswd:ro"
  else
    echo "⚠️  Missing /opt/web-domingo/nginx/.htpasswd (create with: htpasswd -B -c /opt/web-domingo/nginx/.htpasswd <YOUR_USER>)"
  fi

  docker run -d -p 8080:80 \
    -v /opt/web-domingo/dynamic-data:/data:rw \
    $HTPASSWD_MOUNT \
    --name web-domingo web-domingo
EOF

rm deploy.tar.gz
echo "Done."
```

> For CI/CD, replicate the same build/run steps but inject secrets (domain, auth) via your CI’s secret manager.

---

## 7) Verification & operations

```bash
# Host → container (HTTP)
curl -I http://localhost:8080/

# End-to-end (HTTPS via domain)
curl -I https://domingogallardo.com
curl -I https://www.domingogallardo.com

# Certbot
sudo certbot certificates
sudo certbot renew --dry-run

# Logs
journalctl -u nginx --since today
docker logs -n 200 web-domingo
```

---

## 8) Security notes

- Do **not** commit secrets or `.htpasswd` to Git.
- Keep TLS and packages updated; prefer automatic Certbot renewal (timer/service).
- If you don’t want a directory listing in `/data`, remove `autoindex on;` in that block.
- Avoid `try_files` in the `/data/` location if you need to **PUT new files**.
- Inside the container, use `server_name _;` (catch‑all). The host sets the real domain.
- Adjust `client_max_body_size` if you plan to upload large files via `/data`.

---

## 9) Checklist

- [ ] DNS A/AAAA set for `<YOUR_DOMAIN>` and `www.<YOUR_DOMAIN>`
- [ ] UFW allows HTTP/HTTPS/SSH
- [ ] Nginx reverse‑proxy configured and reloaded
- [ ] Certbot issued certificate and renewal OK
- [ ] Docker image built & container running on `:8080`
- [ ] `.htpasswd` created on host and mounted read‑only
- [ ] Quick curl tests pass (HTTP 200/301/302/401 where expected)
- [ ] Logs clean (no recurring errors)\n
