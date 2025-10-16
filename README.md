# 📚 docflow — Pipeline de Documentación Personal (versión resumida)

docflow automatiza **recolectar → procesar → priorizar (bump) → leer → publicar → marcar como completado** tus documentos (artículos, podcasts, tweets, Markdown y PDFs) en una estructura por años.

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
python process_documents.py tweets pdfs
python process_documents.py images
python process_documents.py md
```
- Instapaper → HTML/MD limpios (título con IA, márgenes, metadatos, nombres saneados).  
- Snipd → HTML limpio con tipografía del sistema y botones de audio.  
- Tweets → HTML estilizado.  
- Markdown → conversión a HTML con márgenes + título IA (si hay API) + archivado en `Posts/Posts <AÑO>/`.  
- PDFs → organización anual.  
- Imágenes → copia anual + `gallery.html` scrolleable por año (JPG/PNG/WebP/TIFF/GIF/BMP).

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
│   ├── titles_done_instapaper.txt
│   └── titles_done_markdown.txt
├── Posts/Posts <AÑO>/
├── Podcasts/Podcasts <AÑO>/
├── Tweets/Tweets <AÑO>/
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
