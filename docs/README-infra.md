# docflow Infra: Host Ubuntu (Nginx con TLS) + App en Docker (Nginx)

_Guía pública para desplegar un stack web sencillo y seguro con un **reverse‑proxy** en el **host** y un **contenedor de aplicación** que sirve contenido estático e índices ordenados por fecha, además de un endpoint mínimo de edición tipo WebDAV protegido con **BasicAuth**._

Sitio en producción: https://domingogallardo.com

> **Ámbito y seguridad**
> - Aquí no se incluyen secretos ni valores sensibles. Sustituye los placeholders como `<YOUR_DOMAIN>` y crea las credenciales de forma local.
> - Mantén `.htpasswd` y cualquier archivo privado **fuera del repo**. Usa bind‑mounts en el despliegue.

> **Específicos del repo (docflow)**
> - La infraestructura está bajo `web/` en este repo (no `infra/`).
> - Ficheros proporcionados: `web/Dockerfile`, `web/nginx.conf`, `web/docker-compose.yml`, `web/deploy.sh`.
> - Nombres/rutas usados aquí: nombre del contenedor `web-domingo`, ruta remota `/opt/web-domingo` (coincide con `web/deploy.sh`).
> - En `docker-compose` local, `/data` se monta **solo lectura** (seguro por defecto); el script de deploy monta `/data` **lectura‑escritura** en el servidor.
> - El `web/nginx.conf` incluido sirve `/read/` (HTML+PDF) usando el **autoindex** de nginx por defecto. El índice estático `read.html` se genera en el despliegue y queda accesible en `/read/read.html`. Si prefieres que `/read/` muestre ese índice estático por defecto, añade `index read.html;` dentro de la `location /read/` del Nginx del contenedor. El contenedor usa `server_name localhost`.
> - El listado `read.html` incluye una sección curada: si existe `web/public/read/read_posts.md`, el deploy añade un `<hr/>` y lista esos nombres de fichero debajo (en el orden del archivo). Los elementos bajo el separador representan documentos ya leídos/estudiados (completados).
- Los assets públicos bajo `web/public/` **no** se versionan en el repo público (ignorados vía `.gitignore`), salvo utilidades mínimas imprescindibles como `web/public/read/article.js` (botón de citas) y `web/public/editor.html` (editor de `/data/nota.txt`).

---

## 1) Arquitectura

- **[PROXY] Nginx en el host (Ubuntu)**  
  - Termina **HTTPS** (Let’s Encrypt), redirige HTTP→HTTPS y hace **reverse‑proxy** a la app en `localhost:8080`.
- **[APP] Nginx en contenedor Docker**  
  - Sirve contenido **estático** desde la imagen (`/usr/share/nginx/html`).  
- Expone **/read** (HTML+PDF) con autoindex de nginx; el índice estático `read.html` (ordenado por mtime desc) se genera en el deploy y se sirve en `/read/read.html` salvo que configures `index read.html;` en la `location /read/`.
  - Proporciona **/data** para ediciones simples vía **HTTP PUT** (sin borrar) protegido por **BasicAuth** usando un `.htpasswd` montado desde el host.

**¿Por qué ordenar por mtime?**  
Ajustar el tiempo de modificación (mtime) permite “bumpear” elementos para que suban arriba en el listado del directorio. El script de deploy genera `read.html` ordenado por fecha descendente, lo que encaja con este flujo de trabajo.

---

## 2) Requisitos previos

- Host Ubuntu LTS con acceso root/SSH.
- Registros DNS A/AAAA para `<YOUR_DOMAIN>` y `www.<YOUR_DOMAIN>` apuntando a tu servidor.
- Un repo Git con tu sitio estático bajo `public/`, más los configs de Docker y Nginx de este README.

> Mantén los paquetes del host actualizados regularmente: `sudo apt update && sudo apt -y upgrade`.

---

## 3) Preparación del host (Ubuntu)

### 3.1 Instalar paquetes base

```bash
sudo apt -y install ca-certificates curl gnupg ufw nginx
```

### 3.2 Cortafuegos (UFW)

```bash
sudo ufw allow "Nginx HTTP"     # 80
sudo ufw allow "Nginx HTTPS"    # 443
sudo ufw allow "OpenSSH"        # 22
sudo ufw enable
sudo ufw status
```

