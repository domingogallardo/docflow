# docflow (Local Intranet)

docflow automates your personal document pipeline (web URLs, Instapaper posts, podcasts, Markdown notes, PDFs, images, and tweets) and serves everything locally from `BASE_DIR`.

Podcast snippets are typically captured in [Snipd](https://www.snipd.com) and then exported into this pipeline.

## Architecture overview

![docflow architecture](docs/images/docflow-architecture.webp)

## Current functionality

- Single local source of truth: `BASE_DIR` (resolved from `DOCFLOW_BASE_DIR`, typically in `~/.docflow_env`).
- Static site output under `BASE_DIR/_site`.
- Local workflow state under `BASE_DIR/state`.
- Markdown and PDF ingestion reads files from `BASE_DIR/Incoming/`.
- URL ingestion reads `BASE_DIR/Incoming/links.txt`, downloads articles as Markdown, and leaves failed URLs queued for retry.
- Tweet ingestion also extracts the main external article link from each downloaded tweet/thread and queues it for the Web Clipper.
- Image ingestion moves files into the yearly folder and, when `OPENAI_API_KEY` is configured, renames them with an AI-generated descriptive filename before rebuilding the gallery.

### Local services currently in use

- Intranet at `http://localhost:8080`
  - Managed day to day by LaunchAgent `com.domingo.docflow.intranet`.
  - Serves the generated site plus raw content under `/posts/raw/...`, `/tweets/raw/...`, `/pdfs/raw/...`, `/images/raw/...`, and `/podcasts/raw/...`.
- RemoteControl at `http://localhost:3000`
  - Managed by LaunchAgent `com.domingo.remotecontrol.web`.
  - Exposes an on-demand docflow task (`Docflow: descargar/documentar`) alongside non-docflow tasks.

### Intranet capabilities

`utils/docflow_server.py` currently offers:

- Home page with exact filename search.
- Browse / Reading / Done views.
- Browse hides items already in Reading / Done.
- Highlight toggle on list pages, with browser-persistent state until switched back off.
- With `Highlight: on`, highlighted items move first and are ordered by most recent highlight.
- In `Done`, `Highlight: on` regroups items by the year of the latest highlight, so re-highlighted older items surface under the current highlight year.
- Reading ordered by `reading_at` (oldest first).
- Done ordered by `done_at` (newest first).
- Stage transitions from the UI (`Move to Reading`, `Move to Done`, `Back to Browse`, `Reopen to Reading`).
- Per-article actions in the overlay:
  - Context link (`Inside Browse`, `Inside Reading`, `Inside Done`)
  - `PDF` export
  - `MD` export
  - `Rebuild`
  - `Delete`
- Highlight navigation on article pages when highlights exist (`Jump to highlight`, previous/next controls).
- Article pages remember the last reading position and resume it on reopen unless the URL already targets an explicit hash/deep link.
- PDF files open in the intranet PDF viewer and resume on the last saved page.

### Intranet API

Documented and currently available endpoints:

- `POST /api/to-reading`
- `POST /api/to-done`
- `POST /api/to-browse`
- `POST /api/reopen`
- `POST /api/delete`
- `POST /api/rebuild`
- `POST /api/rebuild-file`
- `GET /api/export-pdf?path=<rel_path>`
- `GET /api/export-markdown?path=<rel_path>`
- `GET /api/highlights?path=<rel_path>`
- `PUT /api/highlights?path=<rel_path>`
- `GET /api/reading-position?path=<rel_path>`
- `PUT /api/reading-position?path=<rel_path>`

`GET /api/export-markdown` returns the Markdown as an HTTP attachment with an explicit `.md` filename in both `filename` and `filename*`.

If `DONE_LINKS_FILE` is set, each `POST /api/to-done` transition appends a Markdown link entry to that file.

### Local state files

All state is stored under `BASE_DIR/state/`:

- `reading.json`: per-path `reading_at` timestamp.
- `done.json`: per-path `done_at` timestamp and optional transition metadata copied on `to-done`:
  - `reading_started_at` (from `reading_at` when moving from Reading to Done)
- `highlights/<sha256-prefix>/<sha256>.json`: canonical per-document highlight payloads, including per-highlight `created_at` timestamps and document `updated_at`.
- `reading_positions/<sha256-prefix>/<sha256>.json`: canonical per-document reading-position payloads (`scroll_y`, `max_scroll`, `progress`, viewport/document height metadata, and PDF `page` / `page_count` metadata).

### Background automations currently in use

The current local setup uses both LaunchAgents and `cron`.

LaunchAgents:

- `~/Library/LaunchAgents/com.domingo.docflow.intranet.plist`
  - Starts the docflow intranet on port `8080`.
- `~/Library/LaunchAgents/com.domingo.remotecontrol.web.plist`
  - Starts the RemoteControl web UI on port `3000`.

Current `crontab` jobs related to docflow:

- Every 6 hours: `/Users/domingo/Programacion/computer-ops/ops/bin/docflow_all.sh`
  - Runs the full ingestion pipeline and rebuilds the intranet outputs.
- Five minutes before each 6-hour run: `/Users/domingo/Programacion/computer-ops/ops/bin/docflow_import_incoming.sh`
  - Prepares `Incoming/` before docflow runs.
- Daily at `02:00`: `/Users/domingo/Programacion/computer-ops/ops/bin/docflow_tweet_daily.sh`
  - Builds the previous day's consolidated tweets and rebuilds the intranet outputs.
- Daily at `01:55`: `/Users/domingo/Programacion/computer-ops/ops/bin/docflow_import_incoming.sh`
  - Prepares `Incoming/` before the nightly docflow jobs.
- Daily at `02:05`: `/Users/domingo/Programacion/computer-ops/ops/bin/docflow_highlights_daily.sh`
  - Builds the previous day's highlights report Markdown.

The shared cron log is:

```bash
~/Library/Logs/remotecontrol/docflow.cron.log
```

### Main folders

`BASE_DIR` is expected to contain:

- `Incoming/`
- `Posts/Posts <YEAR>/`
- `Tweets/Tweets <YEAR>/`
- `Podcasts/Podcasts <YEAR>/`
- `Pdfs/Pdfs <YEAR>/`
- `Images/Images <YEAR>/`
- `_site/` (generated)
- `state/` (generated)

External input files:

- Drop local `.md`, `.pdf`, images, and other source files into `BASE_DIR/Incoming/`.
- URL queue: `BASE_DIR/Incoming/links.txt`
  - The `urls` step downloads each URL as Markdown into `Incoming/`.
  - Successful URLs are removed from `links.txt` and recorded in `processed_history.txt`.
  - Failed URLs stay queued and append timestamped diagnostics to `links_failed.txt`.
  - The `tweets` step appends article links discovered in downloaded tweets so they can be clipped by the `urls` step.

### Markdown metadata

Markdown outputs keep a canonical YAML front matter block. Existing source
fields are preserved, and docflow adds derived fields where available.

Common fields:

- `docflow_id`: stable UUID persisted in the Markdown front matter and mirrored
  into the generated HTML.
- `docflow_markdown_path` and `docflow_html_path`: reciprocal paths, relative
  to `BASE_DIR` when available, linking each Markdown file to its generated
  HTML pair.
- `docflow_render_status`: whether the Markdown has a generated HTML pair
  (`paired_html`) or is intentionally stored as Markdown only (`markdown_only`).
- `source`: logical source preserved from the pipeline (`tweet`, `podcast`,
  `instapaper`, a URL, etc.).
- `title`: detected, extracted, or generated title.
- `source_url`: canonical source URL when the item has one.
- `docflow_source_type`: normalized type (`markdown`, `web`, `tweet`,
  `podcast`, or `instapaper`).
- `docflow_ingested_at`: UTC timestamp for when docflow incorporated the item.
- `docflow_html_generated_at`: UTC timestamp for when docflow generated the
  associated HTML.
- `docflow_body_chars` and `docflow_word_count`: body-only Markdown statistics.
- `docflow_summary`: AI-generated Spanish summary for processed Markdown
  content, except tweets. Summaries aim for 3 to 5 sentences, are generated
  from a bounded content sample, and are capped at 500 characters.

Source-specific fields:

- URL clipping: `docflow_extractor`, `docflow_extraction_attempt`,
  `docflow_final_url`, `docflow_original_url`, and
  `docflow_removed_data_images`.
- Instapaper: `instapaper_id` and `source_name`.
- Podcasts: `podcast_show`, `podcast_episode_title`,
  `podcast_publish_date`, and `podcast_export_date`.
- Tweets: `tweet_url`, `tweet_id`, `tweet_author`, `tweet_author_name`,
  `tweet_capture_source`, `tweet_posted_kind`, `tweet_thread`,
  `tweet_thread_count`, `tweet_reply_to_url`, `tweet_reply_context_included`,
  and `tweet_conversation_count`.

Supported fields are also exported to generated HTML as `docflow-*` meta tags
where relevant, for example `docflow-source-url`, `docflow-html-generated-at`,
or `docflow-tweet-id`.

## Operation and maintenance

### BASE_DIR location

- `BASE_DIR` comes from environment variable `DOCFLOW_BASE_DIR`.
- Canonical place to set it: `~/.docflow_env`.
- If `DOCFLOW_BASE_DIR` is missing, importing `config.py` fails with a clear error.
- For direct commands from this repo, load your environment first:

```bash
source ~/.docflow_env
```

Recommended `~/.docflow_env` snippet:

```bash
export DOCFLOW_BASE_DIR="/path/to/BASE_DIR"
export INTRANET_BASE_DIR="$DOCFLOW_BASE_DIR"
export HIGHLIGHTS_DAILY_DIR="/path/to/Obsidian/Subrayados"
export DONE_LINKS_FILE="/path/to/Obsidian/Leidos.md"
```

### Requirements

- Python 3.10+
- Core dependencies:

```bash
pip install requests beautifulsoup4 markdownify openai pillow pytest markdown
```

Optional for intranet PDF page rendering:

```bash
pip install pymupdf
```

Alternatively, install Poppler tools so `pdfinfo` and `pdftoppm` are available.

Optional for X likes queue:

```bash
pip install "playwright>=1.55"
playwright install chromium
```

Optional for URL-to-Markdown clipping:

```bash
# Requires Node.js and a local Obsidian Web Clipper checkout.
export DOCFLOW_OBSIDIAN_CLIPPER_CLI="$HOME/Repos-Github/obsidian-clipper/dist/cli.cjs"
```

### Manual quick start

1. Configure environment variables (as needed):

```bash
export OPENAI_API_KEY=...
export INSTAPAPER_USERNAME=...
export INSTAPAPER_PASSWORD=...
export DOCFLOW_BASE_DIR="/path/to/BASE_DIR"
export TWEET_LIKES_STATE="$HOME/.secrets/docflow/x_state.json"
export TWEET_LIKES_URL=https://x.com/<user>/likes
export TWEET_LIKES_MAX=50
export TWEET_POSTS_URL=https://x.com/<user>
export TWEET_POSTS_MAX=50
export TWEET_REPLIES_URL=https://x.com/<user>/with_replies
export TWEET_REPLIES_MAX=50
export HIGHLIGHTS_DAILY_DIR="/path/to/Obsidian/Subrayados"
export DONE_LINKS_FILE="/path/to/Obsidian/Leidos.md"
```

Keep `TWEET_LIKES_STATE` outside the repo so cleanup operations do not delete it.
If `TWEET_POSTS_URL` is set, the tweet pipeline also downloads your published tweets, reposts, and replies and tags them separately from likes. Replies are read from `TWEET_REPLIES_URL`, or from `<TWEET_POSTS_URL>/with_replies` when that variable is unset.

2. Run the processing pipeline:

```bash
python process_documents.py all --year 2026
```

For normal local use, prefer the wrapper because it also rebuilds the intranet
indexes after a successful run:

```bash
bash bin/docflow.sh all --year 2026
```

To process only PDFs already present in `Incoming/`, use the matching target:

```bash
bash bin/docflow.sh pdfs --year 2026
```

To download article URLs as Markdown into `Incoming/`, add URLs to
`$DOCFLOW_BASE_DIR/Incoming/links.txt` and run the URL target:

```bash
bash bin/docflow.sh urls
```

Successful URLs are removed from `links.txt` and added to
`Incoming/processed_history.txt`. Failed URLs stay in `links.txt` for retry,
with timestamped error details appended to `Incoming/links_failed.txt`.
The full `all` pipeline runs tweets before URLs, so article links discovered
while downloading tweets are picked up by the Web Clipper in the same run.
Explicit target order is still respected, so run `tweets urls` if you want this
behavior in a selective command.

You can also pass URLs directly:

```bash
bin/urlclip "https://example.com/article"
```

`bin/urlclip` is a low-level downloader for one-off tests; the queue bookkeeping
(`links.txt`, `processed_history.txt`, and `links_failed.txt`) is handled by the
`urls` pipeline target.

3. Build local intranet pages manually:

```bash
python utils/build_browse_index.py --base-dir "$DOCFLOW_BASE_DIR"
python utils/build_reading_index.py --base-dir "$DOCFLOW_BASE_DIR"
python utils/build_done_index.py --base-dir "$DOCFLOW_BASE_DIR"
```

4. Run the intranet server manually (mainly for troubleshooting):

```bash
source ~/.docflow_env
python utils/docflow_server.py --base-dir "$DOCFLOW_BASE_DIR" --host localhost --port 8080
```

Optional full rebuild at startup:

```bash
source ~/.docflow_env
python utils/docflow_server.py --base-dir "$DOCFLOW_BASE_DIR" --rebuild-on-start
```

### LaunchAgent management

Preferred day-to-day usage is the LaunchAgent-managed intranet service:

```bash
launchctl kickstart -k "gui/$(id -u)/com.domingo.docflow.intranet"
```

Useful status checks:

```bash
launchctl print "gui/$(id -u)/com.domingo.docflow.intranet" | rg 'state =|pid =|last exit code ='
launchctl print "gui/$(id -u)/com.domingo.remotecontrol.web" | rg 'state =|pid =|last exit code ='
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3000/
```

If a LaunchAgent is not loaded yet in a new environment:

```bash
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.domingo.docflow.intranet.plist
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.domingo.remotecontrol.web.plist
```

### Cron inspection

Inspect the current scheduled jobs with:

```bash
crontab -l
```

### Manual runners

Full document ingestion runner:

```bash
bash bin/docflow.sh all
```

Behavior:

- Loads `~/.docflow_env` if present.
- Runs `process_documents.py` with your arguments (`all` for full ingestion).
- Rebuilds intranet browse/reading/done pages when processing succeeds.

Optional override:

```bash
INTRANET_BASE_DIR="/path/to/base" bash bin/docflow.sh all
```

Dedicated daily tweet consolidation runner:

```bash
bash bin/docflow_tweet_daily.sh
```

Behavior:

- Loads `~/.docflow_env` if present.
- Runs `bin/build_tweet_consolidated.sh --yesterday --capture-source all`.
- Rebuilds intranet browse/reading/done pages when consolidation succeeds.

Tweet queue from likes feed (and optionally your published tweets/reposts/replies if `TWEET_POSTS_URL` is configured):

```bash
python process_documents.py tweets
```

When tweets are downloaded, docflow scans each captured tweet block for the
first external article-like URL and appends it to `Incoming/links.txt`. It
ignores X/Twitter URLs, `t.co`, tweet media, and quoted-tweet bodies, and skips
URLs already queued or present in `processed_history.txt`. In the full `all`
pipeline, those queued links are downloaded immediately because `tweets` runs
before `urls`.

One-time browser state creation:

```bash
python utils/create_x_state.py --state-path "$HOME/.secrets/docflow/x_state.json"
```

Daily consolidated tweets helper:

```bash
bash bin/build_tweet_consolidated.sh
bash bin/build_tweet_consolidated.sh --capture-source posted
bash bin/build_tweet_consolidated.sh --capture-source all
bash bin/build_tweet_consolidated.sh --day 2026-02-13
bash bin/build_tweet_consolidated.sh --day 2026-02-13 --capture-source posted
bash bin/build_tweet_consolidated.sh --all-days
bash bin/build_tweet_consolidated.sh --all-days --capture-source all
bash bin/build_tweet_consolidated.sh --all-days --cleanup-existing
```

By default, `bin/build_tweet_consolidated.sh` builds liked-tweet consolidations (`Tweets YYYY-MM-DD`).
Use `--capture-source posted` to build published/reposted/reply-tweet consolidations (`Tweets posted YYYY-MM-DD`),
or `--capture-source all` to process both families in one run.

By default, daily grouping for tweet source files uses a local rollover hour at `03:00`
to include just-after-midnight downloads in the previous day. Override with
`DOCFLOW_TWEET_DAY_ROLLOVER_HOUR` (`0`-`23`) when needed.

`--cleanup-existing` removes source tweet `.html` files for consolidated days and keeps source `.md`.
Markdown sources whose HTML is removed are marked as `docflow_render_status: markdown_only`
without changing their `mtime`. Tweet HTML files already in Reading or Done are kept with
their existing state and highlights.

Daily highlights report helper:

```bash
python utils/build_daily_highlights_report.py --day 2026-02-13 --output "/tmp/highlights-2026-02-13.md"
```

If a day has no highlights, the helper exits successfully without writing the note.

Daily highlights report runner:

```bash
bash bin/docflow_highlights_daily.sh
```

Clipboard Markdown helper:

```bash
bin/mdclip
```

Behavior:

- Reads HTML from clipboard when available (`pbpaste -Prefer html`, then macOS pasteboard fallbacks).
- Converts to Markdown and removes extra blank lines between list items.
- Writes cleaned Markdown back to clipboard by default.

Useful flags:

```bash
bin/mdclip --print
bin/mdclip --no-copy
bin/mdclip --from-stdin --no-copy --print < /path/to/input.html
```

Keyboard shortcut bindings (for example `cmd+shift+L`) are configured outside this repo (Shortcuts/automation tool). The versioned command to invoke is `bin/mdclip`.

## Tests

Run all tests:

```bash
pytest -v
```

Targeted example:

```bash
pytest tests/test_docflow_server.py -q
```

## Optional remote access

You can expose the local intranet through a private VPN (for example, Tailscale).
