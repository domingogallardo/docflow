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
- Overlay integration lives in `utils/docflow_server.py` and is intentionally split in two rows:
  - First row for stage actions (`to-working`, `to-done`, `bump`, etc.).
  - Second row for `Index: ...` and highlight jump controls.
  - Hide highlight jump controls when progress total is `0`.
- Highlight payload normalization in `utils/highlight_store.py` must keep stable `id` values; when a highlight arrives without `id`, generate one deterministically to support legacy data and navigation state.
