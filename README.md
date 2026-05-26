# docflow (Local Intranet)

docflow automates your personal document pipeline (web URLs, podcasts, Markdown notes, PDFs, images, and tweets) and serves everything locally from `BASE_DIR`.

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

### Local intranet service

- `utils/docflow_server.py` serves the intranet at `http://localhost:8080` by default.
- It serves generated `_site` pages plus raw library content under
  `/incoming/raw/...`, `/posts/raw/...`, `/tweets/raw/...`, `/pdfs/raw/...`,
  `/images/raw/...`, `/podcasts/raw/...`, and `/files/raw/...`.
- PDFs listed in the intranet open through the reader route
  `/pdfs/view/...`; `/pdfs/raw/...` remains the raw PDF route.
- The current personal deployment can run that server from a LaunchAgent, but
  the LaunchAgent plist and other machine-specific schedulers are not part of
  this repository.

### Intranet capabilities

`utils/docflow_server.py` currently offers:

- Home page with title search and `History`, a recent list derived from saved meaningful reading positions.
- Browse / Reading / Done views.
- Browse hides items already in Reading / Done.
- Browse list pages include topical filter buttons next to the highlight toggle, with a dice button to refresh suggestions.
- Highlight toggle on list pages, with browser-persistent state until switched back off.
- With `Highlight: on`, highlighted items move first and are ordered by most recent highlight.
- In `Done`, `Highlight: on` regroups items by the year of the latest highlight, so re-highlighted older items surface under the current highlight year.
- Reading ordered by latest reading activity: `docflow_last_read` when present, otherwise `reading_at` (newest first).
- Done ordered by `done_at` (newest first).
- Stage transitions from the UI (`Move to Reading`, `Move to Done`, `Back to Browse`, `Reopen to Reading`).
- Per-article actions in the overlay:
  - Context link (`Up to Browse`, `Up to Reading`, `Up to Done`)
  - `PDF` export
  - `MD` export
  - `Rebuild`
  - `Delete`
- `Delete` normally removes both the opened HTML file and its same-stem
  Markdown source. Tweet HTML is special: if its Markdown sibling has
  `source: tweet`, only the HTML is removed; the Markdown is kept as
  `markdown_only`.
- Highlight navigation on article pages when highlights exist (`Jump to highlight`, previous/next controls).
- Article pages remember the last meaningful reading position and resume it on reopen unless the URL already targets an explicit hash/deep link.
- PDF files open in the intranet PDF viewer and resume on the last saved page.
- PDF ingestion creates same-stem Markdown sidecars with `docflow_pdf_path`, so PDFs can carry reading metadata and participate in Reading order.

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
- `GET /api/pdf-page?path=<rel_path>&page=<number>`
- `GET /api/highlights?path=<rel_path>`
- `PUT /api/highlights?path=<rel_path>`
- `GET /api/reading-position?path=<rel_path>`
- `PUT /api/reading-position?path=<rel_path>`

`GET /api/export-markdown` returns the Markdown as an HTTP attachment with an explicit `.md` filename in both `filename` and `filename*`.

If `DONE_LINKS_FILE` is set, a `POST /api/to-done` transition on the canonical
`DOCFLOW_BASE_DIR` appends a Markdown link entry to that file.

### Local state files

All state is stored under `BASE_DIR/state/`:

- `reading.json`: per-path `reading_at` timestamp.
- `done.json`: per-path `done_at` timestamp and optional transition metadata copied on `to-done`:
  - `reading_started_at` (from `reading_at` when moving from Reading to Done)
- `highlights/<sha256-prefix>/<sha256>.json`: canonical per-document highlight payloads, including per-highlight `created_at` timestamps and document `updated_at`.
- `reading_positions/<sha256-prefix>/<sha256>.json`: canonical per-document reading-position payloads (`scroll_y`, `max_scroll`, `progress`, viewport/document height metadata, and PDF `page` / `page_count` metadata).

#### Home History semantics

The home `History` link currently reads `BASE_DIR/_site/history-index.json`.
That generated JSON is a projection of `BASE_DIR/state/reading_positions/`,
sorted by the saved reading-position `updated_at` timestamp descending.

`History` is therefore not yet an independent visit log:

- A document appears after Docflow saves a meaningful reading position for it.
- Opening a document without a meaningful progress/page save may not add it.
- Moving an HTML article back to its beginning can remove its saved reading-position JSON and make it disappear from `History`.
- Moving a PDF back to its first page can do the same when no other meaningful resume position remains.