### 3.3 Instalar Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
# (Opcional) ejecutar docker como tu usuario:
# sudo usermod -aG docker $USER && newgrp docker
```

### 3.4 Directorios persistentes en el host

```bash
sudo mkdir -p /opt/web-domingo/dynamic-data
sudo mkdir -p /opt/web-domingo/nginx
# Permisos de escritura desde Nginx en Alpine (uid=100, gid=101 por defecto)
sudo chown -R 100:101 /opt/web-domingo/dynamic-data
sudo chmod -R 755 /opt/web-domingo/dynamic-data
```

### 3.5 Credenciales BasicAuth (solo en host)

```bash
sudo apt -y install apache2-utils
sudo htpasswd -B -c /opt/web-domingo/nginx/.htpasswd <YOUR_USER>
sudo chown root:root /opt/web-domingo/nginx/.htpasswd
sudo chmod 644 /opt/web-domingo/nginx/.htpasswd
```

> **No** subas `.htpasswd` al repo. Créalo/actualízalo directamente en el host.

---

## 4) Nginx en el host (Reverse‑Proxy + TLS)

Crea `/etc/nginx/sites-available/webapp`:

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

Habilitar y recargar:

```bash
sudo ln -s /etc/nginx/sites-available/webapp /etc/nginx/sites-enabled/webapp
sudo nginx -t && sudo systemctl reload nginx
```

### HTTPS con Let’s Encrypt (Certbot)

```bash
sudo apt update
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d <YOUR_DOMAIN> -d www.<YOUR_DOMAIN> --redirect
```

Renovación:

```bash
sudo systemctl list-timers | grep certbot
sudo certbot renew --dry-run
```

(Hook opcional) `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh`:

```bash
#!/bin/bash
/usr/bin/systemctl reload nginx
```
```bash
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

---

## 5) Contenedor de la app (Nginx en Docker)

### 5.1 Estructura del proyecto

```
web/
├─ Dockerfile
├─ nginx.conf             # dentro del contenedor
├─ docker-compose.yml     # solo desarrollo local
└─ public/                # sitio estático (index.html, /read, etc.)
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
RUN apk add --no-cache nginx tzdata     && mkdir -p /run/nginx

ENV TZ=Europe/Madrid

COPY public /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### 5.3 `nginx.conf` dentro del contenedor

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

        # Editor page (static)
        location = /editor {
            try_files /editor.html =404;   # serves public/editor.html
        }

        # Host-mounted data (PUT via DAV)
        location /data/ {
            alias /data/;

            # Optional directory listing
            autoindex on;

            # WebDAV: only PUT (no DELETE, no MKCOL)
            create_full_put_path on;
            dav_methods PUT;
            dav_access user:rw group:r all:r;

            # Read allowed without auth; writes require BasicAuth
            limit_except GET HEAD {
                auth_basic "Edición protegida";
                auth_basic_user_file /etc/nginx/.htpasswd;
            }
        }

        # /read: HTML + PDF (autoindex)
        location = /read { return 301 /read/; }
        location /read/ {
            alias /usr/share/nginx/html/read/;
            autoindex on;
        }

        # /papers: PDFs del sitio (sección opcional)
        location = /papers { return 301 /papers/; }
        location /papers/ {
            alias /usr/share/nginx/html/papers/;
            index index.html;
            try_files $uri $uri/ /papers/index.html;
        }

        # Fallback para otros estáticos
        location / { try_files $uri $uri/ =404; }

        add_header X-Content-Type-Options nosniff;
        add_header X-Frame-Options DENY;
    }
}
```

### 5.4 docker-compose (solo desarrollo local)

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

### 5.5 Editor estático `/editor` (cliente WebDAV mínimo)

- El archivo `web/public/editor.html` forma parte del repo y se sirve como `https://<YOUR_DOMAIN>/editor`.  
- Carga/guarda `nota.txt` haciendo `fetch` contra `https://<YOUR_DOMAIN>/data/nota.txt` con `credentials: 'include'`, por lo que reutiliza la sesión de BasicAuth (no uses `usuario:contraseña@` en la URL).  
- Muestra estados “Cargando…” / “Guardando…” y propaga los errores HTTP (401, 403, etc.) para que el usuario renueve la autenticación si es necesario.  
- Ideal para automatizaciones o retoques rápidos sobre `/opt/web-domingo/dynamic-data/nota.txt` sin exponer un editor más complejo; los permisos siguen gobernados por `/data/` en `nginx.conf`.

---

## 6) Script de despliegue (incluido)

Usa `web/deploy.sh`. Empaqueta la app, la sube y reconstruye/reinicia el contenedor en el host remoto.

- Uso:
  - `env REMOTE_USER=root REMOTE_HOST=<SERVER_IP> bash web/deploy.sh`
  - Actualización opcional de BasicAuth: define `HTPASSWD_USER` y `HTPASSWD_PSS` (ver 6.1).

