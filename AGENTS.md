# Repository Guidelines

This repository automates collecting and organizing personal documents (Instapaper posts, Snipd podcasts, Tweets, PDFs). Keep changes small, tested, and aligned with the current modular design.

## Project Structure & Modules
- Source: top-level Python modules (e.g., `process_documents.py`, `pipeline_manager.py`, `utils.py`, `*_processor.py`).
- Tests: `tests/` with `pytest` suites and fixtures in `tests/fixtures/`.
- Utilities: `utils/` for helper scripts (e.g., `serve_html.py`, `rebuild_historial.py`).
- Configuration: `config.py` (paths, env vars). Destinations use `BASE_DIR` with year-based folders like `Posts/Posts <AÑO>/`.

## Build, Test, and Dev Commands
- Install deps: `pip install requests beautifulsoup4 markdownify anthropic pillow pytest markdown`
- Run pipeline: `python process_documents.py all --year 2025`
- Selective run: `python process_documents.py tweets pdfs`
- MD → HTML (Incoming): `python md_to_html.py`
- Tests (verbose): `pytest -v`
- Targeted tests: `pytest tests/test_podcast_processor.py -q`

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
