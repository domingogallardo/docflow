# 📚 docflow — Pipeline de Documentación Personal (versión resumida)

docflow automatiza **recolectar → procesar → priorizar (bump) → leer → publicar → marcar como completado** tus documentos (artículos, podcasts, Markdown, PDFs y tweets) en una estructura anual.

## ✨ Características
- Pipeline único para Instapaper, Snipd, PDFs, imágenes, Markdown y tweets (editor remoto + `Tweets/Tweets <AÑO>/`).
- Bump/unbump automático (⭐ en Instapaper) y overlay local (`utils/serve_docs.py`) para publicar, despublicar y marcar procesados.
- Deploy reproducible a `/read/` mediante `web/deploy.sh` (índice estático ordenado por `mtime` + soporte de `read_posts.md`).
- Registro histórico (`Incoming/processed_history.txt`) y utilidades para convertir títulos con IA, limpiar Markdown y copiar citas con Text Fragments.

## 🔧 Requisitos rápidos
- **Python 3.10+**.
- Dependencias base:
  ```bash
  pip install requests beautifulsoup4 markdownify openai pillow pytest markdown
  ```
- Para capturar tweets directamente (opcional):
  ```bash
  pip install playwright
  playwright install chromium
  ```

## 🚀 Arranque rápido
1. Configura variables si usas servicios externos:
   ```bash
   export OPENAI_API_KEY=...     # opcional (títulos IA)
   export INSTAPAPER_USERNAME=...  # opcional
   export INSTAPAPER_PASSWORD=...  # opcional
   ```
2. Ejecuta el pipeline completo (puedes pasar `--year`):
   ```bash
   python process_documents.py all --year 2025
   ```
3. Para la cola remota de tweets:
   ```bash
   python process_documents.py tweets
   ```
4. Sirve el overlay local y revisa los documentos:
   ```bash
   PORT=8000 SERVE_DIR="/ruta/a/⭐️ Documentación" python utils/serve_docs.py
   ```
5. Despliega a `/read/` cuando tengas contenido listo:
   ```bash
   (cd web && ./deploy.sh)
   ```
6. Tests rápidos:
   ```bash
   pytest -q
   ```

## 📚 Documentación
- `docs/guia.md` — guía operativa completa (comandos, overlay, citas, troubleshooting).
- `docs/flujo.md` — flujo de extremo a extremo (entradas, pipeline, publicación y Obsidian).
- `docs/readme-infra.md` — despliegue y hardening (Docker/Nginx, TLS, BasicAuth).
- `docs/ops-playbook.md` — tareas operativas y checklists.

## 📂 Estructura base
```
⭐️ Documentación/
├── Incoming/
├── Posts/Posts <AÑO>/
├── Tweets/Tweets <AÑO>/
├── Podcasts/Podcasts <AÑO>/
├── Pdfs/Pdfs <AÑO>/
├── Images/Images <AÑO>/
└── web/ (deploy estático)
```

## 🤝 Contribuir
- Sigue el estilo del repo (Python 3.10+, tipado moderado, mensajes en español con emoji).
- Asegúrate de actualizar la documentación relevante (`docs/guia.md`, `docs/flujo.md`, etc.) cuando cambies el comportamiento.
- Ejecuta `pytest` antes de abrir un PR.

© 2025 Domingo Gallardo López
