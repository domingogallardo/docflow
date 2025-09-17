# docflow — Guía ampliada

> Este documento amplía el README resumido. Mantiene los detalles operativos para trabajar a diario con docflow. La guía de infra y TLS está en **README-infra.md**.

## Índice
1. [Conceptos clave](#conceptos-clave)
2. [Comandos esenciales](#comandos-esenciales)
3. [Flujo de trabajo detallado](#flujo-de-trabajo-detallado)
4. [Servidor web local (`utils/serve_docs.py`)](#servidor-web-local-utilsservedocspy)
5. [Publicación web (`/read/`) y `read.html`](#publicación-web-read-y-readhtml)
6. [Capturar citas con Text Fragments](#capturar-citas-con-text-fragments)
7. [Variables de entorno](#variables-de-entorno)
8. [Resumen de scripts por fase](#resumen-de-scripts-por-fase)
9. [Solución de problemas](#solución-de-problemas)
10. [Infra y verificación](#infra-y-verificación)

---

## Conceptos clave

- **Bump/Unbump**: ajustar el `mtime` de un archivo para priorizarlo en listados por fecha.  
  - Automático si el título de Instapaper empieza por **⭐**.  
  - Manual con overlay o `utils/bump.applescript` / `utils/un-bump.applescript` (Finder).
- **Overlay**: UI superpuesta en HTML servidos localmente para ejecutar acciones (bump/unbump, publicar, etc.).
- **Completados**: archivos añadidos a `web/public/read/read_posts.md`; aparecen **bajo `<hr/>`** en `/read/`.

---

## Comandos esenciales

```bash
# Pipeline completo o por tipos
python process_documents.py all [--year AAAA]
python process_documents.py instapaper podcasts tweets pdfs

# Convertir Markdown a HTML
python md_to_html.py

# Servir HTML/PDF con overlay
PORT=8000 SERVE_DIR="/ruta/a/⭐️ Documentación" python utils/serve_docs.py
```

Dependencias recomendadas:
```bash
pip install requests beautifulsoup4 markdownify anthropic pillow pytest markdown
```

---

## Flujo de trabajo detallado

1) **Recolectar → Estructura base**  
Guarda tus fuentes en `⭐️ Documentación/Incoming/` (o en sus carpetas de origen) y el pipeline las ordenará en carpetas por año: `Posts/Posts <AÑO>/`, `Podcasts/Podcasts <AÑO>/`, `Tweets/Tweets <AÑO>/`, `Pdfs/Pdfs <AÑO>/`, `Images/Images <AÑO>/`.

2) **Procesar → Pipeline**  
```bash
python process_documents.py all --year 2025
# o selectivo:
python process_documents.py tweets pdfs
python process_documents.py images
```
- Instapaper (HTML + MD limpios, título con IA, márgenes, metadatos y nombres de archivo sanos).  
- Podcasts Snipd (MD → HTML limpio, tipografía del sistema, botones de audio).  
- Tweets (MD → HTML estilizado).  
- PDFs (organización anual).  
- Imágenes (copia anual + galería `gallery.html` con JPG/PNG/WebP/TIFF/GIF/BMP).  
Todo esto lo orquesta `process_documents.py` y procesadores específicos `*_processor.py`.

3) **Priorizar para leer → Bump/Unbump**  
- **Marca con ⭐ en Instapaper**: si añades una estrella al **título** del artículo en Instapaper, el pipeline **propaga** ese “destacado” a HTML/MD y **bumpea automáticamente** el HTML (ajusta su `mtime` al futuro) para que quede arriba en listados por fecha.  
- También tienes atajos de Finder (`utils/bump.applescript`, `utils/un-bump.applescript`) si necesitas subir/bajar manualmente elementos.

4) **Leer localmente y gestionar estado → `utils/serve_docs.py`**  
Arranca el servidor local de lectura:  
 ```bash
PORT=8000 SERVE_DIR="/ruta/a/⭐️ Documentación" python utils/serve_docs.py
```
- Overlay en páginas **HTML** con botones **Bump / Unbump / Publicar / Despublicar / Procesado** y **atajos de teclado**.  
- El listado solo muestra carpetas, HTML y PDFs (los `.md` se ocultan) ordenados por **mtime desc**.  
- Reglas de estado:  
  - **S0** Unbumped + No publicado → muestra *Bump*.  
  - **S1** Bumped + No publicado → muestra *Unbump* y *Publicar*.  
  - **S2** Publicado → muestra *Despublicar* y, si además está bumped, *Procesado*.  
- **Reglas de validación**:  
  - Publicar **requiere** que el archivo esté **bumped** y **no publicado**.  
  - Mientras esté **publicado**, no se permite (ni se muestra) **Bump/Unbump**.  
  - El servidor rechaza `bump`/`unbump_now` si el archivo está publicado.

5) **Publicar en la web pública (`/read/`)**  
Desde el overlay, **Publicar** copia el `.html` o `.pdf` a `web/public/read/` y lanza el **deploy** (`web/deploy.sh`). El deploy construye la imagen Nginx del contenedor, sube los assets al servidor remoto y deja `/read/` servido con un índice **ordenado por fecha (mtime desc)**. Puedes parametrizar `REMOTE_USER`/`REMOTE_HOST` vía entorno.

6) **Capturar citas en páginas publicadas (Text Fragments)**  
En `/read/`, se inyecta un botón flotante **❝ Copiar cita** que, al seleccionar texto, copia una cita en **Markdown** con enlace que incluye **Text Fragments** (`#:~:text=`). Esto facilita pegar citas directamente en Obsidian manteniendo el salto a la posición exacta del texto. (*Script*: `article.js`).

7) **Cosechar / Marcar como “completado”**  
Cuando termines de estudiar un documento publicado y (opcionalmente) bumped, usa **Procesado** en el overlay: hace **Unbump**, añade el nombre del fichero a `web/public/read/read_posts.md` y despliega. En el índice público `/read/` aparecerá **bajo un `<hr/>`** en la sección de “completados”, respetando el orden del fichero `read_posts.md`.

8) **Infra y verificación**  
El despliegue usa **doble Nginx**: proxy con TLS en el **host** y Nginx **dentro del contenedor** sirviendo estáticos; `/data/` permite PUT con BasicAuth (host-montado). Verifica `/read/` con `curl` tras el deploy (ver comandos más abajo).

> Tip: si quieres previsualizar el índice sin desplegar, usa `python utils/build_read_index.py`; en deploy se regenerará automáticamente.

---

## Servidor web local (`utils/serve_docs.py`)

- **Acciones**: Bump (`b`), Unbump (`u`), Publicar (`p`), Despublicar (`d`), Procesado (`x`), Listado (`l`).  
- **Estados**: S0/S1/S2 (ver arriba).  
- **Parámetros**:
  - `PORT` (por defecto 8000)
  - `SERVE_DIR` (ruta base)
  - `BUMP_YEARS` (años al futuro para el bump; por defecto 100)
  - Publicación local:
    - `PUBLIC_READS_DIR` (por defecto `web/public/read`)
    - `DEPLOY_SCRIPT` (por defecto `web/deploy.sh`)
    - `PUBLIC_READS_URL_BASE` (para enlazar el “Ver” tras publicar)

---

## Publicación web (`/read/`) y `read.html`

- El deploy **genera** `read.html` con **dos zonas**:
  - **Arriba**: todo lo **no** listado en `read_posts.md` (orden **mtime desc**).
  - **Abajo**: elementos listados en `web/public/read/read_posts.md` (uno por línea; admite `- ` o `* ` y comentarios `#`).  
- Servido por Nginx del contenedor con *autoindex* activo (ver **README-infra.md**).

Verificación rápida:
```bash
curl -I https://<tu_dominio>/read/
curl -s https://<tu_dominio>/read/ | head -n 40
```

---

## Capturar citas con Text Fragments

- Las páginas en `/read/` inyectan un botón **❝ Copiar cita** (`article.js`).  
- Selecciona un texto y copia una cita en **Markdown** con un enlace que incluye `#:~:text=` para saltar a la posición exacta.  
- El botón solo aparece si hay texto seleccionado y muestra *toast* de éxito/error.
- iOS/iPadOS: se captura tempranamente la selección para evitar que se pierda al tocar el botón. Si el portapapeles falla (p. ej., navegación privada), verás un toast de error; el salto con `#:~:text=` lo gestiona el navegador.

---

## Variables de entorno

```bash
# Integraciones
ANTHROPIC_API_KEY=...          # títulos Instapaper (opcional)
INSTAPAPER_USERNAME=...        # opcional
INSTAPAPER_PASSWORD=...        # opcional

# Publicación/Deploy
REMOTE_USER=root
REMOTE_HOST=1.2.3.4
PUBLIC_READS_URL_BASE=https://<tu_dominio>/read

# Servidor local
PORT=8000
SERVE_DIR="/ruta/a/⭐️ Documentación"
BUMP_YEARS=100

# Opcional: gestión BasicAuth en deploy
HTPASSWD_USER=editor
HTPASSWD_PSS='contraseña'
```

---

## Resumen de scripts por fase

- **Procesar**: `process_documents.py`, `instapaper_processor.py`, `podcast_processor.py`, `tweet_processor.py`, `pdf_processor.py`.  
- **Leer/priorizar/publicar (local)**: `utils/serve_docs.py` (overlay + acciones), `utils/bump.applescript`, `utils/un-bump.applescript`.  
- **Publicar (remoto)**: `web/deploy.sh` (genera `read.html` por mtime desc y respeta `read_posts.md` para la zona de completados).  
- **Capturar citas en `/read/`**: `article.js` (botón **❝ Copiar cita**, Markdown + `#:~:text=`).  
- **Previsualizar índice sin deploy**: `utils/build_read_index.py`.

---

## Solución de problemas

- **No aparece “Publicar”** → el archivo no está **bumped** o ya existe en `PUBLIC_READS_DIR`. Comprueba `mtime` y nombres.  
- **No aparece “Despublicar”** → el archivo no está en `PUBLIC_READS_DIR` (detección por nombre).  
- **`read.html` no cambia** → el deploy lo regenera; fuerza recarga y revisa salida de `web/deploy.sh`.  
- **Error en deploy** → verifica permisos de `web/deploy.sh` (`chmod +x`) y que `REMOTE_USER`/`REMOTE_HOST` están definidos.  
- **Toast sin enlace “Ver”** → define `PUBLIC_READS_URL_BASE`.  

---

## Infra y verificación

La **infra** usa doble Nginx (TLS en host + Nginx en contenedor) y BasicAuth para PUT en `/data` con `.htpasswd` montado en host. Para detalles y hardening, consulta **README-infra.md**.

Verificación con `curl` y logs:
```bash
curl -I https://<tu_dominio>/read/
journalctl -u nginx --since today
docker logs -n 200 web-domingo
```

---

© 2025 Domingo Gallardo López
