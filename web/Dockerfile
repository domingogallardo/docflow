# [APP] NGINX-App (CONTAINER)
# Image that serves the static web and date-ordered listings.
# - Base: Alpine 3.20. NGINX and tzdata are installed via apk. Time zone: Europe/Madrid.
# - [APP] role: serve / (HTML/PDF), expose /read with auto listing
#   (read.html ordered by mtime desc generated on deploy) and enable WebDAV on /data (PUT)
#   with BasicAuth using a mounted .htpasswd.
#
# DigitalOcean deployment with double NGINX (domingogallardo.com):
# - [PROXY] NGINX-Proxy (HOST): terminates TLS (Let's Encrypt), redirects 80→443 and
#   proxies to http://localhost:8080. Config: /etc/nginx/sites-available/miweb.
# - [APP] NGINX-App (CONTAINER): listens on :80 and is published as host:8080.
#   Mounts:
#     - /opt/web-domingo/dynamic-data  → /data  (rw)   ← files editable via WebDAV
#     - /opt/web-domingo/nginx/.htpasswd → /etc/nginx/.htpasswd (ro) ← BasicAuth credentials
#   [APP] configuration is in /etc/nginx/nginx.conf.
#
# Note: read.html is generated in web/deploy.sh.
# The [PROXY] only routes; write authentication is enforced in [APP].

FROM alpine:3.20

# NGINX and tzdata
RUN apk add --no-cache nginx tzdata \
    && mkdir -p /run/nginx

ENV TZ=Europe/Madrid

COPY public /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
