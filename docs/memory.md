# Agent Memory

This file stores stable, reusable operational notes for future agent runs.

## Notes

### Reading/Working Are State-Driven

- `Reading` and `Working` are managed through state, not by moving files into stage directories.
- Canonical source of truth for Reading: `BASE_DIR/state/reading.json`.
- Canonical source of truth: `BASE_DIR/state/working.json`.
- To move an item to Reading, set state with `set_reading_path` (or API `POST /api/to-reading`) using normalized relative paths (for example `Posts/Posts 2026/file.html`).
- To move an item to Working, set state with `set_working_path` (or API `POST /api/to-working`) from Reading.
- To move an item to Done, use `set_done_path` (or API `POST /api/to-done`) from Browse, Reading, or Working.
- On `POST /api/to-done`, `reading_at` and `working_at` (when present) are copied into `done.json` as `reading_started_at` and `working_started_at` so lead time can be computed after completion.
- After Working-related stage changes, regenerate intranet indexes:
  - `python utils/build_browse_index.py --base-dir "/path/to/BASE_DIR"`
  - `python utils/build_reading_index.py --base-dir "/path/to/BASE_DIR"`
  - `python utils/build_working_index.py --base-dir "/path/to/BASE_DIR"`
- Regenerate Done index only if Done state changed:
  - `python utils/build_done_index.py --base-dir "/path/to/BASE_DIR"`

### Highlight Navigation Overlay

- Canonical highlight navigation logic lives in `utils/static/article.js` and is exposed via:
  - `ArticleJS.nextHighlight()`
  - `ArticleJS.previousHighlight()`
  - `ArticleJS.getHighlightProgress()`
  - `articlejs:highlight-progress` (document event)
- Overlay integration lives in `utils/docflow_server.py` and is intentionally split in three rows:
  - First row: status context link (`Inside Browse|Reading|Working|Done`) to the current Kanban list view.
  - Second row: stage actions (`to-reading`, `to-working`, `to-done`, etc.).
  - Third row: highlight jump controls (`Jump to highlight:` + counter + up/down controls).
  - Keep the third row hidden when highlight progress total is `0`.
- Highlight payload normalization in `utils/highlight_store.py` must keep stable `id` values; when a highlight arrives without `id`, generate one deterministically to support legacy data and navigation state.

### Daily Highlights Report

- Canonical generator: `utils/build_daily_highlights_report.py`.
- Build one file per day using `--day YYYY-MM-DD` and `--output /path/report.md`.
- For legacy highlight payloads, always read via `load_highlights_for_path(...)` before rendering so missing ids are normalized.
- Output structure:
  - One header per source file: `### [<file stem>](<intranet raw url>)`.
  - Highlights grouped by subsection title (title shown once in bold per group).
  - Each highlight block contains quoted text plus `[Highlight](<...#hl=<id>>)` deep link.
  - Only fall back to `#:~:text=...` when an id is not available.
- If highlights point to deleted source files, remove those stale highlights from `BASE_DIR/state/highlights` and regenerate daily reports.

### Hash Deep Links

- `utils/static/article.js` supports deep links to a highlight id in the URL hash:
  - `#hl=<id>` (primary)
  - `#highlight=<id>` (alias)
- Public API includes `ArticleJS.focusHighlightById(id, options)` and it is used to focus entries opened from report links.
- `utils/docflow_server.py` overlay script must refresh highlight progress after hash changes and shortly after mount so the `Jump to highlight` counter reflects the focused item.

### Intranet Port

- Local intranet default port is standardized to `8080`.
- Keep defaults aligned in:
  - `utils/docflow_server.py` (`DOCFLOW_PORT` fallback)
  - `utils/random-post.py` (fallback base URL)
- Documentation examples should use `http://localhost:8080` unless explicitly overridden.

### BASE_DIR Source

- `BASE_DIR` is resolved from env var `DOCFLOW_BASE_DIR` (not hardcoded in `config.py`).
- Canonical place to define it: `~/.docflow_env`.
- For direct shell commands in this repo, run `source ~/.docflow_env` first so imports of `config.py` work consistently.
- Keep related env vars in the same file when possible (`INTRANET_BASE_DIR`, `HIGHLIGHTS_DAILY_DIR`, `TWEET_LIKES_STATE`).

### Clipboard Cleaner Shortcut

- Canonical clipboard-cleaning command is `bin/mdclip` (wrapper for `utils/clipboard_cleaner.py`).
- `utils/clipboard_cleaner.py` is the source of truth for HTML-to-Markdown cleanup behavior.
- Keyboard shortcut mapping (for example `cmd+shift+L`) is managed outside this repo; only the executable command is versioned here.
- If cleanup behavior changes, update `tests/test_clipboard_cleaner.py` accordingly.

### Client-Side Sort Direction For Kanban Lists

- List pages using `assets/browse-sort.js` are reordered client-side on `DOMContentLoaded` using `data-dg-sort-mtime`.
- Default direction is descending (`newest first`) unless the page sets `data-dg-sort-direction="asc"` on the `data-dg-sort-toggle` element.
- For `Reading` (`oldest first`), server-side ordering alone is not enough; the page must explicitly set `data-dg-sort-direction="asc"` or the browser will show newest first.
- After changing sort behavior in `utils/build_browse_index.py`, regenerate browse assets (`python utils/build_browse_index.py --base-dir "<BASE_DIR>"`) so `_site/assets/browse-sort.js` is updated.

## Diary

### 2026-02-26

- Moved exact filename search from `/browse/` to home (`/`) and updated tests.
- Changed Reading ordering to `reading_at` oldest first (inverse of previous behavior) in generator + docs + tests.
- Found and fixed a client-side override: `assets/browse-sort.js` was forcing descending order on load.
- Added support for per-page sort direction in `browse-sort.js` and set `Reading` toggle to `data-dg-sort-direction="asc"`.
- Rebuilt indexes/assets, restarted `docflow_server`, and verified in browser (`/reading/?_r=...`) that oldest appears first.
