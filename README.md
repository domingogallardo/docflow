# 📚 docflow — Pipeline de Documentación Personal (versión resumida)

docflow automatiza **recolectar → procesar → priorizar (bump) → leer → publicar → marcar como completado** tus documentos (artículos, podcasts, Markdown y PDFs) en una estructura por años.

- 🚀 **Rápido de arrancar**: un par de comandos y estás procesando.
- 🧭 **Flujo claro**: bump/unbump para priorizar; overlay web local para acciones; deploy a `/read/` en tu web pública.
- 🌐 **Infra separada**: la guía de despliegue vive en **README-infra.md** (doble Nginx host+contenedor, TLS, BasicAuth para PUT en `/data`).

---

## 🔧 Requisitos mínimos

- **Python 3.10+**  
- Instala dependencias básicas:
  ```bash
  pip install requests beautifulsoup4 markdownify openai pillow pytest markdown
  ```
- Para capturar tweets directamente:
  ```bash
  pip install playwright
  playwright install chromium
  ```
- Variables de entorno si usas funciones externas / deploy:
  ```bash
  export OPENAI_API_KEY="..."              # títulos Instapaper (opcional)
  export INSTAPAPER_USERNAME="..."         # opcional
  export INSTAPAPER_PASSWORD="..."         # opcional
  export REMOTE_USER="root"                # para publicar/desplegar
  export REMOTE_HOST="1.2.3.4"             # para publicar/desplegar
  ```

---

## ⚙️ Uso básico

### 1) Procesar contenido
```bash
# Pipeline completo (año opcional)
python process_documents.py all [--year 2025]

# Selectivo
python process_documents.py tweets
python process_documents.py images
python process_documents.py md
```
- Instapaper → HTML/MD limpios (título con IA, márgenes, metadatos, nombres saneados). Incluye los tweets guardados en Instapaper y mantiene la palabra `Tweet` en los nombres generados.  
- Snipd → HTML limpio con tipografía del sistema y botones de audio.  
- Markdown → conversión a HTML con márgenes + título IA (si hay API) + archivado en `Posts/Posts <AÑO>/`.  
- PDFs → organización anual.  
- Imágenes → copia anual + `gallery.html` scrolleable por año (JPG/PNG/WebP/TIFF/GIF/BMP).

### 1ter) Cola de tweets (editor remoto)
Abre `https://domingogallardo.com/editor`, pega una URL por línea (puedes usar `#` para comentarios) y guarda. Después ejecuta:
```bash
python process_documents.py tweets
# o dentro del pipeline completo (se ejecuta al inicio de `all`)
python process_documents.py all
```
El pipeline descarga `https://domingogallardo.com/data/nota.txt`, convierte cada URL en un `.md` con título, enlace, foto de perfil e imágenes, descarta las estadísticas (views/likes), genera el `.html`, aplica título con IA y mueve el par `.md/.html` a `Posts/Posts <AÑO>/`. El fichero remoto no se vacía: sigue disponible para revisarlo o reutilizarlo cuando quieras.

> Si tu editor remoto está protegido con BasicAuth, define `TWEET_EDITOR_USER` y `TWEET_EDITOR_PASS` antes de ejecutar el comando (por ejemplo en tu shell o `.env` local). El script ya apunta a `https://domingogallardo.com/data/nota.txt` por defecto.

### 1qu) Capturar tweets individuales
Si quieres archivar un tweet sin pasar por Instapaper, genera un Markdown listo para `Incoming/`:
```bash
python utils/tweet_to_markdown.py https://x.com/usuario/status/123456789
# Opcional: elegir carpeta o nombre
python utils/tweet_to_markdown.py <URL> --output-dir ~/Documentos/Incoming --filename "Tweet - demo.md"
```
El script usa Playwright (Chromium headless) y guarda un `.md` con título, enlace, foto de perfil y cuerpo sin estadísticas (views/likes), seguido de las imágenes adjuntas del post. Luego ejecuta `process_documents.py tweets` para que el pipeline los convierta a HTML y los archive en `Posts/`.

### 1bis) Limpiar HTML copiado antes de pegar en Obsidian
- Copia el fragmento desde el navegador.
- Ejecuta `mdclip` (o `python utils/clipboard_cleaner.py`).
- Vuelve a pegar en Obsidian: obtendrás listas compactas (sin saltos extra) y el portapapeles ya trae Markdown limpio.

> **Tip**: añade `$(git rev-parse --show-toplevel)/bin` a tu `PATH` para llamar a `mdclip` desde cualquier repo.

### 2) Servidor web local (overlay con acciones)
```bash
PORT=8000 SERVE_DIR="/ruta/a/⭐️ Documentación" python utils/serve_docs.py
```
- Bump/Unbump, Publicar/Despublicar, Procesado (atajos: `b`, `u`, `p`, `d`, `x`).
- Listado por **mtime desc** mostrando solo HTML/PDF; los bumpeados se marcan 🔥.
- ⭐ en **Instapaper** ⇒ **bump automático** del HTML procesado.

### 3) Publicar a la web pública (`/read/`)
- Desde el overlay: **Publicar** copia a `web/public/read/` e invoca `web/deploy.sh`.
- El deploy genera `read.html` con:
  - **Arriba**: no completados (orden mtime desc).
  - **Abajo** (bajo `<hr/>`): los listados en `web/public/read/read_posts.md` (completados).

> La **infra** (Nginx host + contenedor) y TLS están documentadas en **README-infra.md**.

---

## 📂 Estructura de directorios (simplificada)

```
⭐️ Documentación/
├── Incoming/
│   ├── processed_history.txt
│   └── ...
├── Posts/Posts <AÑO>/
├── Podcasts/Podcasts <AÑO>/
├── Pdfs/Pdfs <AÑO>/
├── Images/Images <AÑO>/
└── ...
```

---

## 🧭 Flujo de trabajo (en 5 líneas)

1. Recolecta en `Incoming/` (o carpetas fuente) y ejecuta el pipeline.  
2. Marca con **⭐ en Instapaper** para **bump** automático del HTML procesado.  
3. Lee en el **servidor local** y usa el overlay para *Publicar/Despublicar*.  
4. Captura citas en `/read/` con el botón **❝ Copiar cita** (usa **Text Fragments** y conserva los enlaces en Markdown).  
5. Cuando termines, pulsa **Procesado** → unbump + añade a `read_posts.md` + deploy.

---

## 🔗 Documentación ampliada

- **Guía completa del flujo y comandos** → `docs/GUIA.md`  
- **Infra y despliegue (Docker/Nginx, TLS, BasicAuth)** → `docs/README-infra.md`

---

## 🧪 Tests rápidos

```bash
pytest tests/ -v
```

---

© 2025 Domingo Gallardo López
