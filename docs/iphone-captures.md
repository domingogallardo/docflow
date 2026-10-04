# iPhone captures: Safari and Unread → Docflow

`A Docflow` captures one shared article at a time. It saves directly without a menu
or a note prompt. It does not download the page on the phone.

## Installation

The signed installer is in **iCloud Drive → Shortcuts → Docflow → A Docflow.shortcut**.
Open it on the iPhone and add the shortcut if it has not already synchronized
from the Mac. It appears in the share sheet for URLs, Safari webpages, and text.
The first capture may ask for permission to access the selected iCloud folder.

In Unread, open **Settings → Premium Options → Shortcuts → Add Shortcut**,
enter the exact name `A Docflow`, and enable **Reopen Unread**. This integration
requires Unread Premium. Use its shortcut action on an article or a link.
Unread's input format is documented at
<https://www.goldenhillsoftware.com/unread/shortcuts/>.

## Files and ownership

- `iCloud Drive/Shortcuts/Docflow/queue.md`: append-only capture input. The
  shortcut preserves the original input (including Unread's JSON), extracted
  URLs and capture timestamp. The note field is always empty in new captures;
  the consumer still accepts notes in existing queue records. Text fields use Base64 to avoid
  multiline notes or JSON interfering with record boundaries; this is encoding,
  not encryption. Do not edit incomplete captures during synchronization.
  On this Mac, Apple's native Shortcuts folder is physically under
  `~/Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents/Docflow/`;
  it is not an ordinary folder under `com~apple~CloudDocs/Shortcuts`.
- `iCloud Drive/Shortcuts/Docflow/status.md`: generated readable checklist with
  URLs, notes, and errors. A checked item has a verified archived Markdown/HTML
  pair. The Mac never rewrites `queue.md`, avoiding a capture/process write race.
- `BASE_DIR/state/capture_queue.json`: durable local receipts and original
  metadata. Successful downloads are recorded before ingestion, so an
  interruption does not require downloading the article again.
- Documents enter `BASE_DIR/Incoming` and are archived by the existing Markdown
  pipeline in `BASE_DIR/Posts`. New documents retain capture ID, origin, date,
  and optional note in front matter. Existing articles are reused without
  changing content or `mtime`; the receipt retains the new capture note.
- Successful captures are also recorded in `Incoming/processed_history.txt`.

The primary URL from Unread is its `url` field. `article_url` and
`linked_article_url` are retained as metadata, but the consumer does not silently
download those additional links. For some feeds, `article_url` is a comments
page rather than the article selected for sharing.

## Execution

Load `~/.docflow_env` before direct commands:

```bash
source ~/.docflow_env
bash bin/docflow-captures.sh --dry-run
bash bin/docflow-captures.sh
```

The wrapper acquires the same `docflow-all.lock` as the full-pipeline cron.
It skips a busy lock rather than overlapping an ingestion run. It uses the
configured Python and resolves `BASE_DIR` through `DOCFLOW_BASE_DIR`.
The downloader uses the existing Obsidian Clipper CLI and its quality checks.
The existing `bin/docflow.sh md` wrapper then ingests Markdown and rebuilds
the intranet indexes. Only an archived, nonempty Markdown/HTML pair completes
the capture. Login/paywall/extraction failures remain pending for the next run
and are shown in `status.md`; browser recovery is a manual follow-up.

Cron runs at **23:30 each day**, in the Mac's local timezone, via
`computer-ops/ops/bin/docflow_captures.sh`. Output joins the existing
`~/Library/Logs/remotecontrol/docflow.cron.log`. Like the other cron jobs, it
does not wake a sleeping Mac or catch up a missed run.

## Rebuild the installer

```bash
source ~/.docflow_env
python3 utils/build_capture_shortcut.py /tmp/docflow-unsigned.shortcut
shortcuts sign --mode anyone --input /tmp/docflow-unsigned.shortcut \
  --output "$HOME/Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents/Docflow/A Docflow.shortcut"
```

Signing uses Apple's native tool. Review and import the signed file in Atajos.
Do not write directly to the app's database.

## Validation

```bash
source ~/.docflow_env
"${PYTHON_BIN:-python3}" -m pytest tests/test_capture_shortcut.py tests/test_capture_queue.py tests/test_web_url_pipeline.py tests/test_markdown_processor.py -q
```

For device verification, share one public URL from Safari, then one article
from Unread. No choice or note prompt should appear. Check that two captures reach the Mac, run the consumer,
and verify both completed items in `status.md`. Run again to confirm there are
no pending entries and no duplicate downloads.

## Installation checkpoint (2026-10-04)

The backend, native iCloud folder, signed installer, and 23:30 cron are prepared.
The Mac CLI capture test now writes a valid record. The public Unread Shortcuts
page was downloaded and archived as a nonempty Markdown/HTML pair; `status.md`
shows it completed, and a second consumer run performs no download or ingestion.
The trial exposed empty date and extracted-URL fields: the generator now uses
`WFDate` for date formatting and a `WFTextTokenString` input for URL detection.
The signed installer has been updated and imported on the Mac. A native CLI
run completed without interaction, appended a second valid capture with an
ISO timestamp and extracted URL, and left the note empty. All 36 targeted
tests pass. The iPhone Unread test also succeeded: a new article capture reached the Mac
with a timestamp and an empty note, without any menu or prompt. Safari device
capture remains to be checked. The current shortcut saves directly.
The setup-only earlier versions remain in Atajos with suffixed names; use the
exact name `A Docflow`.