This is intentional for the current implementation: `reading_positions/` answers
"where should reading resume?", while a durable "which documents were visited?"
history would need separate state.

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
- `docflow_markdown_path`, `docflow_html_path`, and `docflow_pdf_path`:
  reciprocal paths, relative to `BASE_DIR` when available, linking each
  Markdown file to its generated HTML or associated PDF pair.
- `docflow_render_status`: whether the Markdown has a generated HTML pair
  (`paired_html`) or is intentionally stored as Markdown only (`markdown_only`).
- `source`: logical source preserved from the pipeline (`tweet`, `podcast`,
  a URL, etc.).
- `title`: detected, extracted, or generated title.
- `source_url`: canonical source URL when the item has one.
- `docflow_source_type`: normalized type (`markdown`, `web`, `tweet`,
  `podcast`, or `pdf`).
- `docflow_post_url`: original post/article URL for web posts and tweet
  articles. When possible, docflow infers web post URLs from the first HTTP(S)
  link in the clipped Markdown body.
- `docflow_original_published_at`: original publication date/time discovered
  from the saved article URL, when available.
- `docflow_original_published_source`: where the original publication date was
  found, such as JSON-LD, HTML meta tags, `<time>`, early visible article text,
  or the URL path.
- `docflow_ingested_at`: UTC timestamp for when docflow incorporated the item.
  This is present for newly ingested items; older migrated/normalized posts may
  omit it when no real ingest timestamp is known.
- `docflow_html_generated_at`: UTC timestamp for when docflow generated the
  associated HTML.
- `docflow_body_chars` and `docflow_word_count`: body-only Markdown statistics.
- `docflow_last_read`: latest persisted reading activity timestamp when the
  reader has saved a meaningful resume position and updates the Markdown pair.
- `docflow_summary`: AI-generated Spanish summary for processed Markdown
  content, except tweets. Summaries aim for 3 to 5 sentences, are generated
  from a bounded content sample, and are capped at 500 characters.

Source-specific fields:

- URL clipping: `docflow_extractor`, `docflow_extraction_attempt`,
  `docflow_final_url`, `docflow_original_url`, and
  `docflow_removed_data_images`.
- Podcasts: `podcast_show`, `podcast_episode_title`,
  `podcast_publish_date`, and `podcast_export_date`.
- Tweets: `tweet_url`, `tweet_id`, `tweet_author`, `tweet_author_name`,
  `tweet_capture_source`, `tweet_content_type`, `tweet_posted_kind`,
  `tweet_thread`, `tweet_thread_count`, `tweet_reply_to_url`,
  `tweet_reply_context_included`, `tweet_conversation_count`,
  `tweet_consolidated_url`, and `tweet_consolidated_anchor`.

Supported fields are also exported to generated HTML as `docflow-*` meta tags
where relevant, for example `docflow-source-url`, `docflow-html-generated-at`,
or `docflow-tweet-id`.

### Post folder dates

Post folders represent the year Docflow should file the article under, using
this effective-year rule:

1. Use the year from `docflow_ingested_at` when it exists. This preserves the
   real download/incorporation year for newly processed posts.
2. Otherwise use the year from `docflow_original_published_at` when it exists.
   This lets migrated posts without a real ingest timestamp leave fallback
   folders such as `Posts 1990` and move to the best-known article year.
3. Otherwise keep the post in its current `Posts YYYY` folder.

Do not use `docflow_html_generated_at` for folder placement; it is only a
technical generation timestamp.

Year browse pages group posts by month using the same effective date rule.
`Posts 1990` is treated as an unknown-date holding folder, so it is rendered as
a flat list without month headings.

### Date metadata lifecycle

Newly downloaded or newly processed Markdown gets `docflow_ingested_at` during
metadata enrichment. This is the authoritative timestamp for when Docflow
incorporated the item.

New URL downloads also try to set `docflow_original_published_at` and
`docflow_original_published_source` during clipping, using the already fetched
HTML first and then the first Markdown body lines before falling back to dates
embedded in the URL path.

`utils/backfill_original_article_dates.py` remains available for historical
posts and repairs. The script skips posts that already have
`docflow_original_published_at` unless `--force` is passed.

