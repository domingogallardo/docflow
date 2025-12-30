# 📚 docflow - Personal Documentation Pipeline (short version)

docflow automates **collect → process → prioritize (bump) → read → publish → mark as completed** your documents (articles, podcasts, Markdown, PDFs, and tweets) in a yearly structure.

## ✨ Features
- Single pipeline for Instapaper, Snipd, PDFs, images, Markdown, and tweets (X likes + `Tweets/Tweets <YEAR>/`).
- Automatic bump/unbump (⭐ in Instapaper) and a local overlay (`utils/serve_docs.py`) to publish and unpublish.
- Deploy to your domain via `web/deploy.sh`: generates a static index at `/read/` (ordered by `mtime`) to read online and copy quotes easily.
- History log (`Incoming/processed_history.txt`) and utilities to generate AI titles, clean Markdown, and copy quotes with Text Fragments.

## 🖼️ Full processing
![Full pipeline diagram](complete_processing.png)

## 🔧 Quick requirements
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
1. Configure variables if you use external services:
   ```bash
   export OPENAI_API_KEY=...       # optional (AI titles)
   export INSTAPAPER_USERNAME=...  # optional
   export INSTAPAPER_PASSWORD=...  # optional
   export TWEET_LIKES_STATE=/path/to/x_state.json  # required if you process X likes
   export TWEET_LIKES_MAX=50                          # optional, scroll limit
   ```
2. Run the full pipeline (you can pass `--year`):
   ```bash
   python process_documents.py all --year 2025

   # If you don't pass --year, DOCPIPE_YEAR is used if present; otherwise the system year.

   # To unify cron and manual execution (loads ~/.docflow_env if it exists):
   bash bin/docflow.sh all
   ```
3. For the remote tweets queue:
   ```bash
   python process_documents.py tweets
   ```
4. Serve the local overlay and review documents:
   ```bash
   PORT=8000 SERVE_DIR="/path/to/⭐️ Documentación" python utils/serve_docs.py
   ```
5. Deploy to `/read/` when content is ready:
   ```bash
   (cd web && ./deploy.sh)
   ```
6. Quick tests:
   ```bash
   pytest -q
   ```

## 🛠️ Standalone scripts
- `utils/standalone_download_liked_tweets.py`: downloads X likes to Markdown from an exported `storage_state`.
- `utils/standalone_download_instapaper.py`: downloads all your Instapaper articles to HTML/Markdown in a directory.
- `utils/standalone_markdown_to_html.py`: converts Markdown to HTML with margins without the full pipeline.
- `utils/standalone_snipd_to_markdown.py`: cleans Snipd exports and splits them into episodes with a snips index.

## 🌐 Publish on your domain (`/read/`)
- Run `web/deploy.sh` (from `web/`) to generate a static index ordered by `mtime` and upload it to the web container on your server (path `/read/`).
- Use BasicAuth on the host if you want private access (configurable via env vars in `deploy.sh`).
- Check after deploy:
  ```bash
  curl -I https://your-domain.com/read/
  curl -s https://your-domain.com/read/ | head -n 20
  ```

## 📚 Documentation
- `docs/guia.md` - full operating guide (commands, overlay, quotes, troubleshooting).
- `docs/flujo.md` - end-to-end flow (inputs, pipeline, publishing, and Obsidian).
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
