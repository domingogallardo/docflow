# 📚 Pipeline de Documentación Personal

Sistema automatizado para recopilar, procesar y organizar documentos personales (artículos web, PDFs, podcasts, tweets) en carpetas estructuradas por años.

---

## ⚙️ Uso

```bash
# Pipeline completo
python process_documents.py [--year 2025]

# Solo procesar tweets y PDFs
python process_documents.py tweets pdfs

# Solo convertir archivos .md a HTML
python md_to_html.py
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
- ✅ Títulos generados automáticamente con IA
- ✅ Imágenes redimensionadas (max 300px ancho)
- ✅ Márgenes del 6% aplicados para mejor lectura
- ✅ Codificación HTML corregida
- ✅ Nombres de archivo limpio (sin caracteres problemáticos)

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
pip install requests beautifulsoup4 markdownify anthropic pillow pytest
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
- `utils/serve_html.py` - Servidor web local (lista directorios, `.html` y `.pdf` ordenados por mtime desc.)
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

31 tests incluidos para validar todos los procesadores y utilidades.

---

© 2025 Domingo Gallardo López