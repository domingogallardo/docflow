# Repository Guidelines

This repository automates collecting and organizing personal documents (Instapaper posts, Snipd podcasts, Markdown notes, PDFs, tweets via a dedicated pipeline). Keep changes small, tested, and aligned with the current modular design.

## Project Structure & Modules
- Source: top-level Python modules (e.g., `process_documents.py`, `pipeline_manager.py`, `utils.py`, `*_processor.py`).
- Tests: `tests/` with `pytest` suites and fixtures in `tests/fixtures/`.
- Utilities: `utils/` for helper scripts (e.g., `serve_html.py`, `rebuild_processed_history.py`).
- Configuration: `config.py` (paths, env vars). Destinations use `BASE_DIR` with year-based folders like `Posts/Posts <YEAR>/`.

## Build, Test, and Dev Commands
- Install deps: `pip install requests beautifulsoup4 markdownify openai pillow pytest markdown`
- Tweet capture deps: `pip install "playwright>=1.55" && playwright install chromium` (expects `expect_response`, tested with 1.55.0)
- Run pipeline: `python process_documents.py all --year 2025`
- Tweets queue: `python process_documents.py tweets` opens your X likes with Playwright (`TWEET_LIKES_STATE`, `TWEET_LIKES_URL`) until it finds the last tweet recorded in `Incoming/tweets_processed.txt`, avoids duplicates, and completes the Markdown/HTML pipeline
- Selective run: `python process_documents.py pdfs md`
- Markdown run: `python process_documents.py md` (titles with AI and saves `.md/.html` next to Instapaper in `Posts/Posts <YEAR>/`)
- Tweet → Markdown helper: `python utils/tweet_to_markdown.py https://x.com/...` (saves to `Incoming/` by default)
- MD → HTML (Incoming): `python md_to_html.py`
- Tests (verbose): `pytest -v`
- Targeted tests: `pytest tests/test_podcast_processor.py -q`

## Deploy & Verify (Web)
- Remote deploy (production-safe): `env PERSONAL_WEB_DIR=/path/to/personal-web REMOTE_USER=root REMOTE_HOST=<SERVER_IP> bash web/deploy.sh`
- Two-site model (must stay explicit):
  - `sitio biblioteca` = local source under `BASE_DIR` (for example `⭐️ Documentación`), where pipelines write files (including `Tweets/Tweets <YEAR>/Consolidado Tweets YYYY-MM-DD.{md,html}`).
  - `sitio publicado` = static web artifacts under `web/public/read/`, which are the files deployed and served by Nginx at `/read/`.
- What it does:
  - Generates a static `read.html` index for `/public/read` (HTML + PDF), ordered by mtime desc (bumps first), grouped by year, with entries like: `FileName — YYYY-Mon-DD HH:MM`.
  - Syncs consolidated tweets from `BASE_DIR/Tweets/Tweets <YEAR>/Consolidado Tweets *.html` into `/public/read/tweets/<YEAR>/`.
  - Generates tweet index pages under `/public/read/tweets` (`read.html` + `<YEAR>.html`) linking to files under `/public/read/tweets/<YEAR>/`.
  - Optionally updates host BasicAuth when `HTPASSWD_USER` and `HTPASSWD_PSS` are set (bcrypt generated on host; no secrets in Git).
  - Bundles `web/Dockerfile`, `web/nginx.conf`, and `web/public/` and deploys to `/opt/web-domingo` on the remote host.
  - If `PERSONAL_WEB_DIR` is missing, deploy uses `docflow/web/public` as base site (only `/read`), which can leave the personal site root empty.
  - Rebuilds and runs the container `web-domingo` on port 8080.
- Nginx inside the container:
- `/read/` serves a static `read.html` (no dynamic directory listing module).
  - `/data/` keeps WebDAV-like PUT enabled; listing is via `autoindex on;` (unchanged).
Public checks:
- `curl -I https://domingogallardo.com/` (200 OK)
- `curl -I https://domingogallardo.com/blog/` (200 OK)
- `curl -I https://domingogallardo.com/read/` (200 OK)
- `curl -s https://domingogallardo.com/read/ | head -n 40` (simple UL with "Name — Date", future items at the top)

