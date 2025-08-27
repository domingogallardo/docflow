# 📚 docflow — Pipeline de Documentación Personal

docflow es un sistema automatizado para recopilar, procesar y organizar documentos personales (artículos web, PDFs, podcasts, tweets) en carpetas estructuradas por años.

---

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

---

## 🎯 Resultado del procesamiento

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

---

## 📂 Estructura

```
⭐️ Documentación/
├── Incoming/               # Archivos nuevos
├── Posts/Posts <AÑO>/      # Artículos procesados
├── Podcasts/Podcasts <AÑO>/ # Podcasts procesados
├── Tweets/Tweets <AÑO>/    # Tweets procesados
├── Pdfs/Pdfs <AÑO>/        # PDFs organizados
└── Historial.txt           # Registro histórico
```

---

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
```

---

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

### Utilidades adicionales
- `utils/serve_docs.py` - Servidor local de lectura para `.html` y `.pdf` con:
  - Overlay en páginas HTML para hacer Bump/Unbump del archivo abierto (botón y atajos: b / u / l y ⌘/Ctrl+B, ⌘/Ctrl+U)
  - Publicar/Despublicar al sitio público desde el overlay:
    - Publicar: copia el HTML activo a `web/public/posts/` preservando `mtime` y ejecuta `web/deploy.sh`.
    - Despublicar: elimina el HTML de `web/public/posts/` y ejecuta `web/deploy.sh`.
    - Atajos: `p` para Publicar (si está bumped y no publicado) y `d` para Despublicar (si ya está publicado).
    - UI: indicador de progreso (“⏳ publicando…/despublicando…”) y notificación tipo toast; opcionalmente añade enlace “Ver” si `PUBLIC_POSTS_URL_BASE` está definido.
    - Lógica de visibilidad: “Publicar” aparece solo si el archivo está bumped y aún no existe en `web/public/posts/`. “Despublicar” aparece si ya existe.
  - Listado de carpetas/archivos ordenado por mtime (desc), resaltando ficheros bump con 🔥
  - Assets del overlay servidos como ficheros externos (evita CSP inline). Desactivar overlay con `?raw=1`
  - Config por entorno: `PORT` (8000), `SERVE_DIR` (ruta base), `BUMP_YEARS` (100)
  - Config extra (publicación):
    - `PUBLIC_POSTS_DIR` (destino local, por defecto `web/public/posts` dentro del repo)
    - `DEPLOY_SCRIPT` (script de despliegue, por defecto `web/deploy.sh`)
    - `PUBLIC_POSTS_URL_BASE` (base pública para el toast, ej. `https://domingogallardo.com/posts`)
    - Requiere exportar `REMOTE_USER` y `REMOTE_HOST` para que `web/deploy.sh` pueda desplegar.
- `utils/rebuild_historial.py` - Reconstruir historial
- `utils/update_font.py` - Actualizar tipografía en archivos HTML
- `utils/borrar_cortos.py` - Eliminar documentos cortos
- `utils/count-files.py` - Contar archivos
- `utils/random-post.py` - Post aleatorio
- `utils/bump.applescript` - Atajo AppleScript para subir archivos en Finder ajustando mtime
- `utils/un-bump.applescript` - Tal cual dice el título

---

## 🧪 Testing

```bash
pytest tests/ -v
```

32 tests incluidos para validar todos los procesadores y utilidades.

---

## 🌐 Infraestructura y despliegue (Docker/Nginx)

Sitio en producción: https://domingogallardo.com

Este repo incluye una configuración opcional para servir tu contenido procesado en un servidor propio:

- Directorio `web/` (infra):
  - `Dockerfile` y `nginx.conf`: Imagen Nginx (Alpine) que sirve HTML/PDF y expone `/docs/` y `/posts/` mediante índices estáticos generados en el deploy, ordenados por fecha (mtime desc). Provee `/data/` para ediciones vía PUT protegido con BasicAuth.
  - `docker-compose.yml` (solo local): monta `./public` y `./dynamic-data` en modo lectura (`:ro`) y expone `8080:80`.
  - `deploy.sh`: empaqueta y despliega al servidor remoto en `/opt/web-domingo` y levanta el contenedor `web-domingo`. Requiere `REMOTE_USER` y `REMOTE_HOST` (no se incluyen secretos en el repo).
  - `.dockerignore` para builds reproducibles.
