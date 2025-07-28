# 📚 Pipeline de Documentación Personal

Sistema automatizado para recopilar, procesar y organizar documentos personales (artículos web, PDFs, podcasts) en carpetas estructuradas por años.

---

## ⚙️ Uso

```bash
# Pipeline completo
python process_documents.py [--year 2025]

# Solo convertir archivos .md a HTML
python md_to_html.py
```

El script principal procesa automáticamente:
- **Artículos de Instapaper** → `Posts/Posts <AÑO>/`
- **Podcasts de Snipd** (MD) → `Podcasts/Podcasts <AÑO>/`
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
- ✅ Márgenes aplicados para lectura cómoda

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
| `process_documents.py` | Script principal - Pipeline completo |
| `md_to_html.py` | Convierte archivos .md a HTML con márgenes |
| `pipeline_manager.py` | Coordinación de procesadores |
| `instapaper_processor.py` | Descarga y procesa artículos web |
| `podcast_processor.py` | Procesa transcripciones de Snipd |
| `pdf_processor.py` | Organiza PDFs |
| `utils.py` | Utilidades comunes |

### Utilidades adicionales
- `utils/serve_html.py` - Servidor web local
- `utils/rebuild_historial.py` - Reconstruir historial
- `utils/borrar_cortos.py` - Eliminar documentos cortos
- `utils/count-files.py` - Contar archivos
- `utils/random-post.py` - Post aleatorio

---

## 🧪 Testing

```bash
pytest tests/ -v
```

19 tests incluidos para validar todos los procesadores y utilidades.

---

© 2025 Domingo Gallardo López