# Repository Guidelines

This repository automates collecting and organizing personal documents (Instapaper posts, Snipd podcasts, Markdown notes, PDFs, tweets via a dedicated pipeline). Keep changes small, tested, and aligned with the current modular design.

## Project Structure & Modules
- Source: top-level Python modules (e.g., `process_documents.py`, `pipeline_manager.py`, `utils.py`, `*_processor.py`).
- Tests: `tests/` with `pytest` suites and fixtures in `tests/fixtures/`.
- Utilities: `utils/` for helper scripts (e.g., `serve_html.py`, `rebuild_processed_history.py`).
- Configuration: `config.py` (paths, env vars). Destinations use `BASE_DIR` with year-based folders like `Posts/Posts <YEAR>/`.

## Build, Test, and Dev Commands
- Install deps: `pip install requests beautifulsoup4 markdownify openai pillow pytest markdown`
- Tweet capture deps: `pip install playwright && playwright install chromium`
- Run pipeline: `python process_documents.py all --year 2025`
- Tweets queue: `python process_documents.py tweets` opens your X likes with Playwright (`TWEET_LIKES_STATE`, `TWEET_LIKES_URL`) until it finds the last tweet recorded in `Incoming/tweets_processed.txt`, avoids duplicates, and completes the Markdown/HTML pipeline
- Selective run: `python process_documents.py pdfs md`
- Markdown run: `python process_documents.py md` (titles with AI and saves `.md/.html` next to Instapaper in `Posts/Posts <YEAR>/`)
- Tweet → Markdown helper: `python utils/tweet_to_markdown.py https://x.com/...` (saves to `Incoming/` by default)
- MD → HTML (Incoming): `python md_to_html.py`
- Tests (verbose): `pytest -v`
- Targeted tests: `pytest tests/test_podcast_processor.py -q`

## Deploy & Verify (Web)
- Remote deploy: `env REMOTE_USER=root REMOTE_HOST=<SERVER_IP> bash web/deploy.sh`
- What it does:
  - Generates a minimal static index for `/public/read` (HTML + PDF), ordered by mtime desc (bumps first), with entries like: `FileName — YYYY-Mon-DD HH:MM`.
  - Optionally updates host BasicAuth when `HTPASSWD_USER` and `HTPASSWD_PSS` are set (bcrypt generated on host; no secrets in Git).
  - Bundles `web/Dockerfile`, `web/nginx.conf`, and `web/public/` and deploys to `/opt/web-domingo` on the remote host.
  - Rebuilds and runs the container `web-domingo` on port 8080.
- Nginx inside the container:
- `/read/` serves a static `index.html` (no dynamic directory listing module).
  - `/data/` keeps WebDAV-like PUT enabled; listing is via `autoindex on;` (unchanged).
Public checks:
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
- To preview the index locally without deploying, run: `python utils/build_read_index.py` (single list ordered by mtime).
- Local overlay (`utils/serve_docs.py`) offers Bump/Unbump/Publish/Unpublish.
- Whenever you change the base code, check whether the change should also be reflected in standalone scripts (for example, `utils/standalone_*.py`).
- By default, user requests refer to the main pipeline code; only update standalone scripts after the user confirms the base change.

## Instapaper Starred & Bump
- Star marking: to highlight an Instapaper article, add a star (⭐) at the beginning of its title in Instapaper.
- Propagation: the pipeline normalizes the title (removes the star for naming), adds `data-instapaper-starred="true"` and `<meta name="instapaper-starred" content="true">` to HTML, and `instapaper_starred: true` front matter to Markdown.
- Auto-bump: starred Instapaper HTML files are automatically bumped (their `mtime` is set to the future) so they sort to the top in date-ordered listings. The local server `utils/serve_docs.py` highlights bumped files (🔥) and allows Unbump from the overlay.

## Coding Style & Naming
- Python 3.10+; 4-space indentation; keep functions small and cohesive.
- Use type hints where practical and module-level docstrings.
- Modules: `snake_case.py` (e.g., `podcast_processor.py`); classes: `CamelCase` (e.g., `PodcastProcessor`).
- Reuse centralized helpers in `utils.py` (e.g., `markdown_to_html_body`, `wrap_html`, `get_base_css`).
- Keep console messages consistent (Spanish text + emoji), no excessive logging.

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
