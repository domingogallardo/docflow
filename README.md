# 📚 docflow - Personal Documentation Pipeline (short version)

docflow automates **collect -> process -> prioritize (bump) -> read -> publish -> mark as highlighted** for your documents (articles, podcasts, Markdown, PDFs, and tweets) in a yearly structure.

## 🧭 Two-site model (important)
docflow works with two different sites:

1. `sitio biblioteca` (local source of truth)
- What it is: your local document library under `BASE_DIR` (from `config.py`).
- Main path: `BASE_DIR` (for example, `/Users/domingo/⭐️ Documentación`).
- Current local intranet server: `python utils/docflow_server.py --base-dir "/path/to/BASE_DIR"` (serves `_site` + API).
- Legacy local overlay (still available): `python utils/serve_docs.py`.
- Tweet consolidated files are created here:
  - `BASE_DIR/Tweets/Tweets <YEAR>/Tweets YYYY-MM-DD.{md,html}`.

2. `sitio publicado` (web output)
- What it is: static files inside this repo that are deployed to your web server.
- Main path: `web/public/read/`.
- Served in production by Nginx at `/read/` (for example, `https://domingogallardo.com/read/`).
- Deployed by: `bash web/deploy.sh` (or `bash bin/publish_web.sh` wrapper).

Tweet flow across both sites:
- `bin/docflow.sh all` calls `bin/build_tweet_consolidated.sh --yesterday`.
- `bin/build_tweet_consolidated.sh` calls `utils/build_daily_tweet_consolidated.py` to generate daily consolidated files in the `sitio biblioteca` and then removes source tweet files included in the consolidated day.
- `utils/sync_tweets_public.py` copies consolidated files from the library into the published site under `web/public/read/tweets/<YEAR>/`.
- `utils/build_tweets_index.py` generates yearly static index pages in the `sitio publicado` (`web/public/read/tweets/<YEAR>.html`) that link to consolidated files for each year.
- `web/deploy.sh` publishes what exists under `web/public/read/`.

## 🏠 Local intranet mode (single server, no Docker required)
You can run docflow as a local intranet from your MacBook (source of truth = `BASE_DIR`) with one Python process:

- Static output root:
  - `BASE_DIR/_site/index.html`
  - `BASE_DIR/_site/browse/...`
  - `BASE_DIR/_site/read/...`
  - `BASE_DIR/_site/assets/...`
- Local state:
  - `BASE_DIR/state/published.json`
  - `BASE_DIR/state/bump.json`
  - `BASE_DIR/state/highlights/...`
- In intranet mode, bump is state-based (`bump.json`) and does not modify file `mtime`.

Build and run:

```bash
# Rebuild browse/read static pages into BASE_DIR/_site
python utils/build_browse_index.py --base-dir "/Users/domingo/⭐️ Documentación"
python utils/build_read_index.py --base-dir "/Users/domingo/⭐️ Documentación"

# Run one local server (HTML/assets/raw files + API actions, no startup rebuild by default)
python utils/docflow_server.py --base-dir "/Users/domingo/⭐️ Documentación" --host 127.0.0.1 --port 8088
# Optional: force full rebuild on startup
python utils/docflow_server.py --base-dir "/Users/domingo/⭐️ Documentación" --rebuild-on-start
```

Expose to your tailnet (iPhone/iPad access, without public internet ports):

```bash
tailscale serve --bg 8088
tailscale serve status
```

Main API actions:
- `/api/publish` `{ "path": "Posts/Posts 2026/file.html" }`
- `/api/unpublish` `{ "path": "Posts/Posts 2026/file.html" }`
- `/api/bump` `{ "path": "Posts/Posts 2026/file.html" }`
- `/api/unbump` `{ "path": "Posts/Posts 2026/file.html" }`
- `/api/rebuild` `{}`
- `GET /api/highlights?path=Posts/Posts%202026/file.html`
- `PUT /api/highlights?path=Posts/Posts%202026/file.html` (JSON payload)

Rebuild behavior in intranet mode:
- On server start: no rebuild by default.
- Optional startup rebuild with `--rebuild-on-start`.
- On per-file actions (`publish`, `unpublish`, `bump`, `unbump`, highlights save): partial `browse` rebuild (affected branch) + full `read` rebuild.

Raw file routes served directly from `BASE_DIR`:
- `/posts/raw/<path>` -> `BASE_DIR/Posts/<path>`
- `/pdfs/raw/<path>` -> `BASE_DIR/Pdfs/<path>`
- `/images/raw/<path>` -> `BASE_DIR/Images/<path>`
- `/tweets/raw/<path>` -> `BASE_DIR/Tweets/<path>`
- `/incoming/raw/<path>` -> `BASE_DIR/Incoming/<path>`
- `/files/raw/<path>` -> `BASE_DIR/<path>` (fallback)

State schema (versioned JSON, local-only):

```json
{
  "version": 1,
  "items": {
    "Posts/Posts 2026/file.html": {
      "published_at": "2026-02-15T18:10:00Z"
    }
  }
}
```

```json
{
  "version": 1,
  "items": {
    "Posts/Posts 2026/file.html": {
      "original_mtime": 1739614200.0,
      "bumped_mtime": 4910000001.0,
      "updated_at": "2026-02-15T18:12:00Z"
    }
  }
}
```

## ✨ Highlights
- Single pipeline for Instapaper, Snipd, PDFs, images, Markdown, and X likes (`Tweets/Tweets <YEAR>/`).
- Daily tweet consolidated files (`Tweets YYYY-MM-DD.{md,html}`) with full tweet/thread content, images, preserved links, file `mtime` set to *(last tweet of the day + 60s)* so listings stay interleaved chronologically, and source daily tweet files removed after consolidation.
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
   export INTRANET_BASE_DIR="/Users/domingo/⭐️ Documentación"  # optional override for local _site rebuild
   ```
2. Run the full pipeline (you can pass `--year`):
   ```bash
   python process_documents.py all --year 2025

   # If you don't pass --year, DOCPIPE_YEAR is used if present; otherwise the system year.

   # To unify cron and manual execution (loads ~/.docflow_env if it exists):
   bash bin/docflow.sh all
   # Also builds tweet consolidated files for yesterday if missing:
   #   Tweets YYYY-MM-DD.md / .html
   # Also syncs public highlights into Posts/Posts <YEAR>/highlights/.
   # If the pipeline + highlights sync succeed, it regenerates web/public/read/read.html.
   # It runs web/deploy.sh only if read.html changed (requires REMOTE_USER/REMOTE_HOST).
   # It also rebuilds local intranet browse index in BASE_DIR/_site/browse.
   # It does not rebuild local intranet read index.
   ```
3. Review locally with the legacy overlay (optional; intranet mode uses `docflow_server.py`):
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
- Consolidated daily tweets helper:
  ```bash
  # Default mode: build yesterday only (skip if .md + .html already exist)
  bash bin/build_tweet_consolidated.sh

  # Specific day
  bash bin/build_tweet_consolidated.sh --day 2026-02-13

  # Build all days found under Tweets/Tweets <YEAR>/ (skip existing)
  bash bin/build_tweet_consolidated.sh --all-days

  # Force rebuild in any mode
  bash bin/build_tweet_consolidated.sh --day 2026-02-13 --force
  ```

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
- `docs/intranet-mode.md` - canonical local intranet mode (`_site`, `docflow_server.py`, API, rebuild strategy, tailscale).
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
