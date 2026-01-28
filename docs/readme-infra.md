# docflow Infra: Ubuntu host (Nginx with TLS) + App in Docker (Nginx)

_Public guide to deploy a simple, secure web stack with a **reverse proxy** on the **host** and an **app container** that serves static content and date-ordered indexes, plus a minimal WebDAV-like editing endpoint protected with **BasicAuth**._

Production site: https://domingogallardo.com

> **Scope and security**
> - No secrets or sensitive values are included here. Replace placeholders like `<YOUR_DOMAIN>` and create credentials locally.
> - Keep `.htpasswd` and any private files **out of the repo**. Use bind-mounts in deployment.

> **Repo specifics (docflow)**
> - Infrastructure lives under `web/` in this repo (not `infra/`).
> - Provided files: `web/Dockerfile`, `web/nginx.conf`, `web/docker-compose.yml`, `web/deploy.sh`.
> - Names/paths used here: container name `web-domingo`, remote path `/opt/web-domingo` (matches `web/deploy.sh`).
> - In local docker-compose, `/data` is mounted **read-only** (safe by default); the deploy script mounts `/data` **read-write** on the server.
> - The included `web/nginx.conf` serves `/read/` (HTML+PDF) using nginx **autoindex** by default. The static `read.html` index is generated on deploy and is available at `/read/read.html`. If you want `/read/` to show that static index by default, add `index read.html;` inside the container Nginx `location /read/`. The container uses `server_name localhost`.
> - The `read.html` listing is a single block ordered by mtime desc with all HTML/PDFs in `web/public/read/`.
- Public assets under `web/public/` are **not** versioned in the public repo (ignored via `.gitignore`), except minimal essentials like `web/public/read/article.js` (quote button). The base site can live in a separate repo and be injected at deploy time via `PERSONAL_WEB_DIR`.

---

## 1) Architecture