- Seguridad y alcance:
  - El contenido público (`web/public/`) no se versiona: está ignorado en `.gitignore`. En GitHub sólo se publican los ficheros de configuración.
  - Guía completa (host Nginx con TLS + contenedor app): ver `README-infra.md`.

Nota: si quieres edición autenticada de `/data/` en el servidor, crea y monta un `.htpasswd` en `/opt/web-domingo/nginx/.htpasswd` (fuera del repo). Por defecto, en `docker-compose` local `/data` se monta en solo lectura.

### 📤 Publicar desde el servidor local (resumen rápido)

```bash
# Arrancar el servidor local con publicación habilitada
REMOTE_USER=root REMOTE_HOST=<SERVER_IP> \
PUBLIC_POSTS_URL_BASE=https://domingogallardo.com/posts \
PORT=8000 SERVE_DIR="/Users/domingo/⭐️ Documentación" \
python utils/serve_docs.py
```

- Abre un `.html` y usa:
  - `b` para Bump, `u` para Unbump, `l` para ir al listado
  - `p` para Publicar (si bumped y no publicado) → copia + deploy
  - `d` para Despublicar (si publicado) → borra + deploy

El índice de `/posts/` y `/docs/` se regenera en el deploy, mostrando los archivos ordenados por `mtime` descendente (los bumpeados aparecen arriba).

---

## ⭐ Instapaper: Artículos Destacados

- Detección: se identifica si un artículo está marcado con estrella tanto en el listado (`/u/<página>`) como en la página de lectura (`/read/<id>`). Se consideran:
  - Estrella al inicio del `<title>` o del `h1` visible (⭐, ⭐️, ★, ✪, ✭).
  - Indicadores de UI: enlaces `unstar`, controles con `aria-pressed=true`, clases `starred/on/filled`, o SVGs relacionados.
- Normalización del título: cualquier prefijo de estrella en el título se elimina para nombrar y mostrar sin el emoji.
- Salida HTML: si está destacado, se añade
  - `<meta name="instapaper-starred" content="true">`
  - Atributo en la raíz: `<html data-instapaper-starred="true">`
  - Comentario de marca: `<!-- instapaper_starred: true -->`
- Salida Markdown: se incluye front matter YAML al inicio:
  - `---\ninstapaper_starred: true\n---`

### Cómo preparar el artículo en Instapaper
- Basta con añadir una estrella (⭐) al inicio del título del artículo en Instapaper. Con eso es suficiente para que el pipeline lo detecte como destacado.

### Bump automático de HTML destacados
- Los artículos destacados se bumpean automáticamente al terminar el procesamiento: se ajusta su `mtime` al futuro para que queden arriba en listados ordenados por fecha (por ejemplo, en Finder o en el servidor `utils/serve_docs.py`).
- En el servidor de lectura (`utils/serve_docs.py`), los archivos bumpeados se resaltan con 🔥 y puedes hacer Unbump desde el overlay (atajos: `u` o ⌘/Ctrl+U).

Uso downstream:
- Filtrar Markdown por front matter (`instapaper_starred: true`) en tu generador estático o script.
- Para HTML, buscar el meta `<meta name="instapaper-starred" content="true">` o el atributo `data-instapaper-starred="true"` para resaltar o priorizar.

- Publicación opcional: puedes copiar manualmente una selección de HTML (p. ej., los bumpeados) a `web/public/posts/` para exponerlos en la web. El contenedor los sirve bajo `/posts/` con un índice estático generado automáticamente (orden mtime desc), y así puedes referenciarlos fácilmente desde Obsidian.

---

© 2025 Domingo Gallardo López