- Qué hace (resumen):
  - Genera `read.html` para `/public/read` (HTML+PDF). La zona superior es mtime‑desc para ficheros no listados en `read_posts.md`; debajo un `<hr/>` lista los de `web/public/read/read_posts.md` (si existe), representando **completados**. Nota: por defecto, `/read/` muestra el autoindex de nginx; este archivo se consulta como `/read/read.html`. Si prefieres que sea el índice por defecto, añade `index read.html;` dentro de la `location /read/` del Nginx del contenedor.
  - Empaqueta `web/Dockerfile`, `web/nginx.conf` y `web/public/` (excluye `.DS_Store` y AppleDouble).
  - Asegura rutas remotas bajo `/opt/web-domingo` y sube el bundle.
  - Limpia cualquier `/opt/web-domingo/public` previo antes de extraer para evitar stale files.
  - (Opcional) crea/actualiza `/opt/web-domingo/nginx/.htpasswd` en el host si se proporcionan `HTPASSWD_USER` y `HTPASSWD_PSS` (bcrypt con `htpasswd -iB`).
  - Extrae el archivo (suprimiendo ciertos warnings de `tar` cuando aplica) y restablece permisos en `/opt/web-domingo/dynamic-data` (uid=100,gid=101; chmod 755).
  - Reconstruye la imagen y ejecuta el contenedor como `web-domingo` en el puerto `8080` del host con montajes:
    - `/opt/web-domingo/dynamic-data:/data:rw`
    - `/opt/web-domingo/nginx/.htpasswd:/etc/nginx/.htpasswd:ro`

> Para CI/CD, replica estos pasos e inyecta credenciales desde el gestor de secretos de tu CI.

### 6.1 Gestionar `.htpasswd` durante el deploy (opcional)

Para evitar ediciones manuales en el host, `web/deploy.sh` puede actualizar `/opt/web-domingo/nginx/.htpasswd` si defines ambas variables:

- `HTPASSWD_USER`: usuario para BasicAuth.
- `HTPASSWD_PSS`: contraseña en texto plano pasada por entorno; el script genera un hash bcrypt en el host usando `htpasswd -iB` (la contraseña viaja por **stdin**, no aparece en **argv**).

Ejemplo:

```bash
HTPASSWD_USER=editor HTPASSWD_PSS='my-strong-pass' REMOTE_USER=root REMOTE_HOST=<SERVER_IP> bash web/deploy.sh
```

---

## 7) Verificación y operaciones

```bash
# Host → contenedor (HTTP)
curl -I http://localhost:8080/

# Extremo a extremo (HTTPS por dominio)
curl -I https://domingogallardo.com
curl -I https://www.domingogallardo.com

# Certbot
sudo certbot certificates
sudo certbot renew --dry-run

# Logs
journalctl -u nginx --since today
docker logs -n 200 web-domingo
```

Mantenimiento de la sección “completados” curada:
- Edita `web/public/read/read_posts.md` en el repo para mover elementos terminados bajo el separador en el siguiente deploy. Un nombre de fichero por línea (incluida la extensión). Las líneas pueden empezar por `- ` o `* ` y se ignoran los comentarios `#`.

---

## 8) Notas de seguridad

- **No** subas secretos ni `.htpasswd` a Git.
- Mantén TLS y paquetes al día; prioriza la renovación automática de Certbot (timer/service).
- Si no quieres listado de directorios en `/data`, quita `autoindex on;` en ese bloque.
- Evita `try_files` en la location `/data/` si necesitas **PUT de ficheros nuevos**.
- Dentro del contenedor, puedes usar `server_name _;` (catch‑all). El host define el dominio real.
- En el contenedor, la config usa `server_name localhost` (el host gestiona el dominio).
- Ajusta `client_max_body_size` si vas a subir archivos grandes vía `/data`.

---

## 9) Checklist

- [ ] DNS A/AAAA configurados para `<YOUR_DOMAIN>` y `www.<YOUR_DOMAIN>`
- [ ] UFW permite HTTP/HTTPS/SSH
- [ ] Reverse‑proxy Nginx configurado y recargado
- [ ] Certificado emitido por Certbot y renovación OK
- [ ] Imagen de Docker construida y contenedor corriendo en `:8080`
- [ ] `.htpasswd` creado en el host y montado en solo lectura
- [ ] Pruebas rápidas con curl correctas (HTTP 200/301/302/401 según lo esperado)
- [ ] Logs limpios (sin errores recurrentes)
