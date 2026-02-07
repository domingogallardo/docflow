# 📚 docflow - Personal Documentation Pipeline (short version)

docflow automates **collect -> process -> prioritize (bump) -> read -> publish -> mark as highlighted** for your documents (articles, podcasts, Markdown, PDFs, and tweets) in a yearly structure.

## ✨ Highlights
- Single pipeline for Instapaper, Snipd, PDFs, images, Markdown, and X likes (`Tweets/Tweets <YEAR>/`).
- Local overlay (`utils/serve_docs.py`) to bump/unbump, publish/unpublish (copies to `web/public/read/` + deploy), or delete.
- Sync public highlights into `Posts/Posts <YEAR>/highlights/` and inject invisible markers into local `.md` (overlapping highlights are consolidated) after `bin/docflow.sh` (manual: `python utils/sync_public_highlights.py --base-url https://...`). When the pipeline and highlights sync succeed, it regenerates `web/public/read/read.html` and runs `web/deploy.sh` only if the index changed.
- Deploy to your domain via `web/deploy.sh`: generates a static `/read/` index ordered by `mtime` and assembles the base site from a separate repo via `PERSONAL_WEB_DIR` (required for production deploys).
- History log (`Incoming/processed_history.txt`) and utilities for AI titles, Markdown cleanup, and quote capture.
- Routing is tag-based: tweets/podcasts/Instapaper are tagged, and generic Markdown is any `.md` without a `source:` tag.

## 🖼️ Full processing
![Full pipeline diagram](complete_processing.png)

## 🔧 Requirements
- **Python 3.10+**.
- Core dependencies:
  ```bash
  pip install requests beautifulsoup4 markdownify openai pillow pytest markdown
  ```
- To capture tweets directly (optional):
  ```bash
  pip install "playwright>=1.55"
  playwright install chromium
  ```
  (Uses Playwright's `expect_response`; tested with 1.55.0.)

## 🚀 Quick start
1. Configure env vars if you use external services:
   ```bash
   export OPENAI_API_KEY=...         # optional (AI titles)
   export INSTAPAPER_USERNAME=...    # optional
   export INSTAPAPER_PASSWORD=...    # optional
   export TWEET_LIKES_STATE=/path/to/x_state.json  # required if you process X likes
   export TWEET_LIKES_MAX=50                           # optional, scroll limit
   export HIGHLIGHTS_BASE_URL=https://your-domain.com  # required for highlight sync in bin/docflow.sh
   ```
2. Run the full pipeline (you can pass `--year`):
   ```bash
   python process_documents.py all --year 2025

   # If you don't pass --year, DOCPIPE_YEAR is used if present; otherwise the system year.

   # To unify cron and manual execution (loads ~/.docflow_env if it exists):
   bash bin/docflow.sh all
   # Also syncs public highlights into Posts/Posts <YEAR>/highlights/.
   # If the pipeline + highlights sync succeed, it regenerates web/public/read/read.html.
   # It runs web/deploy.sh only if read.html changed (requires REMOTE_USER/REMOTE_HOST).
   ```
3. Review locally with the overlay (bump/unbump, publish/unpublish, delete):
   ```bash
   PORT=8000 SERVE_DIR="/path/to/⭐️ Documentación" python utils/serve_docs.py
   ```
4. Deploy to `/read/` when ready:
   ```bash
   PERSONAL_WEB_DIR=/path/to/personal-web bash bin/publish_web.sh
   ```
   For production, do not deploy without `PERSONAL_WEB_DIR`; otherwise the base site can be replaced by `docflow/web/public` (usually only `/read`).
5. Quick tests:
   ```bash
   pytest -q
   ```

## 🐦 X likes pipeline (quick notes)
- One-time login to export session state:
  ```bash
  python utils/create_x_state.py
  ```
- Process the likes queue:
  ```bash
  python process_documents.py tweets
  ```
- If you like the last tweet of a thread, the pipeline saves the full thread in a single Markdown file.
- The pipeline waits ~1s after loading a tweet to let X finish rendering before extraction.
- The pipeline stops at the last processed tweet (`Incoming/tweets_processed.txt`) and honors `TWEET_LIKES_MAX`.

## 🏷️ Source tags (routing)
- Markdown routing is based on `source:` front matter (no heuristics).
- Tweets: `source: tweet` (added by `tweet_to_markdown.py` / likes pipeline).
- Instapaper: HTML includes `<meta name="docflow-source" content="instapaper">` and Markdown includes `source: instapaper`.
- Podcasts: `source: podcast` (auto-added when cleaning Snipd exports).
- Generic Markdown: any `.md` in `Incoming/` without a `source:` tag.

## 🌐 Publish on your domain (`/read/`)
- Run `web/deploy.sh` (from `web/`) to generate a static `read.html` index ordered by `mtime` and upload to the web container.
- Or run `bin/publish_web.sh` to load `~/.docflow_env`, validate env vars, and call `web/deploy.sh`.
- Production safety rule: `PERSONAL_WEB_DIR` must point to your personal site repo (`<PERSONAL_WEB_DIR>/public` must exist) before deploy.
- If `PERSONAL_WEB_DIR` is empty, deploy assembles `/public` from `docflow/web/public` and can leave the personal site root incomplete.
- `/read/` should serve `read.html` (autoindex off) via Nginx `index read.html` + `try_files`.
- The index shows 🟡 for items with highlight JSON in `Posts/Posts <YEAR>/highlights/`.
- If you run `utils/build_read_index.py` outside the repo, ensure it can resolve `BASE_DIR` (via `config.py` or `DOCFLOW_BASE_DIR`).
- Use BasicAuth on the host if you want private access (configurable via env vars in `deploy.sh`).
- Verify after deploy:
  ```bash
  curl -I https://your-domain.com/
  curl -I https://your-domain.com/blog/
  curl -I https://your-domain.com/read/
  curl -s https://your-domain.com/read/ | head -n 20
  ```

## 📚 Documentation
- `docs/guide.md` - full operating guide (commands, overlay, quotes, troubleshooting).
- `docs/flow.md` - end-to-end flow (inputs, pipeline, publishing, and Obsidian).
- `docs/readme-infra.md` - deployment and hardening (Docker/Nginx, TLS, BasicAuth).
- `docs/ops-playbook.md` - operational tasks and checklists.

## 📂 Base structure
```
⭐️ Documentación/
├── Incoming/
├── Posts/Posts <YEAR>/
├── Tweets/Tweets <YEAR>/
├── Podcasts/Podcasts <YEAR>/
├── Pdfs/Pdfs <YEAR>/
├── Images/Images <YEAR>/
└── web/ (static deploy)
```

© 2026 Domingo Gallardo López
