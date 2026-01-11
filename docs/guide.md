# docflow - Extended guide

> This document expands the short README. It keeps the operational details for working with docflow day to day. The infra and TLS guide is in **readme-infra.md**.

## Table of contents
- [docflow - Extended guide](#docflow---extended-guide)
  - [Table of contents](#table-of-contents)
  - [Key concepts](#key-concepts)
  - [Essential commands](#essential-commands)
  - [Detailed workflow](#detailed-workflow)
  - [Local web server (`utils/serve_docs.py`)](#local-web-server-utilsserve_docspy)
  - [Web publishing (`/read/`) and `read.html`](#web-publishing-read-and-readhtml)
  - [Capture quotes with Text Fragments](#capture-quotes-with-text-fragments)
  - [Environment variables](#environment-variables)
  - [Script summary by phase](#script-summary-by-phase)
  - [Troubleshooting](#troubleshooting)
  - [Infrastructure and verification](#infrastructure-and-verification)

---

## Key concepts

- **Bump/Unbump**: adjust a file's `mtime` to prioritize it in date-ordered listings.  
  - Automatic if the Instapaper title starts with **⭐**.  
  - Manual via the overlay or `utils/bump.applescript` / `utils/un-bump.applescript` (Finder).
- **Overlay**: UI on locally served HTML to perform actions (bump/unbump, publish, etc.).
- **Source tags (routing)**: Markdown routing is based on `source:` front matter only.  
  - Tweets: `source: tweet`  
  - Instapaper: `source: instapaper` (HTML must include `<meta name="docflow-source" content="instapaper">`)  
  - Podcasts: `source: podcast`  
  - Generic Markdown: any `.md` without a `source:` tag

---

## Essential commands

```bash
# Full pipeline or by type
python process_documents.py all [--year YYYY]
python process_documents.py posts podcasts pdfs
python process_documents.py tweets

# Convert Markdown to HTML
python md_to_html.py

# Serve HTML/PDF with overlay
PORT=8000 SERVE_DIR="/path/to/⭐️ Documentación" python utils/serve_docs.py
```

Recommended dependencies:
```bash
pip install requests beautifulsoup4 markdownify openai pillow pytest markdown
```
To capture tweets directly:
```bash
pip install "playwright>=1.55"
playwright install chromium
```
(`expect_response` required; tested with 1.55.0.)

---

## Detailed workflow

1) **Collect → Base structure**  
Save your sources in `⭐️ Documentación/Incoming/` (or their original folders) and the pipeline will place them into year-based folders: `Posts/Posts <YEAR>/`, `Podcasts/Podcasts <YEAR>/`, `Pdfs/Pdfs <YEAR>/`, `Images/Images <YEAR>/`, `Tweets/Tweets <YEAR>/`.

2) **Process → Pipeline**  
```bash
python process_documents.py all --year 2025
# or selective:
python process_documents.py pdfs md
python process_documents.py images
```
- Instapaper (clean HTML + MD, AI title, margins, metadata, and safe filenames).  
- Snipd podcasts (MD → clean HTML, system typography, audio buttons).  
- PDFs (yearly organization).  
- Images (yearly copy + `gallery.html` for JPG/PNG/WebP/TIFF/GIF/BMP).  
All of this is orchestrated by `process_documents.py` and specific `*_processor.py` modules. Routing is tag-based: any Markdown without a `source:` tag is treated as generic input.

> **Tweet shortcut**: `python utils/tweet_to_markdown.py https://x.com/...` downloads the tweet with Playwright and saves it as `.md` with title, link, profile photo, and body without metrics (views/likes), followed by attached images. Default wait after load is 1s.

> **Tweets queue**: Like the tweets you want to process on X. Run once `python utils/create_x_state.py` to log in manually and save your `storage_state` (you can change the path with `--state-path` and point `TWEET_LIKES_STATE` to that file). From then on, `python process_documents.py tweets` opens your likes feed (`TWEET_LIKES_URL`, default `https://x.com/domingogallardo/likes`) with Playwright, extracts the newest links until it finds the last processed tweet (using `Incoming/tweets_processed.txt` as reference) or until the `TWEET_LIKES_MAX` limit (default 100). To avoid overload, set `TWEET_LIKES_BATCH` (default 10) so only that many new likes are processed per run.
> If you like the last tweet of a thread, the pipeline groups the previous tweets by the same author/time into a single Markdown file.

3) **Prioritize for reading → Bump/Unbump**  
- **Star in Instapaper**: if you add a star to the article **title** in Instapaper, the pipeline **propagates** that "featured" status to HTML/MD and **auto-bumps** the HTML (sets its `mtime` to the future) so it appears at the top of date-sorted lists.  
- You also have Finder shortcuts (`utils/bump.applescript`, `utils/un-bump.applescript`) if you need to bump/unbump manually.

4) **Read locally and manage state → `utils/serve_docs.py`**  
Start the local reading server:  
```bash
PORT=8000 SERVE_DIR="/path/to/⭐️ Documentación" python utils/serve_docs.py
```
- Overlay on **HTML** pages with **Bump / Unbump / Publish / Unpublish / Delete** buttons and **keyboard shortcuts**.  
- The listing shows only folders, HTML, and PDFs (hides `.md`), ordered by **mtime desc**.  
- State rules:  
  - **S0** Unbumped + Not published → shows *Bump*.  
  - **S1** Bumped + Not published → shows *Unbump* and *Publish*.  
  - **S2** Published → shows *Unpublish*.  
- **Validation rules**:  
  - Publishing **requires** the file to be **bumped** and **not published**.  
  - While **published**, **Bump/Unbump** is not allowed (and not shown).  
  - The server rejects `bump`/`unbump_now` if the file is published.
- **Delete** permanently removes the HTML/PDF (and any associated Markdown) from the local library.

5) **Publish to the public web (`/read/`)**  
From the overlay, **Publish** copies the `.html` or `.pdf` to `web/public/read/` and triggers the **deploy** (`web/deploy.sh`). The deploy builds the Nginx image, uploads assets to the remote server, and serves `/read/` with an index **ordered by date (mtime desc)**. You can set `REMOTE_USER`/`REMOTE_HOST` via the environment.

6) **Capture quotes and highlights on published pages**  
On `/read/`, a floating **❝ Copy quote** button is injected. When you select text, it copies a **Markdown** quote with a link that includes **Text Fragments** (`#:~:text=`). This makes it easy to paste quotes directly into Obsidian while keeping the jump to the exact position. The overlay also shows **Subrayar**, which saves highlights to `/data/highlights/<file>.json` (visible across browsers). Hold **Alt** or **Shift** and click a highlight to remove it. (*Script*: `article.js`).

7) **Close the loop**  
When you finish reading, you can keep the document published or unpublish it; `/read/` is a single date-ordered listing.

8) **Infrastructure and verification**  
Deployment uses **double Nginx**: a TLS proxy on the **host** and Nginx **inside the container** serving static files; `/data/` allows PUT with BasicAuth (host-mounted). Verify `/read/` with `curl` after deploy (commands below).

> Tip: if you want to preview the index without deploying, use `python utils/build_read_index.py`; deploy will regenerate it anyway.

---

## Local web server (`utils/serve_docs.py`)

- **Actions**: Bump (`b`), Unbump (`u`), Publish (`p`), Unpublish (`d`), Delete (button), Listing (`l`).  
- **States**: S0/S1/S2 (see above).  
- **Parameters**:
  - `PORT` (default 8000)
  - `SERVE_DIR` (base path)
  - `BUMP_YEARS` (years in the future for bumping; default 100)
  - Local publishing:
    - `PUBLIC_READS_DIR` (default `web/public/read`)
    - `DEPLOY_SCRIPT` (default `web/deploy.sh`)
    - `PUBLIC_READS_URL_BASE` (to link the "View" after publishing)

---

## Web publishing (`/read/`) and `read.html`

- The deploy **generates** `read.html` as a single listing **ordered by mtime desc** with all HTML/PDFs in `web/public/read/`.
- Served by the container's Nginx with *autoindex* enabled (see **readme-infra.md**).

Quick verification:
```bash
curl -I https://<your_domain>/read/
curl -s https://<your_domain>/read/ | head -n 40
```

---

## Capture quotes and highlights

- Pages under `/read/` inject a **❝ Copy quote** button (`article.js`).  
- Select text and copy a **Markdown** quote with a link that includes `#:~:text=` to jump to the exact position.  
- It preserves links and emphasis from the selected fragment, converting them to Markdown before copying.  
- The button only appears when there is selected text and shows a success/error *toast*.
- The overlay also includes **Subrayar**, which saves highlights to `/data/highlights/<file>.json` (visible across browsers).
- Hold **Alt** or **Shift** and click a highlight to remove it.
- iOS/iPadOS: selection is captured early so it isn't lost when tapping the button. If the clipboard fails (e.g., private browsing), you'll see an error toast; fragment navigation is handled by the browser.

---

## Environment variables

```bash
# Integrations
OPENAI_API_KEY=...             # Instapaper titles (optional)
INSTAPAPER_USERNAME=...        # optional
INSTAPAPER_PASSWORD=...        # optional

# Publishing/Deploy
REMOTE_USER=root
REMOTE_HOST=1.2.3.4
PUBLIC_READS_URL_BASE=https://<your_domain>/read

# Local server
PORT=8000
SERVE_DIR="/path/to/⭐️ Documentación"
BUMP_YEARS=100

# Optional: BasicAuth management in deploy
HTPASSWD_USER=editor
HTPASSWD_PSS='password'
```

---

## Script summary by phase

- **Process**: `process_documents.py`, `instapaper_processor.py`, `podcast_processor.py`, `pdf_processor.py`.  
- **Read/prioritize/publish (local)**: `utils/serve_docs.py` (overlay + actions), `utils/bump.applescript`, `utils/un-bump.applescript`.  
- **Publish (remote)**: `web/deploy.sh` (generates `read.html` by mtime desc as a single listing).  
- **Capture quotes/highlights in `/read/`**: `article.js` (**❝ Copy quote** + **Subrayar**, Markdown + `#:~:text=`, highlights via `/data/highlights/`).  
- **Preview index without deploy**: `utils/build_read_index.py`.

---

## Troubleshooting

- **"Publish" does not appear** → the file is not **bumped** or already exists in `PUBLIC_READS_DIR`. Check `mtime` and names.  
- **"Unpublish" does not appear** → the file is not in `PUBLIC_READS_DIR` (detected by name).  
- **`read.html` does not change** → deploy regenerates it; hard-refresh and check `web/deploy.sh` output.  
- **Deploy error** → verify `web/deploy.sh` permissions (`chmod +x`) and that `REMOTE_USER`/`REMOTE_HOST` are set.  
- **Toast without "View" link** → set `PUBLIC_READS_URL_BASE`.  

---

## Infrastructure and verification

The **infra** uses double Nginx (TLS on host + Nginx in container) and BasicAuth for PUT on `/data` with a host-mounted `.htpasswd`. For details and hardening, see **readme-infra.md**.
