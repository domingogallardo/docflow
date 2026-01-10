# 📚 docflow - Personal Documentation Pipeline (short version)

docflow automates **collect -> process -> prioritize (bump) -> read -> publish -> mark as completed** for your documents (articles, podcasts, Markdown, PDFs, and tweets) in a yearly structure.

## ✨ Highlights
- Single pipeline for Instapaper, Snipd, PDFs, images, Markdown, and X likes (`Tweets/Tweets <YEAR>/`).
- Automatic bump/unbump (⭐ in Instapaper) and a local overlay (`utils/serve_docs.py`) to publish/unpublish/delete.
- Deploy to your domain via `web/deploy.sh`: generates a static `/read/` index ordered by `mtime`.
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
  pip install playwright
  playwright install chromium
  ```

## 🚀 Quick start
1. Configure env vars if you use external services:
   ```bash
   export OPENAI_API_KEY=...         # optional (AI titles)
   export INSTAPAPER_USERNAME=...    # optional
   export INSTAPAPER_PASSWORD=...    # optional
   export TWEET_LIKES_STATE=/path/to/x_state.json  # required if you process X likes
   export TWEET_LIKES_MAX=50                           # optional, scroll limit
   ```
2. Run the full pipeline (you can pass `--year`):
   ```bash
   python process_documents.py all --year 2025

   # If you don't pass --year, DOCPIPE_YEAR is used if present; otherwise the system year.

   # To unify cron and manual execution (loads ~/.docflow_env if it exists):
   bash bin/docflow.sh all
   ```
3. Review locally with the overlay (publish/unpublish/delete):
   ```bash
   PORT=8000 SERVE_DIR="/path/to/⭐️ Documentación" python utils/serve_docs.py
   ```
4. Deploy to `/read/` when ready:
   ```bash
   (cd web && ./deploy.sh)
   ```
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
- The pipeline stops at the last processed tweet (`Incoming/tweets_processed.txt`) and honors `TWEET_LIKES_MAX` and `TWEET_LIKES_BATCH` (optional).

## 🏷️ Source tags (routing)
- Markdown routing is based on `source:` front matter (no heuristics).
- Tweets: `source: tweet` (added by `tweet_to_markdown.py` / likes pipeline).
- Instapaper: HTML includes `<meta name="docflow-source" content="instapaper">` and Markdown includes `source: instapaper`.
- Podcasts: `source: podcast` (auto-added when cleaning Snipd exports).
- Generic Markdown: any `.md` in `Incoming/` without a `source:` tag.

## 🌐 Publish on your domain (`/read/`)
- Run `web/deploy.sh` (from `web/`) to generate a static index ordered by `mtime` and upload to the web container.
- Use BasicAuth on the host if you want private access (configurable via env vars in `deploy.sh`).
- Verify after deploy:
  ```bash
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
