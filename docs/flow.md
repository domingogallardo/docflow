# 📜 Content flow with DocFlow (extended version)

This document describes how each content type enters, is processed, and is published in your system, based on the real behavior of `process_documents.py`, `pipeline_manager.py`, the `serve_docs.py` overlay, and the deployment to `domingogallardo.com`. Part of the structure is in the original document that already lists the four inputs (Instapaper, Snipd, Incoming, and X likes).

---

## 0. Prerequisites and environment

- You have a `BASE_DIR` defined in `config.py` that points to your local documentation folder (for example, `"/Users/domingo/⭐️ Documentación"`). All processors write under it.
- You have the local server script `utils/serve_docs.py` to review documents in the browser, with buttons for **Bump**, **Unbump**, **Publish**, etc.
- You have the `web/` directory with `web/deploy.sh` which generates `/read/` and uploads the content to the server, restarting the `web-domingo` container. This is what turns a local document into an "official source."
- Python is available to run `process_documents.py`.

---

## 1. Inputs

| Input | Source | What arrives | Processing |
| --- | --- | --- | --- |
| **A. Instapaper** | Articles and newsletters saved in Instapaper | Exported Markdown/HTML | `python process_documents.py posts` → `InstapaperProcessor` |
| **B. Snipd** | Podcast snips with transcripts | Snipd Markdown export | `python process_documents.py podcasts` → `PodcastProcessor` |
| **C. Local Incoming** | PDFs, `.md`, or other files saved in `⭐️ Documentación/Incoming` | `.pdf`, `.md`, images | `python process_documents.py pdfs/md/images` → specific processors |
| **D. X likes** | Marked as "Like" on `TWEET_LIKES_URL` | Individual tweets | `python process_documents.py tweets` → `process_tweets_pipeline()` → `MarkdownProcessor.process_tweet_markdown_subset()` → `Tweets/Tweets <YEAR>/` |

Important notes for input D:
- The tweets pipeline uses `utils/x_likes_fetcher.fetch_like_items_with_state` to open your likes feed with Playwright and stop once it reaches the last tweet recorded in `Incoming/tweets_processed.txt`.
- Tweets are managed exclusively via those likes or dedicated tools; Instapaper is no longer used to capture them.

Routing rule (no heuristics):
- **Markdown** is routed exclusively by `source:` front matter.
- **Tweets**: `source: tweet`.
- **Instapaper**: Markdown uses `source: instapaper`; HTML must include `<meta name="docflow-source" content="instapaper">`.
- **Podcasts**: `source: podcast` (auto-added when cleaning Snipd exports).
- **Generic Markdown**: any `.md` without a `source:` tag.

---

## 2. Ingestion and local storage

The base command is:

```bash
python process_documents.py [targets] [--year 2025]
```

- `posts` → Instapaper
- `podcasts` → Snipd
- `pdfs`, `md`, `images` → Incoming
- `tweets` → X likes (sends the result to `Tweets/Tweets <YEAR>/`)
- `all` → runs everything and logs paths

Each processor:
1. cleans/converts the content,
2. generates HTML when applicable,
3. moves it to its yearly folder (`Posts/Posts 2025/`, `Podcasts/Podcasts 2025/`, `Pdfs/Pdfs 2025/`, `Tweets/Tweets 2025/`, etc.) under `BASE_DIR`.

---

## 3. Review on the local web server

To review processed content:

```bash
PORT=8000 SERVE_DIR="/Users/domingo/⭐️ Documentación" python utils/serve_docs.py
```

The overlay:
- lists documents ordered by `mtime`,
- allows **Bump (b)**, **Unbump (u)**, **Publish (p)**, **Unpublish (d)**, and **Delete**,
- **Bump/Unbump** adjusts the local file `mtime` so it moves in the listing,
- **Publish/Unpublish** copies/removes the file in `web/public/read/` and runs `web/deploy.sh`,
- is the point where you decide what goes to the web.

All inputs A-D converge here.

---

## 4. Publishing to `domingogallardo.com`

When a document is ready:

1. Click **Publish** in the overlay (or copy the file into `web/public/read/`).
2. Run:

   ```bash
   cd web
   ./deploy.sh
   ```

   The script:
   - regenerates `web/public/read/index.html` ordered by `mtime`,
   - uploads everything to `/opt/web-domingo/` and restarts the `web-domingo` container that serves on port 8080.

From this point on, that document is the **official source**: it is the one you will use in Obsidian.

---

## 5. Distillation in Obsidian

Rule: **only bring into Obsidian what is already published at `/read/`**. Do not copy directly from Instapaper, Snipd, or Incoming.

In Obsidian:
- copy quotes or fragments,
- add the public URL,
- write your personal note.

---

## 6. Complete example (X like case)

1. You "Like" a tweet from your main account.
2. Run:

   ```bash
   python process_documents.py tweets --year 2025
   ```

   This:
   - opens your likes feed with Playwright using the configured `storage_state`,
   - stops at the last tweet already in `Incoming/tweets_processed.txt`,
   - converts new likes to Markdown/HTML and moves them to `Tweets/Tweets 2025/`.
3. Open the local server (`serve_docs.py`) and view the tweet as a page.
4. Click **Publish**.
5. Run `web/deploy.sh`.
6. Open the public URL in `domingogallardo.com/read/...` and copy the paragraph into Obsidian from there.

---

## 7. Common issues

- **No tweets were processed**: check whether the URL is commented out with `#` or if it is already in `Incoming/tweets_processed.txt`.
- **It does not appear in the overlay**: verify the processor moved it to the yearly folder under `BASE_DIR` and that `serve_docs.py` points there.
- **I see it locally but not on the web**: you need to run `web/deploy.sh`.
- **Years are getting mixed**: verify the `--year` you pass to the processor and the one in `config.py`.

---

## 8. Flow diagram

```text
Inputs:
  A) Instapaper
  B) Snipd
  C) Local Incoming
  D) X likes
            │
            ▼
  process_documents.py  →  yearly folders in BASE_DIR
            │
            ▼
  utils/serve_docs.py (overlay, review, publish)
            │
            ▼
  web/deploy.sh  →  domingogallardo.com (/read/)
            │
            ▼
          Obsidian
```