- **[PROXY] Nginx on the host (Ubuntu)**  
  - Terminates **HTTPS** (Let's Encrypt), redirects HTTP->HTTPS, and **reverse-proxies** to the app on `localhost:8080`.
- **[APP] Nginx in a Docker container**  
  - Serves **static** content from the image (`/usr/share/nginx/html`).  
- Exposes **/read** (HTML+PDF) with nginx autoindex; the static `read.html` index (ordered by mtime desc) is generated at deploy and served at `/read/read.html` unless you configure `index read.html;` in `location /read/`.
  - Provides **/data** for simple edits via **HTTP PUT** (no delete) protected by **BasicAuth** using a host-mounted `.htpasswd`.

**Why order by mtime?**  
Adjusting the modification time (mtime) lets you \"bump\" items so they rise to the top of the directory listing. The deploy script generates `read.html` in descending date order, which matches this workflow.

---

## 2) Prerequisites

- Ubuntu LTS host with root/SSH access.
- DNS A/AAAA records for `<YOUR_DOMAIN>` and `www.<YOUR_DOMAIN>` pointing to your server.
- A Git repo with your static site under `public/`, plus the Docker and Nginx configs from this README. (You can keep the personal site in a separate repo and point `PERSONAL_WEB_DIR` at it.)

> Keep host packages updated regularly: `sudo apt update && sudo apt -y upgrade`.

---

## 3) Host preparation (Ubuntu)

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

### 3.4 Persistent host directories

```bash
sudo mkdir -p /opt/web-domingo/dynamic-data
sudo mkdir -p /opt/web-domingo/nginx
# Write permissions from Nginx in Alpine (uid=100, gid=101 by default)
sudo chown -R 100:101 /opt/web-domingo/dynamic-data
sudo chmod -R 755 /opt/web-domingo/dynamic-data
```

### 3.5 BasicAuth credentials (host only)

```bash
sudo apt -y install apache2-utils
sudo htpasswd -B -c /opt/web-domingo/nginx/.htpasswd <YOUR_USER>
sudo chown root:root /opt/web-domingo/nginx/.htpasswd
sudo chmod 644 /opt/web-domingo/nginx/.htpasswd
```

> **Do not** commit `.htpasswd` to the repo. Create/update it directly on the host.

---

## 4) Nginx on the host (Reverse-Proxy + TLS)

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

### HTTPS with Let's Encrypt (Certbot)

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

(Optional hook) `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh`:

```bash
#!/bin/bash
/usr/bin/systemctl reload nginx
```
```bash
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

---

## 5) App container (Nginx in Docker)

### 5.1 Project structure

```
web/
├─ Dockerfile
├─ nginx.conf             # inside the container
├─ docker-compose.yml     # local development only
└─ public/                # static site (index.html, /read, etc.)
```

### 5.2 Dockerfile (Alpine + TZ)

```dockerfile
# [APP] NGINX-App (CONTAINER)
# Image that serves the static web and date-ordered listings.
# - Base: Alpine 3.20. Installs NGINX and tzdata from apk. Time zone: Europe/Madrid.
# - [APP] function: serve / (HTML/PDF), expose /read with a static mtime-desc index
#   (generated at deploy), and enable WebDAV on /data (PUT) with BasicAuth using a mounted .htpasswd.
#
# Dual NGINX deployment:
# - [PROXY] Host: terminates TLS (Let's Encrypt), redirects 80->443, and
#   proxies to http://localhost:8080.
# - [APP] Container: listens on :80 and is published as host:8080.
#   Mounts:
#     - /opt/web-domingo/dynamic-data  -> /data  (rw)   <- editable files via WebDAV
#     - /opt/web-domingo/nginx/.htpasswd -> /etc/nginx/.htpasswd (ro) <- BasicAuth credentials
#   [APP] config lives at /etc/nginx/nginx.conf.
#
# Note: the /read index is generated in `web/deploy.sh`.
# [PROXY] only routes; write auth is enforced in [APP].

FROM alpine:3.20

# NGINX and tzdata
RUN apk add --no-cache nginx tzdata     && mkdir -p /run/nginx

ENV TZ=Europe/Madrid

COPY public /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### 5.3 `nginx.conf` inside the container

```nginx
include /etc/nginx/modules/*.conf;

user nginx;

worker_processes 1;

events {
    worker_connections 1024;
}

http {
    include       mime.types;
    default_type  application/octet-stream;

    server {
        listen 80;
        server_name localhost;

        root /usr/share/nginx/html;

        # Host-mounted data (PUT via DAV)
        location /data/ {
            alias /data/;

            # Optional directory listing
            autoindex on;

            # WebDAV: only PUT (no DELETE, no MKCOL)
            create_full_put_path on;
            dav_methods PUT;
            dav_access user:rw group:r all:r;

            # Reads are allowed without auth; writes require BasicAuth
            limit_except GET HEAD {
                auth_basic "Protected editing";
                auth_basic_user_file /etc/nginx/.htpasswd;
            }
        }

        # /read: HTML + PDF (autoindex)
        location = /read { return 301 /read/; }
        location /read/ {
            alias /usr/share/nginx/html/read/;
            autoindex on;
        }

        # /papers: site PDFs (optional section)
        location = /papers { return 301 /papers/; }
        location /papers/ {
            alias /usr/share/nginx/html/papers/;
            index index.html;
            try_files $uri $uri/ /papers/index.html;
        }

        # Fallback for other static assets
        location / { try_files $uri $uri/ =404; }

        add_header X-Content-Type-Options nosniff;
        add_header X-Frame-Options DENY;
    }
}
```

### 5.4 docker-compose (local development only)

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

## 6) Deploy script (included)

Use `web/deploy.sh`. It bundles the app, uploads it, and rebuilds/restarts the container on the remote host.

- Usage:
  - `env REMOTE_USER=root REMOTE_HOST=<SERVER_IP> bash web/deploy.sh`
  - Optional BasicAuth update: set `HTPASSWD_USER` and `HTPASSWD_PSS` (see 6.1).
  - Optional base site: set `PERSONAL_WEB_DIR=/path/to/personal-web` (deploy will use its `public/` as the base site).

- What it does (summary):
  - Generates `read.html` for `/public/read` (HTML+PDF) as **a single mtime-desc listing**. Note: by default, `/read/` shows nginx autoindex; this file is served at `/read/read.html`. If you want it to be the default index, add `index read.html;` inside the container Nginx `location /read/`.
  - Bundles `web/Dockerfile`, `web/nginx.conf`, and a staged `public/` directory (excluding `.DS_Store` and AppleDouble).
    - If `PERSONAL_WEB_DIR` is set, the staged `public/` comes from `<PERSONAL_WEB_DIR>/public` plus `/read` from this repo.
    - Otherwise it uses `web/public/` directly.
  - Ensures remote paths under `/opt/web-domingo` and uploads the bundle.
  - Cleans any previous `/opt/web-domingo/public` before extracting to avoid stale files.
  - (Optional) creates/updates `/opt/web-domingo/nginx/.htpasswd` on the host if `HTPASSWD_USER` and `HTPASSWD_PSS` are provided (bcrypt via `htpasswd -iB`).
  - Extracts the archive (suppressing certain `tar` warnings when applicable) and resets permissions on `/opt/web-domingo/dynamic-data` (uid=100,gid=101; chmod 755).
  - Rebuilds the image and runs the container as `web-domingo` on host port `8080` with mounts:
    - `/opt/web-domingo/dynamic-data:/data:rw`
    - `/opt/web-domingo/nginx/.htpasswd:/etc/nginx/.htpasswd:ro`

> For CI/CD, replicate these steps and inject credentials from your CI secrets manager.

### 6.1 Manage `.htpasswd` during deploy (optional)

To avoid manual edits on the host, `web/deploy.sh` can update `/opt/web-domingo/nginx/.htpasswd` if you define both variables:

- `HTPASSWD_USER`: user for BasicAuth.
- `HTPASSWD_PSS`: plain-text password passed via env; the script generates a bcrypt hash on the host using `htpasswd -iB` (the password travels via **stdin**, not **argv**).

Example:

```bash
HTPASSWD_USER=editor HTPASSWD_PSS='my-strong-pass' REMOTE_USER=root REMOTE_HOST=<SERVER_IP> bash web/deploy.sh
```

---

## 7) Verification and operations

```bash
# Host -> container (HTTP)
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

Note: the `/read/` index is a single date-ordered listing.

---

## 8) Security notes

- **Do not** push secrets or `.htpasswd` to Git.
- Keep TLS and packages up to date; prioritize automatic Certbot renewal (timer/service).
- If you don't want directory listings on `/data`, remove `autoindex on;` from that block.
- Avoid `try_files` in the `/data/` location if you need **PUT of new files**.
- Inside the container, you can use `server_name _;` (catch-all). The host defines the real domain.
- In the container, the config uses `server_name localhost` (the host manages the domain).
- Adjust `client_max_body_size` if you will upload large files via `/data`.

---

## 9) Checklist

- [ ] DNS A/AAAA configured for `<YOUR_DOMAIN>` and `www.<YOUR_DOMAIN>`
- [ ] UFW allows HTTP/HTTPS/SSH
- [ ] Reverse-proxy Nginx configured and reloaded
- [ ] Certificate issued by Certbot and renewal OK
- [ ] Docker image built and container running on `:8080`
- [ ] `.htpasswd` created on the host and mounted read-only
- [ ] Quick curl checks return expected HTTP 200/301/302/401
- [ ] Logs are clean (no recurring errors)
