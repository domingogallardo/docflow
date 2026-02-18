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
