# Intranet Mode (Local, Tailscale)

Current local-first intranet behavior for docflow.

## Scope

- Host/source of truth: `BASE_DIR` (your local library).
- One server process: `python utils/docflow_server.py`.
- No Docker/public deploy required for local reading/curation.
- Legacy `utils/serve_docs.py` still exists for compatibility, but intranet mode is the current local workflow.

## Generated outputs and state

- Static site output:
  - `BASE_DIR/_site/index.html`
  - `BASE_DIR/_site/browse/...`
  - `BASE_DIR/_site/read/...`
  - `BASE_DIR/_site/assets/...`
- Local state:
  - `BASE_DIR/state/published.json`
  - `BASE_DIR/state/bump.json`
  - `BASE_DIR/state/highlights/...`
- Highlights compatibility: when no canonical state highlight exists, legacy `Posts/Posts <YEAR>/highlights/*.json` is used as read fallback.

## Browse and Read behavior

- `browse` is full-library navigation (categories):
  - `posts`, `tweets`, `pdfs`, `images`, `podcasts`
- `incoming` is intentionally not listed in browse.
- `read` is curated, generated from `published.json`.
- `read` does not generate yearly tweets pages (`/read/tweets/<YEAR>.html`) in intranet mode.

## Bump semantics (important)

- In intranet mode, bump is state-based:
  - It updates `state/bump.json`.
  - It does **not** modify file `mtime`.
- Listing order uses bump state, while displayed dates are the file's real `mtime`.

## Server actions and rebuilds

`utils/docflow_server.py` serves:
- Static files from `_site`
- Raw files from `BASE_DIR` via `/posts/raw/...`, `/pdfs/raw/...`, etc.
- API actions:
  - `POST /api/publish`
  - `POST /api/unpublish`
  - `POST /api/bump`
  - `POST /api/unbump`
  - `POST /api/rebuild`
  - `GET /api/highlights?path=<rel_path>`
  - `PUT /api/highlights?path=<rel_path>`

Rebuild strategy:
- On server start: no rebuild by default.
- Optional startup rebuild with `--rebuild-on-start`.
- On per-file actions (publish/bump/highlights):
  - Partial rebuild for `browse` (affected directory branch only).
  - Full rebuild for `read`.
- On `POST /api/rebuild`: full `browse + read`.

## `bin/docflow.sh all` integration

`bin/docflow.sh all` keeps legacy public-site flow and now also integrates intranet:
- It rebuilds `BASE_DIR/_site/browse` after a successful pipeline run.
- It does **not** rebuild intranet `read` (curation should only change from intranet publish/unpublish actions).
- Optional override:
  - `INTRANET_BASE_DIR=/path/to/base_dir`

## Tailscale exposure

Recommended:

```bash
python utils/docflow_server.py --base-dir "/Users/domingo/⭐️ Documentación" --host 127.0.0.1 --port 8088
# optional full rebuild before serving
python utils/docflow_server.py --base-dir "/Users/domingo/⭐️ Documentación" --rebuild-on-start
tailscale serve --bg 8088
tailscale serve status
```

This gives one URL for both UI and API (buttons work from iPhone/iPad).
