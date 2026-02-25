# Repository Guidelines

This repository automates collecting and organizing personal documents (Instapaper posts, Snipd podcasts, Markdown notes, PDFs, images, tweets) in a local intranet workflow. Keep changes small, tested, and aligned with the current modular design.

## Project Structure & Modules

- Source: top-level Python modules (for example `process_documents.py`, `pipeline_manager.py`, `utils.py`, `*_processor.py`).
- Tests: `tests/` with `pytest` suites and fixtures in `tests/fixtures/`.
- Utilities: `utils/` for helper scripts (for example `docflow_server.py`, `build_browse_index.py`, `build_working_index.py`).
- Configuration: `config.py` (paths and env vars).

## Build, Test, and Dev Commands

- Install deps: `pip install requests beautifulsoup4 markdownify openai pillow pytest markdown`
- Tweet capture deps: `pip install "playwright>=1.55" && playwright install chromium`
- Run full pipeline: `python process_documents.py all --year 2026`
- Selective run: `python process_documents.py pdfs md`
- Tweet queue: `python process_documents.py tweets`
- Create/refresh X likes state: `python utils/create_x_state.py --state-path /Users/<you>/.secrets/docflow/x_state.json`
- Build intranet browse index: `python utils/build_browse_index.py --base-dir "/path/to/BASE_DIR"`
- Build intranet working index: `python utils/build_working_index.py --base-dir "/path/to/BASE_DIR"`
- Run intranet server: `python utils/docflow_server.py --base-dir "/path/to/BASE_DIR" --port 8080`
- Unified wrapper: `bash bin/docflow.sh all`
- Tests (verbose): `pytest -v`
- Targeted tests: `pytest tests/test_docflow_server.py -q`

## Intranet-Only Model

- Single source of truth: `BASE_DIR`.
- Generated site: `BASE_DIR/_site/`.
- Local state: `BASE_DIR/state/` (`done.json`, `bump.json`, `highlights/`).
- No remote deploy flow in this repository.

## Git: Pre-commit/push checks

- Current branch: `git branch --show-current` (must be `main`).
- Remotes: `git remote -v` (origin → `https://github.com/domingogallardo/docflow.git`).
- Upstream tracking: `git rev-parse --abbrev-ref @{upstream} || echo "(no upstream)"`.
- No pending changes: `git status -sb`.
- Last commit: `git log -1 --oneline` (Conventional Commit style message).
- No divergence: `git fetch -p && git status -sb` (no `ahead/behind`).
- Push permissions: `git push --dry-run`.

Useful setup (new environment):

- Identity: `git config --get user.name` / `git config --get user.email`.
- Credentials: valid GitHub HTTPS token or SSH key.
- Default upstream: `git push -u origin main` (first time only).

## Notes for Agents

- Keep all script messages in English.
- Preserve file `mtime` only for existing content files inside `BASE_DIR` (for example articles/pages under `Posts`, `Tweets`, etc.) unless the task explicitly requires changing ordering semantics.
- Do not preserve `mtime` for repository code/docs files outside `BASE_DIR` (for example `docs/*.md`, `utils/*.py`, tests).
- Use intranet routes and local state as canonical behavior (`docflow_server.py`, `_site`, `state`).
- API backward compatibility is not required in this repo: there is a single user/consumer. Prefer removing obsolete API terms and endpoints instead of keeping legacy aliases.
- Long-term operational notes live in `docs/memory.md`.

### Fast path for article location (avoid full-disk search)

- For URLs like `http://localhost:8080/posts/raw/Posts%202026/...html`:
  1. Resolve `BASE_DIR` from `config.py`.
  2. Decode URL-encoded filename.
  3. Check exact path under `BASE_DIR/Posts/Posts <YEAR>/`.
  4. If needed, do narrow search under `"$BASE_DIR/Posts"` only.
- Avoid full-home searches unless explicitly requested.

## Coding Style & Naming

- Python 3.10+; 4-space indentation; keep functions small and cohesive.
- Use type hints where practical and module-level docstrings.
- Modules: `snake_case.py`; classes: `CamelCase`.
- Reuse centralized helpers in `utils.py` where possible.
- Keep console logging concise.

## Testing Guidelines

- Framework: `pytest`.
- Add unit tests for new behavior and edge cases.
- Use `tmp_path` and monkeypatch for I/O isolation; avoid network.
- Name tests by feature (for example `tests/test_docflow_server.py`).

## Commit & Pull Requests

- Prefer Conventional Commits with optional scope (`feat(...)`, `fix(...)`, `tests(...)`, `docs: ...`).
- PRs should include: rationale, behavioral impact, tests, and config/env notes.
- If behavior or CLI changes, update `README.md` and relevant docs.

## Security & Config Tips

- Do not commit secrets.
- Use env vars for credentials: `OPENAI_API_KEY`, `INSTAPAPER_USERNAME`, `INSTAPAPER_PASSWORD`.
- Optional year override: `DOCPIPE_YEAR`.
- Keep `TWEET_LIKES_STATE` outside the repo (for example `/Users/<you>/.secrets/docflow/x_state.json`) to avoid losing session state during repo cleanup.
- Keep `BASE_DIR` in `config.py` aligned with your local environment.
