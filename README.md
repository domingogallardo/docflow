# 📚 Pipeline de Documentación Personal

Este proyecto automatiza la recopilación, procesamiento y organización de documentos personales (artículos HTML, PDFs, etc.) en un sistema estructurado por años. Utiliza scripts en Python para automatizar tareas frecuentes como descarga, conversión de formatos, generación de títulos atractivos con inteligencia artificial y gestión histórica de archivos.

---

## 🚀 ¿Qué hace exactamente?

El pipeline realiza automáticamente las siguientes tareas:

1. **Descarga artículos HTML** desde una cuenta de Instapaper.
2. **Convierte HTML en Markdown** usando `markdownify`.
3. **Corrige la codificación de caracteres** y el formato HTML.
4. **Ajusta automáticamente las imágenes** de gran tamaño.
5. **Genera automáticamente títulos descriptivos** para los artículos usando la API de Anthropic (Claude 3).
6. **Organiza los archivos procesados** en carpetas anuales (`Posts 2025`, `Pdfs 2025`, etc.).
7. **Mantiene un historial completo** en el fichero `Historial.txt`, mostrando primero los documentos más recientes.

---

## 📂 Estructura del proyecto

```
⭐️ Documentación/
├── Incoming/               # Archivos nuevos esperando procesamiento
├── Posts/
│   └── Posts <AÑO>/        # Posts procesados por años
├── Pdfs/
│   └── Pdfs <AÑO>/         # PDFs procesados por años
└── Historial.txt           # Registro histórico, más nuevo arriba
```

---

## 🛠 Requisitos

* **Python 3.10+**

* Librerías Python:

  ```bash
  pip install requests beautifulsoup4 markdownify anthropic pillow
  ```

* **Claves API**:

  * [Anthropic Claude 3 API](https://console.anthropic.com/settings/keys)

Guarda tus claves API en variables de entorno:

```bash
export ANTHROPIC_API_KEY="tu_clave"
```

---

## ⚙️ Uso

Para procesar documentos nuevos:

```bash
python process_documents.py [--year 2025]
```

* El año por defecto es el actual, pero se puede forzar con el flag `--year`.

---

## 📌 Scripts incluidos

| Script                      | Función                                                        |
| --------------------------- | -------------------------------------------------------------- |
| `scrape.py`                 | Descarga artículos desde Instapaper                            |
| `html2md.py`                | Convierte HTML a Markdown                                      |
| `fix_html_encoding.py`      | Inserta charset UTF-8 en documentos HTML                       |
| `ajustar_ancho_imagenes.py` | Reduce automáticamente el ancho de imágenes grandes            |
| `add_margin_html.py`        | Añade márgenes estándar al HTML                                |
| `update_titles.py`          | Usa IA (Anthropic) para generar títulos descriptivos           |
| `rebuild_historial.py`      | Reconstruye por completo `Historial.txt` por fecha de creación |

---

## 🔄 Reconstruir Historial

Si necesitas regenerar por completo el historial:

```bash
python rebuild_historial.py
```

Este script genera un backup (`Historial.txt.bak`) antes de reconstruir el historial.

---

## 💡 Licencia

Este proyecto es para uso personal. Si deseas reutilizar o modificar partes del código, puedes hacerlo libremente.

---

© 2025 Domingo Gallardo López
