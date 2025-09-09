# 📚 docflow — Pipeline de Documentación Personal

docflow es un sistema automatizado para recopilar, procesar y organizar documentos personales (artículos web, PDFs, podcasts, tweets) en carpetas estructuradas por años.

```text
          _
         /^\ 
         |-|
         |D|
         |O|
         |C|
         |F|
         |L|
         |O|
         |W|
        /| |\
       /_| |_\
         /_\
        /___\
       /_/ \_\
```


## ⚙️ Uso

```bash
# Pipeline completo
python process_documents.py all [--year 2025]

# Solo procesar tweets y PDFs
python process_documents.py tweets pdfs

# Solo convertir archivos .md a HTML
python md_to_html.py

# Servir HTML/PDF con overlay de Bump/Unbump
PORT=8000 SERVE_DIR="/Users/domingo/⭐️ Documentación" python utils/serve_docs.py
```

El script principal procesa automáticamente:
- **Podcasts de Snipd** (Markdown) → `Podcasts/Podcasts <AÑO>/`
- **Tweets** (Markdown) → `Tweets/Tweets <AÑO>/`
- **Artículos de Instapaper** (HTML) → `Posts/Posts <AÑO>/`
- **PDFs** → `Pdfs/Pdfs <AÑO>/`

## 🛠 Requisitos

**Python 3.10+** y librerías:
```bash
pip install requests beautifulsoup4 markdownify anthropic pillow pytest markdown
```

**Variables de entorno:**

```bash
export ANTHROPIC_API_KEY="tu_clave"
export INSTAPAPER_USERNAME="tu_usuario" 
export INSTAPAPER_PASSWORD="tu_contraseña"
export REMOTE_USER="usuario_en_host_web_pública"
export REMOTE_HOST="IP_host_web_pública"
# Opcional: actualizar credenciales BasicAuth del editor en el deploy
# (se genera bcrypt en el host; no se guarda nada en Git)
# export HTPASSWD_USER="editor"
# export HTPASSWD_PSS="mi-contraseña-segura"
```

Nota: `REMOTE_USER` y `REMOTE_HOST` solo son necesarios si vas a Publicar/Despublicar desde el overlay del “Servidor web local”.

## 🎯 Descarga de documentos

### 📄 Artículos de Instapaper
**Entrada:** Artículos guardados en tu cuenta de Instapaper  
**Resultado:** Archivos HTML y Markdown listos para lectura con:
- ✅ Títulos generados automáticamente con IA (ES/EN, con reintentos y fallback)
- ✅ Imágenes redimensionadas (max 300px ancho)
- ⚠️ Las imágenes no se descargan; se enlazan a su servidor de origen.
  Si Instapaper no pudo obtenerlas (por ejemplo, porque Medium bloqueó su
  descarga), en el HTML final ni siquiera habrá etiquetas `<img>` para
  ellas. Si el servidor de origen solo impide el hotlinking, las imágenes
  enlazadas pueden aparecer rotas.
- ✅ Márgenes del 6% aplicados para mejor lectura
- ✅ Codificación HTML corregida
- ✅ Nombres de archivo limpio (sin caracteres problemáticos)
- ✅ Marcado de artículos destacados (estrella) propagado a HTML/MD
- ✅ Si el artículo está destacado, el HTML se bumpea automáticamente (ajuste de mtime al futuro) para que aparezca arriba en listados por fecha

### 🎧 Podcasts de Snipd  
**Entrada:** Archivos Markdown exportados desde Snipd  
**Resultado:** Transcripciones HTML limpias y organizadas con:
- ✅ Contenido limpio (sin HTML innecesario ni "Click to expand")
- ✅ Enlaces de audio convertidos a botones atractivos
- ✅ Formato HTML con tablas y código renderizado
- ✅ Nombres basados en metadatos del episodio
- ✅ Tipografía del sistema (San Francisco) para lectura elegante

