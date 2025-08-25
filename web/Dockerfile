# [APP] NGINX-App (CONTENEDOR)
# Imagen que sirve la web estática y listados ordenados por fecha.
# - Base: Alpine 3.20. Se instalan NGINX y tzdata desde apk. Zona horaria: Europe/Madrid.
# - Función [APP]: servir / (HTML/PDF), exponer /docs y /posts con índices estáticos por mtime desc
#   (generados en el deploy) y habilitar WebDAV en /data (PUT) con BasicAuth usando un .htpasswd montado.
#
# Despliegue en DigitalOcean con doble NGINX (domingogallardo.com):
# - [PROXY] NGINX-Proxy (HOST): termina TLS (Let’s Encrypt), redirige 80→443 y
#   hace proxy a http://localhost:8080. Config: /etc/nginx/sites-available/miweb.
# - [APP] NGINX-App (CONTENEDOR): escucha en :80 y se publica como host:8080.
#   Montajes:
#     - /opt/web-domingo/dynamic-data  → /data  (rw)   ← ficheros editables vía WebDAV
#     - /opt/web-domingo/nginx/.htpasswd → /etc/nginx/.htpasswd (ro) ← credenciales BasicAuth
#   La configuración de [APP] está en /etc/nginx/nginx.conf.
#
# Nota: los índices de /docs y /posts se generan en web/deploy.sh.
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
