# Repository Guidelines

This repository automates collecting and organizing personal documents (Instapaper posts, Snipd podcasts, Tweets, PDFs). Keep changes small, tested, and aligned with the current modular design.

## Project Structure & Modules
- Source: top-level Python modules (e.g., `process_documents.py`, `pipeline_manager.py`, `utils.py`, `*_processor.py`).
- Tests: `tests/` with `pytest` suites and fixtures in `tests/fixtures/`.
- Utilities: `utils/` for helper scripts (e.g., `serve_html.py`, `rebuild_processed_history.py`).
- Configuration: `config.py` (paths, env vars). Destinations use `BASE_DIR` with year-based folders like `Posts/Posts <AÑO>/`.

## Build, Test, and Dev Commands
- Install deps: `pip install requests beautifulsoup4 markdownify anthropic pillow pytest markdown`
- Run pipeline: `python process_documents.py all --year 2025`
- Selective run: `python process_documents.py tweets pdfs`
- Markdown run: `python process_documents.py md` (titula con IA y guarda los `.md/.html` junto a Instapaper en `Posts/Posts <AÑO>/`)
- MD → HTML (Incoming): `python md_to_html.py`
- Tests (verbose): `pytest -v`
- Targeted tests: `pytest tests/test_podcast_processor.py -q`

## Deploy & Verify (Web)
- Remote deploy: `env REMOTE_USER=root REMOTE_HOST=<SERVER_IP> bash web/deploy.sh`
- What it does:
  - Generates a minimal static index for `/public/read` (HTML + PDF), ordered by mtime desc (bumps first), with entries as: `FileName — YYYY-Mon-DD HH:MM`.
  - If `web/public/read/read_posts.md` exists, it adds a `<hr/>` and lists those filenames below in the order provided. Files under the separator represent items already read/studied (completed). Lines allow `- `, `* ` bullets and `#` comments.
  - Optionally updates host BasicAuth when `HTPASSWD_USER` and `HTPASSWD_PSS` are set (bcrypt generated on host; no secrets in Git).
  - Bundles `web/Dockerfile`, `web/nginx.conf`, and `web/public/` and deploys to `/opt/web-domingo` on the remote host.
  - Rebuilds and runs the container `web-domingo` on port 8080.
- Nginx inside the container:
- `/read/` serves a static `index.html` (no dynamic directory listing module).
  - `/data/` keeps WebDAV-like PUT enabled; listing is via `autoindex on;` (unchanged).
Public checks:
- `curl -I https://domingogallardo.com/read/` (200 OK)
- `curl -s https://domingogallardo.com/read/ | head -n 40` (UL simple con “Nombre — Fecha”, futuro arriba)

## Git: Checks previos a commit/push
- Rama actual: `git branch --show-current` (debe ser `main`).
- Remotos: `git remote -v` (origin → https://github.com/domingogallardo/docflow.git).
- Upstream tracking: `git rev-parse --abbrev-ref @{upstream} || echo "(sin upstream)"`.
- Sin cambios pendientes: `git status -sb` (revisa `??` y ` M`).
- Último commit: `git log -1 --oneline` (mensaje estilo Conventional Commits).
- Sin divergencias: `git fetch -p && git status -sb` (no `ahead/behind`).
- Permisos de push: `git push --dry-run`.

Configuración útil (si es un entorno nuevo)
- Identidad: `git config --get user.name` / `git config --get user.email`.
- Token/SSH: asegúrate de tener credenciales válidas (GitHub HTTPS token o SSH).
- Upstream por defecto: `git push -u origin main` (solo la primera vez).

Notes for agents
- Do not touch `/data/` auth or methods; `/read/` is a static listing now.
- Note: the old directory-listing CSS is not used anymore by these static indexes.
- If the server is reachable and you have approval, you can run `web/deploy.sh` directly; otherwise provide the exact command for the user to run.
- To preview the index locally without deploying, run: `python utils/build_read_index.py` (uses `web/public/read/read_posts.md`).
 - Local overlay (`utils/serve_docs.py`) includes a “Procesado” button on HTML pages when a file is bumped and published; it unbumps locally, prepends the filename to `web/public/read/read_posts.md`, and triggers a deploy.

## Instapaper Starred & Bump
- Star marking: to mark an Instapaper article as highlighted, simply add a star (⭐) at the beginning of its title in Instapaper.
- Propagation: the pipeline normalizes the title (removes the star for naming), adds `data-instapaper-starred="true"` and `<meta name="instapaper-starred" content="true">` to HTML, and `instapaper_starred: true` front matter to Markdown.
- Auto-bump: starred Instapaper HTML files are automatically bumped (their `mtime` is set to the future) so they sort to the top in date-ordered listings. The local server `utils/serve_docs.py` highlights bumped files (🔥) and allows Unbump from the overlay.

## Coding Style & Naming
- Python 3.10+; 4-space indentation; keep functions small and cohesive.
- Use type hints where practical and module-level docstrings.
- Modules: `snake_case.py` (e.g., `tweet_processor.py`); classes: `CamelCase` (e.g., `TweetProcessor`).
- Reuse centralized helpers in `utils.py` (e.g., `markdown_to_html_body`, `wrap_html`, `get_base_css`).
- Keep console messages consistent (Spanish text + emoji), no excessive logging.

## Testing Guidelines
- Framework: `pytest`. Add unit tests for new behavior and edge cases.
- Follow existing patterns: temp dirs via `tmp_path`, monkeypatch external I/O, and avoid network.
- Name tests by feature (e.g., `tests/test_instapaper_processor.py`) and use fixtures under `tests/fixtures/`.
- Run `pytest -v` locally; ensure existing tests stay green.

## Commit & Pull Requests
- Commits: prefer Conventional Commit style with optional scope, matching history: `feat(instapaper): ...`, `fix(utils): ...`, `tests(tweets): ...`, `docs: ...`.
- PRs must include: clear description, rationale, before/after notes (sample CLI output ok), updated tests, and any config/env notes.
- If behavior or CLI changes, update `README.md` and this guide as needed.

## Security & Config Tips
- Do not commit secrets. Configure via env vars: `ANTHROPIC_API_KEY`, `INSTAPAPER_USERNAME`, `INSTAPAPER_PASSWORD`, optional `DOCPIPE_YEAR`.
- Adjust `BASE_DIR` in `config.py` for your system (path contains Unicode); keep year-derived subfolders consistent.
