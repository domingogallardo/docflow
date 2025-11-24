# 📜 Flujo de contenidos con DocFlow (versión ampliada)

Este documento describe cómo entra, se procesa y se publica cada tipo de contenido en tu sistema, según el comportamiento real de `process_documents.py`, `pipeline_manager.py`, el overlay de `serve_docs.py` y el despliegue a `domingogallardo.com`. Parte de la estructura está en el documento original que ya enumera las 4 entradas (Instapaper, Snipd, Incoming y likes de X).

---

## 0. Prerrequisitos y entorno

- Tienes definido un `BASE_DIR` en `config.py` que apunta a tu carpeta local de documentación (por ejemplo, `"/Users/domingo/⭐️ Documentación"`). Todos los procesadores escriben debajo de ahí.
- Tienes el script de servidor local `utils/serve_docs.py` para revisar los documentos en el navegador, con los botones de **Bump**, **Unbump**, **Publicar**, etc.
- Tienes el directorio `web/` con el script `web/deploy.sh` que genera `/read/` y sube el contenido al servidor, reiniciando el contenedor `web-domingo`. Esto es lo que convierte un documento local en “fuente oficial”.
- Python disponible para ejecutar `process_documents.py`.

---

## 1. Entradas

| Entrada | Origen | Qué llega | Procesamiento |
| --- | --- | --- | --- |
| **A. Instapaper** | Artículos y newsletters guardados en Instapaper | Markdown/HTML exportado | `python process_documents.py posts` → `InstapaperProcessor` |
| **B. Snipd** | Snips de podcasts con transcripción | Markdown export Snipd | `python process_documents.py podcasts` → `PodcastProcessor` |
| **C. Incoming local** | PDFs, `.md` u otros ficheros que guardas en `⭐️ Documentación/Incoming` | `.pdf`, `.md`, imágenes | `python process_documents.py pdfs/md/images` → procesadores específicos |
| **D. Likes de X** | Marcados con “Me gusta” en `TWEET_LIKES_URL` | Tweets individuales | `python process_documents.py tweets` → `process_tweets_pipeline()` → `MarkdownProcessor.process_markdown_subset()` → `Tweets/Tweets <AÑO>/` |

Notas importantes del punto D:
- El pipeline de tweets utiliza `utils/x_likes_fetcher.fetch_likes_with_state` para abrir tu feed de likes con Playwright y cortar cuando llega al último tweet registrado en `Incoming/tweets_processed.txt`.
- Los tweets se gestionan exclusivamente mediante esos likes o herramientas dedicadas; Instapaper ya no se usa para capturarlos.

---

## 2. Ingesta y almacenamiento local

El comando base es:

```bash
python process_documents.py [targets] [--year 2025]
```

- `posts` → Instapaper
- `podcasts` → Snipd
- `pdfs`, `md`, `images` → Incoming
- `tweets` → likes de X (envía el resultado a `Tweets/Tweets <AÑO>/`)
- `all` → ejecuta todos y registra rutas

Cada procesador:
1. limpia/convierten el contenido,
2. genera HTML si aplica,
3. lo mueve a su carpeta anual (`Posts/Posts 2025/`, `Podcasts/Podcasts 2025/`, `Pdfs/Pdfs 2025/`, `Tweets/Tweets 2025/`, etc.) dentro de `BASE_DIR`.

---

## 3. Revisión en servidor web local

Para revisar lo procesado:

```bash
PORT=8000 SERVE_DIR="/Users/domingo/⭐️ Documentación" python utils/serve_docs.py
```

El overlay:
- lista los documentos ordenados por `mtime`,
- permite **Bump (b)**, **Unbump (u)**, **Publicar (p)**, **Despublicar (d)**,
- aplica **bump automático** a los HTML generados desde Instapaper si el artículo original estaba marcado con ⭐ (lo hace `InstapaperProcessor` usando `utils.bump_files`, igual que en el pipeline),
- es el punto donde decides qué pasa a la web.

Todas las entradas A–D convergen aquí.

---

## 4. Publicación en `domingogallardo.com`

Cuando un documento ya está bien:

1. Pulsas **Publicar** en el overlay (o copias el archivo a `web/public/read/`).
2. Ejecutas:

   ```bash
   cd web
   ./deploy.sh
   ```

   El script:
   - regenera `web/public/read/index.html` ordenado por `mtime`,
   - sube todo a `/opt/web-domingo/` y reinicia el contenedor `web-domingo` que sirve en el puerto 8080.

A partir de aquí ese documento es la **fuente oficial**: es el que usarás en Obsidian.

---

## 5. Destilado en Obsidian

Regla: **solo llevas a Obsidian lo que ya está publicado en `/read/`**. No copias directamente desde Instapaper, ni desde Snipd, ni desde Incoming.

En Obsidian:
- copias las citas o fragmentos,
- añades la URL pública,
- escribes el comentario o nota personal.

---

## 6. Ejemplo completo (caso “like en X”)

1. Das “Me gusta” a un tweet desde tu cuenta principal.
2. Ejecutas:

   ```bash
   python process_documents.py tweets --year 2025
   ```

   Esto:
   - abre tu feed de likes con Playwright usando el `storage_state` configurado,
   - corta en el último tweet que ya aparece en `Incoming/tweets_processed.txt`,
   - convierte los nuevos likes a Markdown/HTML y los mueve a `Tweets/Tweets 2025/`.
3. Abres el servidor local (`serve_docs.py`), ves el tweet como página.
4. Pulsas **Publicar**.
5. Ejecutas `web/deploy.sh`.
6. Abres la URL pública en `domingogallardo.com/read/...` y desde ahí copias el párrafo a Obsidian.

---

## 7. Problemas típicos

- **No se ha procesado ningún tweet**: comprueba si la URL está comentada con `#` o si ya está en `Incoming/tweets_processed.txt`.
- **No aparece en el overlay**: revisa que el procesador lo movió a la carpeta anual dentro de `BASE_DIR` y que `serve_docs.py` apunta ahí.
- **Lo veo en local pero no en la web**: falta ejecutar `web/deploy.sh`.
- **Me está mezclando años**: revisa el `--year` que pasas al procesador y el que hay en `config.py`.

---

## 8. Diagrama del flujo

```text
Entradas:
  A) Instapaper
  B) Snipd
  C) Incoming local
  D) Editor remoto de tweets
            │
            ▼
  process_documents.py  →  carpetas anuales en BASE_DIR
            │
            ▼
  utils/serve_docs.py (overlay, revisión, publicar)
            │
            ▼
  web/deploy.sh  →  domingogallardo.com (/read/)
            │
            ▼
          Obsidian
```