### 🐦 Tweets
**Entrada:** Archivos Markdown con tweets exportados (`Tweets *.md`)  
**Resultado:** Colecciones HTML estilizadas con:
- ✅ Tipografía del sistema (San Francisco) elegante
- ✅ Estilo azul Twitter (#1DA1F2) para enlaces
- ✅ Títulos en negrita con separadores sutiles
- ✅ Márgenes del 6% para lectura cómoda
- ✅ Archivo MD original preservado
- ✅ Nombres de archivo mantenidos (ej: `Tweets 2025-07`)

### 📑 PDFs
**Entrada:** Archivos PDF en `Incoming/`  
**Resultado:** PDFs organizados por año manteniendo formato original
- ✅ Organizados en carpetas anuales
- ✅ Nombres originales preservados
- ✅ Registro en historial para seguimiento

## ⭐ Instapaper: Artículos Destacados

- Si quieres destacar un artículo para que se "bumpee" automáticamente, basta con editar el título del artículo en Instapaper añadiendo una estrella  (⭐) al comienzo.

- Salida HTML: si está destacado, se añade
  - `<meta name="instapaper-starred" content="true">`
  - Atributo en la raíz: `<html data-instapaper-starred="true">`
  - Comentario de marca: `<!-- instapaper_starred: true -->`
- Salida Markdown: se incluye front matter YAML al inicio:
  - `---\ninstapaper_starred: true\n---`

### Bump automático de HTML destacados
- Los artículos destacados se bumpean automáticamente al terminar el procesamiento: se ajusta su `mtime` al futuro para que queden arriba en listados ordenados por fecha (por ejemplo, en Finder o en el servidor `utils/serve_docs.py`).
- En el servidor de lectura (`utils/serve_docs.py`), los archivos bumpeados se resaltan con 🔥 y puedes hacer Unbump desde el overlay (atajos: `u` o ⌘/Ctrl+U).

Uso downstream:
- Filtrar Markdown por front matter (`instapaper_starred: true`) en tu generador estático o script.
- Para HTML, buscar el meta `<meta name="instapaper-starred" content="true">` o el atributo `data-instapaper-starred="true"` para resaltar o priorizar.


## 📂 Estructura de directorios

```
⭐️ Documentación/
├── Incoming/               # Archivos nuevos
├── Posts/Posts <AÑO>/      # Artículos procesados
├── Podcasts/Podcasts <AÑO>/ # Podcasts procesados
├── Tweets/Tweets <AÑO>/    # Tweets procesados
├── Pdfs/Pdfs <AÑO>/        # PDFs organizados
└── Historial.txt           # Registro histórico
```

Esta estructura es el destino natural de la “Descarga de documentos”.


## Web pública (carpeta `web/`)

La carpeta `web/` contiene la infraestructura y el contenido estático que se publica en tu servidor remoto.

- Contenido público: `web/public/`
  - Ruta pública: `/read/` (HTML + PDFs combinados).
  - `read.html` se genera en cada deploy, ordenado por `mtime` desc; además, si existe `web/public/read/read_posts.md`, se inserta un `<hr/>` y debajo se listan (en el orden del fichero) los elementos ahí indicados. Esos ficheros bajo el separador son los ya leídos/estudiados (completados). El directorio se sirve con el listado automático de nginx.
  - El overlay de `utils/serve_docs.py` publica/despublica copiando o borrando archivos en `web/public/read/` y ejecutando el deploy.
- Deploy: `web/deploy.sh`
  - Requiere `REMOTE_USER` y `REMOTE_HOST` en el entorno.
  - Empaqueta `web/Dockerfile`, `web/nginx.conf` y `web/public/`, los sube a `/opt/web-domingo` y levanta el contenedor `web-domingo` en el servidor (Nginx en host termina HTTPS y hace proxy al puerto 8080 del contenedor).
  - Editor y credenciales:
    - `/editor` es una página estática que edita `/data/nota.txt` mediante `PUT`.
    - `/data/` exige BasicAuth. El contenedor lee `/etc/nginx/.htpasswd` montado desde el host en `/opt/web-domingo/nginx/.htpasswd` (ro).
    - Permisos: el `.htpasswd` debe ser legible por Nginx; usa `chmod 644 /opt/web-domingo/nginx/.htpasswd` en el host.
    - Deploy con credenciales: si defines `HTPASSWD_USER` y `HTPASSWD_PSS`, el deploy genera/actualiza el `.htpasswd` en el host con hash bcrypt (la contraseña se pasa por stdin; no se guarda en Git).
  - Verificación pública rápida:
    - `curl -I https://domingogallardo.com/read/`
    - `curl -s https://domingogallardo.com/read/ | head -n 40`
- `/data/` en el contenedor mantiene PUT habilitado (estilo WebDAV); el listado sigue con `autoindex on;` (no se modifica desde este repo).

Más detalles de Docker/Nginx y del proceso de despliegue en la sección “🌐 Infraestructura y despliegue (Docker/Nginx)”.

## Servidor web local

`utils/serve_docs.py` levanta un servidor para leer `.html`/`.pdf` y gestionar tus documentos con un overlay sencillo y rápido. Publica/despublica en `web/public/read/`.

- Overlay en `.html` con Bump/Unbump, Publicar/Despublicar y atajos de teclado.
- Listado de carpetas/archivos ordenado por `mtime` descendente; los bumpeados se resaltan con 🔥.
- Overlay desactivable con `?raw=1`. CSS/JS externos para evitar bloqueos CSP.

Arranque rápido (con publicación/despliegue habilitados):

```bash
REMOTE_USER=root REMOTE_HOST=<SERVER_IP> \
PUBLIC_READS_URL_BASE=https://domingogallardo.com/read \
PORT=8000 SERVE_DIR="/Users/domingo/⭐️ Documentación" \
python utils/serve_docs.py
```

Acciones y atajos del overlay:
- Bump: botón o `b` (también ⌘/Ctrl+B)
- Unbump: botón o `u` (también ⌘/Ctrl+U)
- Ir al listado (carpeta): `l`
- Publicar: botón o `p` cuando el archivo está bumpeado y no publicado
- Despublicar: botón o `d` cuando el archivo ya está publicado
 - Procesado: botón o `x` cuando el archivo está bumpeado y publicado; realiza Unbump + añade el fichero a `web/public/read/read_posts.md` + despliegue.

### Flujo de estados (UI)

- S0 — Unbumped + No publicado: solo muestra Bump.
- S1 — Bumped + No publicado: muestra Unbump y Publicar.
- S2 — Publicado: muestra Despublicar y, si además está bumped, también Procesado.
- Reglas de validación:
  - Publicar requiere que el archivo esté bumped y no publicado.
  - Mientras esté publicado, no se permite (ni se muestra) Bump/Unbump.
  - El servidor rechaza `bump`/`unbump_now` si el archivo está publicado, evitando “Publicado + Unbumped”.
  - Este flujo aplica al overlay (HTML) y al índice (PDFs).

Publicar/Despublicar:
- Publicar copia el `.html` abierto o un `.pdf` (desde el índice) a `web/public/read/` preservando `mtime` y lanza `web/deploy.sh`.
- Despublicar elimina ese archivo de `web/public/read/` y lanza `web/deploy.sh`.
- Estados en la UI: “⏳ publicando…” / “⏳ despublicando…”, botón deshabilitado durante la operación, y confirmación con toast. Si defines `PUBLIC_READS_URL_BASE`, el toast incluye enlace “Ver”.
- Visibilidad: “Publicar” aparece si el archivo está bumpeado y aún no existe en `web/public/read/`. “Despublicar” aparece si ya existe.

Procesado:
- Disponible cuando el fichero está bumpeado y publicado.
- Al pulsar, hace Unbump del fichero local, lo añade (idempotente, como primera línea) a `web/public/read/read_posts.md` y lanza el deploy. Así, en `/read/` dejará de aparecer arriba y pasará a la sección inferior (bajo `<hr/>`) como “completado”.

Variables de entorno:
- Básicas: `PORT` (8000), `SERVE_DIR` (ruta base), `BUMP_YEARS` (100)
- Publicación (local):
  - `PUBLIC_READS_DIR` (por defecto `web/public/read`)
  - `DEPLOY_SCRIPT` (por defecto `web/deploy.sh`)
  - `PUBLIC_READS_URL_BASE` (ej. `https://domingogallardo.com/read` para el enlace “Ver” del overlay)
- Deploy: `REMOTE_USER` y `REMOTE_HOST` (requeridos por `web/deploy.sh`; el script hereda estas variables y debe ser ejecutable con `chmod +x web/deploy.sh`)
 - Deploy (opcional, gestión de BasicAuth): si defines `HTPASSWD_USER` y `HTPASSWD_PSS`, el deploy actualizará `/opt/web-domingo/nginx/.htpasswd` en el host generando un hash bcrypt (la contraseña viaja por `stdin`, no se muestra en `argv`).

Listado estático en el deploy:
- `web/deploy.sh` genera `read.html` para `/read/` (HTML/PDF) con dos zonas:
  - Arriba: listado por `mtime` desc de todos los ficheros que no estén en `read_posts.md`.
  - Separador `<hr/>` + abajo: los ficheros listados en `web/public/read/read_posts.md` (uno por línea; se permiten viñetas `- ` o `* ` y comentarios `#`). Esta sección representa artículos/PDFs ya leídos y estudiados (completados).

Generación local del índice:
- `python utils/build_read_index.py` (opcional para previsualizar sin desplegar)
- Edita `web/public/read/read_posts.md` para mover entradas a la sección inferior (completados).

Solución de problemas:
- “Publicar” no aparece: el archivo no está bumpeado o ya existe en `PUBLIC_READS_DIR`. Comprueba `mtime` y que el nombre no exista en destino.
- “Despublicar” no aparece: el archivo no está en `PUBLIC_READS_DIR` (detección por nombre). Revisa `PUBLIC_READS_DIR` efectivo.
- Error al publicar/desplegar: mira la consola de `serve_docs.py` para el detalle. Asegura `chmod +x web/deploy.sh` y exporta `REMOTE_USER`/`REMOTE_HOST`.
- Toast sin enlace “Ver”: define `PUBLIC_READS_URL_BASE`.
- `read.html` no cambia: el deploy lo regenera. Fuerza recarga. Verifica que `web/deploy.sh` terminó sin errores.

## 📌 Scripts principales

| Script | Función |
|--------|---------|
| `process_documents.py` | Script principal - Pipeline completo o parcial |
| `md_to_html.py` | Convierte archivos .md a HTML con márgenes |
| `pipeline_manager.py` | Coordinación de procesadores |
| `instapaper_processor.py` | Descarga y procesa artículos web |
| `podcast_processor.py` | Procesa transcripciones de Snipd |
| `tweet_processor.py` | Procesa colecciones de tweets |
| `pdf_processor.py` | Organiza PDFs |
| `utils.py` | Utilidades comunes |
| `utils/build_read_index.py` | Genera `web/public/read/read.html` usando `read_posts.md` |

### Utilidades adicionales
- `utils/serve_docs.py` — ver sección “Servidor web local”.
- `utils/rebuild_historial.py` - Reconstruir historial
- `utils/update_font.py` - Actualizar tipografía en archivos HTML
- `utils/borrar_cortos.py` - Eliminar documentos cortos
- `utils/count-files.py` - Contar archivos
- `utils/random-post.py` - Post aleatorio
- `utils/bump.applescript` - Atajo AppleScript para subir archivos en Finder ajustando mtime
- `utils/un-bump.applescript` - Tal cual dice el título

## 🧪 Testing

```bash
pytest tests/ -v
```

Incluye una batería de tests para validar los procesadores y utilidades.


## 🌐 Infraestructura y despliegue (Docker/Nginx)

Sitio en producción: https://domingogallardo.com

Este repo incluye una configuración opcional para servir tu contenido procesado en un servidor propio:

- Directorio `web/` (infra):
  - `Dockerfile` y `nginx.conf`: Imagen Nginx (Alpine) que sirve HTML/PDF y expone `/read/` con listado automático; `read.html` se genera en el deploy ordenado por fecha (mtime desc). Provee `/data/` para ediciones vía PUT protegido con BasicAuth.
  - `docker-compose.yml` (solo local): monta `./public` y `./dynamic-data` en modo lectura (`:ro`) y expone `8080:80`.
  - `deploy.sh`: empaqueta y despliega al servidor remoto en `/opt/web-domingo` y levanta el contenedor `web-domingo`. Requiere `REMOTE_USER` y `REMOTE_HOST` (no se incluyen secretos en el repo).
  - `.dockerignore` para builds reproducibles.
- Seguridad y alcance:
  - El contenido público (`web/public/`) no se versiona: está ignorado en `.gitignore`. En GitHub sólo se publican los ficheros de configuración.
  - Guía completa (host Nginx con TLS + contenedor app): ver [README-infra.md](README-infra.md).
  - Playbook de operaciones del host: ver [OPS-PLAYBOOK.md](OPS-PLAYBOOK.md).

---

© 2025 Domingo Gallardo López