`utils/backfill_post_ingested_dates_from_mtime.py` repairs post Markdown that
predates the ingest field but has a meaningful file `mtime` after the initial
Docflow normalization window. By default that window ends at
`2025-03-20T23:59:59Z`; after running the backfill, post articles that still
lack both `docflow_ingested_at` and `docflow_original_published_at` should have
a Markdown `mtime` at or before that threshold. The script only scans article
Markdown under `Posts/`, writes missing `docflow_ingested_at` values from the
Markdown `mtime`, mirrors the value to a same-stem HTML file when present, and
preserves both file mtimes.

After adding or refreshing original publication dates, run
`utils/reorganize_posts_by_date.py` to apply the folder rule above, then rebuild
the intranet indexes.

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
pip install requests beautifulsoup4 markdownify openai pillow pytest markdown scikit-learn
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
mkdir -p "$HOME/Repos-Github"
git clone https://github.com/obsidianmd/obsidian-clipper.git \
  "$HOME/Repos-Github/obsidian-clipper"
cd "$HOME/Repos-Github/obsidian-clipper"
npm install
npm run build

export DOCFLOW_OBSIDIAN_CLIPPER_CLI="$HOME/Repos-Github/obsidian-clipper/dist/cli.cjs"
```

docflow uses that `dist/cli.cjs` path by default when the Web Clipper checkout
lives under `$HOME/Repos-Github/obsidian-clipper`. Set
`DOCFLOW_OBSIDIAN_CLIPPER_CLI` when the checkout lives somewhere else.

### Manual quick start

1. Configure environment variables (as needed):

```bash
export OPENAI_API_KEY=...
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

4. Backfill Markdown sidecars for existing PDFs:

```bash
python utils/backfill_pdf_sidecars.py --base-dir "$DOCFLOW_BASE_DIR" --dry-run
python utils/backfill_pdf_sidecars.py --base-dir "$DOCFLOW_BASE_DIR"
```

5. Backfill original publication dates from saved post URLs:

```bash
python utils/backfill_original_article_dates.py --base-dir "$DOCFLOW_BASE_DIR" --dry-run
python utils/backfill_original_article_dates.py --base-dir "$DOCFLOW_BASE_DIR"
```

6. Backfill missing post ingest dates from meaningful mtimes:

```bash
python utils/backfill_post_ingested_dates_from_mtime.py --base-dir "$DOCFLOW_BASE_DIR" --dry-run
python utils/backfill_post_ingested_dates_from_mtime.py --base-dir "$DOCFLOW_BASE_DIR"
```

Use `--after` only when intentionally changing the normalization threshold.

7. Reorganize post folders using the effective date rule:

```bash
python utils/reorganize_posts_by_date.py --base-dir "$DOCFLOW_BASE_DIR" --dry-run
python utils/reorganize_posts_by_date.py --base-dir "$DOCFLOW_BASE_DIR"
```

8. Run the intranet server manually (mainly for troubleshooting):

```bash
source ~/.docflow_env
python utils/docflow_server.py --base-dir "$DOCFLOW_BASE_DIR" --host localhost --port 8080
```

Optional full rebuild at startup:

```bash
source ~/.docflow_env
python utils/docflow_server.py --base-dir "$DOCFLOW_BASE_DIR" --rebuild-on-start
```

### Optional LaunchAgent management

The personal deployment can manage the intranet server through a LaunchAgent
named `com.domingo.docflow.intranet`. The plist is maintained outside this
repository; when it is installed, restart it with:

```bash
launchctl kickstart -k "gui/$(id -u)/com.domingo.docflow.intranet"
```

Useful status checks:

```bash
launchctl print "gui/$(id -u)/com.domingo.docflow.intranet" | rg 'state =|pid =|last exit code ='
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/
```

If a LaunchAgent is not loaded yet in a new environment:

```bash
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.domingo.docflow.intranet.plist
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

Each entry in a daily consolidated tweet HTML has a stable anchor, preferably
`tweet-<tweet_id>`. Source tweet Markdown gets `tweet_consolidated_url` pointing
to `/tweets/raw/.../<consolidated>.html#<anchor>` and
`tweet_consolidated_anchor` with the anchor id. These fields are kept in the
Markdown source so future search/index features can surface tweet Markdown and
open the reader at the consolidated entry.

`--cleanup-existing` removes source tweet `.html` files for consolidated days and keeps source `.md`.
Markdown sources whose HTML is removed are marked as `docflow_render_status: markdown_only`
and have stale `docflow_html_path` removed without changing their `mtime`. Tweet HTML files
already in Reading or Done are kept with their existing state and highlights.

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