## Git: Pre-commit/push checks
- Current branch: `git branch --show-current` (must be `main`).
- Remotes: `git remote -v` (origin → https://github.com/domingogallardo/docflow.git).
- Upstream tracking: `git rev-parse --abbrev-ref @{upstream} || echo "(no upstream)"`.
- No pending changes: `git status -sb` (check `??` and ` M`).
- Last commit: `git log -1 --oneline` (Conventional Commit style message).
- No divergence: `git fetch -p && git status -sb` (no `ahead/behind`).
- Push permissions: `git push --dry-run`.

Useful setup (new environment)
- Identity: `git config --get user.name` / `git config --get user.email`.
- Token/SSH: make sure you have valid credentials (GitHub HTTPS token or SSH).
- Default upstream: `git push -u origin main` (only the first time).

Notes for agents
- Do not touch `/data/` auth or methods; `/read/` is a static listing now.
- Note: the old directory-listing CSS is not used anymore by these static indexes.
- If the server is reachable and you have approval, you can run `web/deploy.sh` directly; otherwise provide the exact command for the user to run.
- For `domingogallardo.com` production deploys, require `PERSONAL_WEB_DIR` to be set and valid before running deploy (`test -d "$PERSONAL_WEB_DIR/public"`).
- Canonical local value in this environment: `/Users/domingo/Programacion/personal-web`.
- To preview the index locally without deploying, run: `python utils/build_read_index.py` (generates `read.html` in `web/public/read`, grouped by year and ordered by mtime).
- Local overlay (`utils/serve_docs.py`) offers Bump/Unbump/Publish/Unpublish.
- **Important:** Preserve file `mtime` whenever editing existing content. If a script rewrites HTML/MD, restore `mtime` afterward (use `st_birthtime` on macOS as the source of truth, or capture and reapply the original `mtime`). This keeps chronological ordering stable.

### Fast path for article location (avoid full-disk search)
- For issues referencing article URLs (for example `http://localhost:8000/Posts/Posts%202026/...html`), do **not** search the whole home directory first.
- Resolve `BASE_DIR` from `config.py` and map directly:
  - Local downloaded file: `"$BASE_DIR/Posts/Posts <YEAR>/<decoded filename>.html"`
  - Public web copy in repo: `web/public/read/<decoded filename>.html`
- Decode URL-encoded names (`%20`, `%2C`, etc.) before checking paths.
- Search scope order:
  1. Exact path from URL under `BASE_DIR`
  2. Exact basename in `web/public/read/`
  3. Narrow search under `"$BASE_DIR/Posts"` only
  4. Narrow search under repo only
- Avoid commands like `find /Users/...` unless the user explicitly asks for a full-system search or canonical paths fail.

## Coding Style & Naming
- Python 3.10+; 4-space indentation; keep functions small and cohesive.
- Use type hints where practical and module-level docstrings.
- Modules: `snake_case.py` (e.g., `podcast_processor.py`); classes: `CamelCase` (e.g., `PodcastProcessor`).
- Reuse centralized helpers in `utils.py` (e.g., `markdown_to_html_body`, `wrap_html`, `get_base_css`).
- Keep console messages consistent (English text + emoji), no excessive logging.
- All script messages must be English only.

## Testing Guidelines
- Framework: `pytest`. Add unit tests for new behavior and edge cases.
- Follow existing patterns: temp dirs via `tmp_path`, monkeypatch external I/O, and avoid network.
- Name tests by feature (e.g., `tests/test_instapaper_processor.py`) and use fixtures under `tests/fixtures/`.
- Run `pytest -v` locally; ensure existing tests stay green.

## Commit & Pull Requests
- Commits: prefer Conventional Commit style with optional scope, matching history: `feat(instapaper): ...`, `fix(utils): ...`, `tests(markdown): ...`, `docs: ...`.
- PRs must include: clear description, rationale, before/after notes (sample CLI output ok), updated tests, and any config/env notes.
- If behavior or CLI changes, update `README.md` and this guide as needed.

## Security & Config Tips
- Do not commit secrets. Configure via env vars: `OPENAI_API_KEY`, `INSTAPAPER_USERNAME`, `INSTAPAPER_PASSWORD`, optional `DOCPIPE_YEAR`.
- Adjust `BASE_DIR` in `config.py` for your system (path contains Unicode); keep year-derived subfolders consistent.
