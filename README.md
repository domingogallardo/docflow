# docflow (Local Intranet)

docflow automates your personal document pipeline (Instapaper posts, podcasts, Markdown notes, PDFs, images, and tweets) and serves everything locally from `BASE_DIR`.

## What this repo does now

- Single local source of truth: `BASE_DIR` (configured in `config.py`).
- Single local server: `python utils/docflow_server.py`.
- Static site output under `BASE_DIR/_site`.
- Local state under `BASE_DIR/state`.
- No remote deploy flow in this repository.

## Main folders

`BASE_DIR` is expected to contain:

- `Incoming/`
- `Posts/Posts <YEAR>/`
- `Tweets/Tweets <YEAR>/`
- `Podcasts/Podcasts <YEAR>/`
- `Pdfs/Pdfs <YEAR>/`
- `Images/Images <YEAR>/`
- `_site/` (generated)
- `state/` (generated)

## Requirements

- Python 3.10+
- Core dependencies:

```bash
pip install requests beautifulsoup4 markdownify openai pillow pytest markdown
```

Optional for X likes queue:

```bash
pip install "playwright>=1.55"
playwright install chromium
```

## Quick start

1. Configure environment variables (as needed):

```bash
export OPENAI_API_KEY=...
export INSTAPAPER_USERNAME=...
export INSTAPAPER_PASSWORD=...
export TWEET_LIKES_STATE=/Users/<you>/.secrets/docflow/x_state.json
export TWEET_LIKES_URL=https://x.com/<user>/likes
export TWEET_LIKES_MAX=50
```

Keep `TWEET_LIKES_STATE` outside the repo so cleanup operations do not delete it.

2. Run the processing pipeline:

```bash
python process_documents.py all --year 2026
```

3. Build local intranet pages:

```bash
python utils/build_browse_index.py --base-dir "/Users/domingo/⭐️ Documentación"
python utils/build_read_index.py --base-dir "/Users/domingo/⭐️ Documentación"
```

4. Run local server:

```bash
python utils/docflow_server.py --base-dir "/Users/domingo/⭐️ Documentación" --host 127.0.0.1 --port 8088
```

Optional full rebuild at startup:

```bash
python utils/docflow_server.py --base-dir "/Users/domingo/⭐️ Documentación" --rebuild-on-start
```

## Unified runner (`bin/docflow.sh`)

Use this wrapper for cron/manual runs:

```bash
bash bin/docflow.sh all
```

Behavior:

- Loads `~/.docflow_env` if present.
- Runs `process_documents.py` with your arguments.
- If target is `all`, runs `bin/build_tweet_consolidated.sh --yesterday`.
- Rebuilds intranet browse/read pages (`utils/build_browse_index.py` and `utils/build_read_index.py`) when processing succeeds.

Optional override:

```bash
INTRANET_BASE_DIR="/path/to/base" bash bin/docflow.sh all
```

## Intranet server API

`utils/docflow_server.py` serves:

- Static files from `BASE_DIR/_site`
- Raw files from `BASE_DIR` routes (`/posts/raw/...`, `/tweets/raw/...`, etc.)
- JSON API actions:
  - `POST /api/publish`
  - `POST /api/unpublish`
  - `POST /api/bump`
  - `POST /api/unbump`
  - `POST /api/delete`
  - `POST /api/rebuild`
  - `GET /api/highlights?path=<rel_path>`
  - `PUT /api/highlights?path=<rel_path>`

## Tweet pipeline

- Queue from likes feed:

```bash
python process_documents.py tweets
```

- One-time browser state creation:

```bash
python utils/create_x_state.py --state-path /Users/<you>/.secrets/docflow/x_state.json
```

- Daily consolidated tweets helper:

```bash
bash bin/build_tweet_consolidated.sh
bash bin/build_tweet_consolidated.sh --day 2026-02-13
bash bin/build_tweet_consolidated.sh --all-days
bash bin/build_tweet_consolidated.sh --all-days --cleanup-existing
```

## Tests

Run all tests:

```bash
pytest -v
```

Targeted example:

```bash
pytest tests/test_docflow_server.py -q
```

## Documentation

- `docs/intranet-mode.md`: canonical intranet behavior and rebuild model.
