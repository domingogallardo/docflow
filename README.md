# 📚 Pipeline de Documentación Personal

Este proyecto automatiza la recopilación, procesamiento y organización de documentos personales (artículos web, PDFs, podcasts, etc.) en un sistema estructurado por años. Utiliza scripts en Python para automatizar tareas frecuentes como descarga, conversión de formatos, generación de títulos atractivos con inteligencia artificial y gestión histórica de archivos.

El pipeline incluye **validación automática de credenciales**, **mensajes informativos** cuando no hay archivos que procesar, y es **robusto ante fallos** - continúa procesando archivos locales aunque falle algún servicio externo.

---

## 🚦 Flujo de procesamiento de documentos

### 1. **Preparación: ¿De dónde parten los documentos?**
- **En el directorio `Incoming/` se colocan manualmente:**
  - Archivos PDF que quieras organizar.
  - Archivos Markdown exportados desde Snipd (transcripciones de podcasts).
- **Además:**
  - Los artículos guardados previamente en tu cuenta de Instapaper están listos para ser descargados y procesados automáticamente por el pipeline. El sistema **valida automáticamente las credenciales** y muestra mensajes claros si hay problemas de conexión.

De este modo, el pipeline parte de tres fuentes principales de documentos originales:
- PDFs (manual, en `Incoming/`)
- Podcasts exportados de Snipd (manual, en `Incoming/`)  
- Artículos web guardados en Instapaper (descarga automática con validación, HTML generado en `Incoming/`)

### 2. **Procesamiento de Podcasts (Snipd)**
- Se detectan primero los archivos Markdown exportados desde Snipd (contienen "Episode metadata" y "## Snips").
- **Pipeline especializado:**
  1. Limpieza (`clean_snip.py`): elimina HTML innecesario, show notes, enlaces de audio y la frase "Click to expand".
  2. Conversión a HTML (`md2html.py`).
  3. Añadir márgenes (`add_margin_html.py`).
- **Renombrado:**
  - Se extraen el título del episodio y el nombre del show de los metadatos.
  - Los archivos `.md` y `.html` se renombran con el formato: `Show - Episode title.md` / `.html`.  
  - **Se eliminan caracteres problemáticos** (`#`, `/`, etc.) para evitar conflictos con servidores locales.
- **Organización:**
  - Se mueven inmediatamente a la carpeta anual de podcasts: `Podcasts/Podcasts <AÑO>/`.
  - Así, **no pasan por el pipeline de posts normales** ni por la generación de títulos con IA.

### 3. **Procesamiento de Posts y PDFs (Pipeline regular)**
- Se procesan todos los archivos restantes en `Incoming/` (PDF, Markdown no-podcast y los HTML descargados automáticamente desde Instapaper).
- **Pipeline robusto y modular:**
  1. **Posts de Instapaper**: Procesados por `InstapaperProcessor` que maneja internamente:
     - Descarga de artículos desde Instapaper (con validación)
     - Conversión HTML → Markdown  
     - Corrección de codificación
     - Reducción de imágenes
     - Generación de títulos con IA
     - **Elimina caracteres problemáticos** para compatibilidad con servidores web
  2. **Aplicación de márgenes**: Script compartido `add_margin_html.py`
  3. **PDFs**: Procesados por `PDFProcessor` que los mueve directamente sin transformaciones
- **Organización:**
  - **Posts:** Los archivos procesados se renombran y se mueven a `Posts/Posts <AÑO>/`.
  - **PDFs:** Se mueven a `Pdfs/Pdfs <AÑO>/` manteniendo su nombre original.

### 4. **Transparencia del proceso**
- **Cada script muestra mensajes informativos** cuando no hay archivos que procesar.
- **Validación automática** de credenciales con mensajes de error claros.
- **Pipeline tolerante a fallos**: Si falla la descarga de Instapaper, continúa procesando PDFs y otros archivos locales.

### 5. **Registro histórico**
- Todos los archivos procesados (posts, PDFs, podcasts) se registran en `Historial.txt` (los más recientes arriba).

---

## 📂 Estructura del proyecto

