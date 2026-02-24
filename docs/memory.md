# Agent Memory

This file stores stable, reusable operational notes for future agent runs.

## Working Is State-Driven

- `Working` is managed through state, not by moving files into a `Working/` directory.
- Canonical source of truth: `BASE_DIR/state/working.json`.
- To move an item to Working, set state with `set_working_path` (or API `POST /api/to-working`) using normalized relative paths (for example `Posts/Posts 2026/file.html`).
- After Working-related stage changes, regenerate intranet indexes:
  - `python utils/build_browse_index.py --base-dir "/path/to/BASE_DIR"`
  - `python utils/build_working_index.py --base-dir "/path/to/BASE_DIR"`
- Regenerate Done index only if Done state changed:
  - `python utils/build_done_index.py --base-dir "/path/to/BASE_DIR"`

## Highlight Navigation Overlay

- Canonical highlight navigation logic lives in `utils/static/article.js` and is exposed via:
  - `ArticleJS.nextHighlight()`
  - `ArticleJS.previousHighlight()`
  - `ArticleJS.getHighlightProgress()`
  - `articlejs:highlight-progress` (document event)
- Overlay integration lives in `utils/docflow_server.py` and is intentionally split in three rows:
  - First row: status context link (`Inside Browse|Working|Done`) to the current Kanban list view.
  - Second row: stage actions (`to-working`, `to-done`, `bump`, etc.).
  - Third row: highlight jump controls (`Jump to highlight:` + counter + up/down controls).
  - Keep the third row hidden when highlight progress total is `0`.
- Highlight payload normalization in `utils/highlight_store.py` must keep stable `id` values; when a highlight arrives without `id`, generate one deterministically to support legacy data and navigation state.

## Daily Highlights Report

- Canonical generator: `utils/build_daily_highlights_report.py`.
- Build one file per day using `--day YYYY-MM-DD` and `--output /path/report.md`.
- For legacy highlight payloads, always read via `load_highlights_for_path(...)` before rendering so missing ids are normalized.
- Output structure:
  - One header per source file: `### [<file stem>](<intranet raw url>)`.
  - Highlights grouped by subsection title (title shown once in bold per group).
  - Each highlight block contains quoted text plus `[Highlight](<...#hl=<id>>)` deep link.
  - Only fall back to `#:~:text=...` when an id is not available.
- If highlights point to deleted source files, remove those stale highlights from `BASE_DIR/state/highlights` and regenerate daily reports.

## Hash Deep Links

- `utils/static/article.js` supports deep links to a highlight id in the URL hash:
  - `#hl=<id>` (primary)
  - `#highlight=<id>` (alias)
- Public API includes `ArticleJS.focusHighlightById(id, options)` and it is used to focus entries opened from report links.
- `utils/docflow_server.py` overlay script must refresh highlight progress after hash changes and shortly after mount so the `Jump to highlight` counter reflects the focused item.

## Intranet Port

- Local intranet default port is standardized to `8080`.
- Keep defaults aligned in:
  - `utils/docflow_server.py` (`DOCFLOW_PORT` fallback)
  - `utils/random-post.py` (fallback base URL)
- Documentation examples should use `http://localhost:8080` unless explicitly overridden.

## Tweet Daily Consolidation Schedule

- `bin/docflow.sh all` no longer runs tweet daily consolidation.
- Daily tweet consolidation is handled by `bin/docflow_tweet_daily.sh`.
- Schedule it as a separate cron job at `01:00` and keep intranet rebuilds in that process.
