# 📚 Pipeline de Documentación Personal

Sistema automatizado para recopilar, procesar y organizar documentos personales (artículos web, PDFs, podcasts) en carpetas estructuradas por años.

---

## ⚙️ Uso

```bash
python process_documents.py [--year 2025]
```

El script procesa automáticamente:
- **Artículos de Instapaper** → `Posts/Posts <AÑO>/`
- **Podcasts de Snipd** (MD) → `Podcasts/Podcasts <AÑO>/`
- **PDFs** → `Pdfs/Pdfs <AÑO>/`

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