```
⭐️ Documentación/
├── Incoming/               # Archivos nuevos esperando procesamiento
├── Posts/
│   └── Posts <AÑO>/        # Posts procesados por años
├── Pdfs/
│   └── Pdfs <AÑO>/         # PDFs procesados por años (nombre original)
├── Podcasts/
│   └── Podcasts <AÑO>/     # Podcasts procesados por años (renombrados por metadatos)
└── Historial.txt           # Registro histórico, más nuevo arriba
```

---

## 🛠 Requisitos

* **Python 3.10+**

* Librerías Python:

  ```bash
  pip install requests beautifulsoup4 markdownify anthropic pillow
  ```

* Librerías de desarrollo (opcional, para tests):

  ```bash
  pip install pytest
  ```

* **Claves API y credenciales**:

  * [Anthropic Claude 3 API](https://console.anthropic.com/settings/keys)
  * Credenciales de Instapaper (para descarga automática)

Guarda tus claves API y credenciales en variables de entorno:

```bash
export ANTHROPIC_API_KEY="tu_clave"
export INSTAPAPER_USERNAME="tu_usuario"
export INSTAPAPER_PASSWORD="tu_contraseña"
```

---

## ⚙️ Uso

Para procesar documentos nuevos:

```bash
python process_documents.py [--year 2025]
```

* El año por defecto es el actual, pero se puede especificar de dos formas:
  * Con el flag `--year`: `python process_documents.py --year 2025`
  * Con variable de entorno: `export DOCPIPE_YEAR="2025"`

---

## 📌 Scripts incluidos

| Script                       | Función                                                        |
| ---------------------------- | -------------------------------------------------------------- |
| `process_documents.py`       | **Script principal** - Ejecuta todo el pipeline completo      |
| `document_processor.py`      | **Arquitectura modular** - Clases principales del sistema     |
| `instapaper_processor.py`    | **Procesador unificado** - Maneja todo el pipeline de Instapaper |
| `pdf_processor.py`           | **Procesador de PDFs** - Mueve PDFs sin procesamiento adicional |
| `clean_snip.py`              | Limpia archivos Markdown exportados desde Snipd                |
| `md2html.py`                 | Convierte archivos Markdown a HTML                             |
| `add_margin_html.py`         | Añade márgenes estándar al HTML (compartido por podcasts y posts) |
| `utils.py`                   | Utilidades comunes (detección podcasts, renombrado, etc.)     |
| `utils/serve_html.py`        | Servidor web que lista archivos .html desde una carpeta dada   |
| `utils/rebuild_historial.py` | Reconstruye por completo `Historial.txt` por fecha de creación |
| `utils/borrar_cortos.py`     | Elimina documentos demasiado cortos                            |
| `utils/count-files.py`       | Cuenta los archivos existentes                                 |
| `utils/random-post.py`       | Selecciona aleatoriamente un post (requiere archivo `Posts.txt`) |

### 🏗️ Arquitectura Modular

El sistema está organizado en **procesadores especializados**:

- **`InstapaperProcessor`**: Maneja descarga, conversión HTML→MD, corrección de encoding, reducción de imágenes y generación de títulos con IA
- **`PDFProcessor`**: Procesa PDFs moviéndolos directamente (sin transformaciones)  
- **`DocumentProcessor`**: Orquesta todo el sistema y coordina los procesadores

**Scripts compartidos**: Solo `add_margin_html.py` se ejecuta independientemente porque lo usan tanto podcasts como posts.

---

## 🧪 Testing

El proyecto incluye una suite de tests automatizados para garantizar la robustez:

```bash
# Ejecutar todos los tests
pytest tests/

# Ejecutar tests específicos
pytest tests/test_utils.py
pytest tests/test_clean_snip.py
pytest tests/test_document_processor.py

# Ejecutar con detalles
pytest tests/ -v
```

**Tests incluidos:**
- **Tests unitarios**: `extract_episode_title`, `is_podcast_file`, `clean_lines`
- **Tests de integración**: Pipeline completo con directorios temporales y mocks
- **Cobertura**: Funciones críticas de detección, renombrado y procesamiento

---

## 🔄 Reconstruir Historial

Si necesitas regenerar por completo el historial:

```bash
python utils/rebuild_historial.py
```

Este script genera un backup (`Historial.txt.bak`) antes de reconstruir el historial.

---

## 💡 Licencia

Este proyecto es para uso personal. Si deseas reutilizar o modificar partes del código, puedes hacerlo libremente.

---

© 2025 Domingo Gallardo López
