# Intranet Mode

Current local-first behavior for docflow.

## Scope

- Source of truth: `BASE_DIR`.
- One server process: `python utils/docflow_server.py`.
- No public web deploy flow in this repository.

## Generated outputs and state

Static output under `BASE_DIR/_site`:

- `index.html`
- `browse/...`
- `read/...`
- `assets/...`

Local state under `BASE_DIR/state`:

- `published.json`
- `bump.json`
- `highlights/...`

## Browse and Read behavior

- `browse`: full library navigation by category (`posts`, `tweets`, `pdfs`, `images`, `podcasts`).
- `incoming` is intentionally excluded from browse navigation.
- `read`: curated list from `state/published.json`.
- Highlight marks (🟡) come from canonical local highlight state only.

## Bump semantics

- Bump is state-based.
- `state/bump.json` controls sort priority.
- File `mtime` is not modified by bump/unbump actions.

## Server routes and API

`utils/docflow_server.py` serves:

- Static files from `_site`
- Raw files from `BASE_DIR` via `/posts/raw/...`, `/pdfs/raw/...`, etc.
- API endpoints:
  - `POST /api/publish`
  - `POST /api/unpublish`
  - `POST /api/bump`
  - `POST /api/unbump`
  - `POST /api/delete`
  - `POST /api/rebuild`
  - `GET /api/highlights?path=<rel_path>`
  - `PUT /api/highlights?path=<rel_path>`

## Rebuild model

- Startup rebuild is optional (`--rebuild-on-start`).
- Per-file API actions trigger:
  - partial browse rebuild for the affected branch
  - full read rebuild
- `POST /api/rebuild` triggers full browse + read rebuild.

## `bin/docflow.sh all`

`bin/docflow.sh` now runs the local flow only:

- executes `process_documents.py`
- optionally runs tweet daily consolidation (`--yesterday` when target is `all`)
- rebuilds intranet browse and read

Optional override:

- `INTRANET_BASE_DIR=/path/to/base`

## X Likes session state

- Store Playwright `storage_state` outside the repository.
- Recommended path: `/Users/<you>/.secrets/docflow/x_state.json`
- Set it in `~/.docflow_env`:
  - `export TWEET_LIKES_STATE=/Users/<you>/.secrets/docflow/x_state.json`
- Generate/refresh it with:
  - `python utils/create_x_state.py --state-path /Users/<you>/.secrets/docflow/x_state.json`

## Tailscale exposure

```bash
python utils/docflow_server.py --base-dir "/Users/domingo/⭐️ Documentación" --host 127.0.0.1 --port 8088
# optional full rebuild before serving
python utils/docflow_server.py --base-dir "/Users/domingo/⭐️ Documentación" --rebuild-on-start

# publish inside your tailnet
tailscale serve --bg 8088
tailscale serve status
```

## Auto-start on macOS

Use a user `LaunchAgent` (`~/Library/LaunchAgents/com.domingo.docflow.intranet.plist`) so intranet starts at login and restarts if it exits.

Load/update it:

```bash
launchctl bootout gui/$(id -u)/com.domingo.docflow.intranet 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.domingo.docflow.intranet.plist
launchctl kickstart -k gui/$(id -u)/com.domingo.docflow.intranet
```

Check status and logs:

```bash
launchctl print gui/$(id -u)/com.domingo.docflow.intranet | head -n 40
tail -f ~/Library/Logs/docflow/intranet.out.log
tail -f ~/Library/Logs/docflow/intranet.err.log
```
