# [APP] NGINX-App (CONTENEDOR)
# Imagen que sirve la web estática y los listados ordenados por fecha.
# - Base: Alpine 3.20. Se instalan NGINX, tzdata y el módulo FancyIndex desde apk
#   (versiones compatibles). Zona horaria: Europe/Madrid.
# - Función [APP]: servir / (HTML/PDF), listar /docs y /posts por mtime (FancyIndex),
#   y habilitar WebDAV en /data (PUT) con BasicAuth usando un .htpasswd montado.
#
# Despliegue en DigitalOcean con doble NGINX:
# - [PROXY] NGINX-Proxy (HOST): termina TLS (Let’s Encrypt), redirige 80→443 y
#   hace proxy a http://localhost:8080. Config: /etc/nginx/sites-available/miweb.
# - [APP] NGINX-App (CONTENEDOR): escucha en :80 y se publica como host:8080.
#   Montajes:
#     - /opt/web-domingo/dynamic-data  → /data  (rw)   ← ficheros editables vía WebDAV
#     - /opt/web-domingo/nginx/.htpasswd → /etc/nginx/.htpasswd (ro) ← credenciales BasicAuth
#   La configuración de [APP] está en /etc/nginx/nginx.conf (incluye FancyIndex).
#
# Nota: FancyIndex muestra los listados por fecha de modificación (ideal para “bumps”).
# El [PROXY] solo enruta; la autenticación de escritura se aplica en [APP].

FROM alpine:3.20

# NGINX y FancyIndex del mismo repositorio (versiones compatibles)
RUN apk add --no-cache nginx nginx-mod-http-fancyindex tzdata \
    && mkdir -p /run/nginx

ENV TZ=Europe/Madrid

COPY public /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
