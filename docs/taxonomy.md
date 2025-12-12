# Taxonomy Outputs & Navigation Contract (Depth=2)

The script `utils/standalone_taxonomy_depth2_llm_only.py` builds a **depth-2 taxonomy** for a directory of Markdown articles:

* **Macro** (top level)
* **Category** (second level; each category belongs to exactly one macro)
* **Tags** (free-form keywords per article)

The pipeline produces JSON/JSONL files that downstream applications can use to **navigate, filter, and display** articles.

---

## Quick start: generating outputs

Example command (paths intentionally generic):

```bash
rm -rf ./out && mkdir -p ./out

python utils/standalone_taxonomy_depth2_llm_only.py \
  --input_dir "./articles" \
  --out_dir "./out" \
  --model gpt-5-mini \
  --votes_per_article 2 \
  --debug
```

Notes:

* `--input_dir` must contain the `.md` articles (recursively).
* `--out_dir` will be created/overwritten by you (the script writes output files there).
* `--votes_per_article` increases cost and stability (2–3 is a good range for higher consistency).
* `--debug` prints LLM retry errors (useful when iterating).

---

## Directory layout assumption (important)

Downstream applications in this project assume the following simple layout:

```
project_root/
  articles/               <-- your Markdown articles (.md)
    a.md
    b.md
  out/                    <-- taxonomy output directory
    canonical_macros.json
    canonical_categories.json
    macro_category_map.json
    assignments.jsonl
    records.jsonl
    report.md
```

**Content resolution rule (simple):**

> To open the full article content, the app joins `input_dir` + `file_name`.

That is: the “real content” is loaded by reading:

```
<input_dir>/<file_name>
```

This works well as long as:

* article file names are unique within `input_dir` (recommended),
* and the taxonomy outputs correspond to the same article directory.

---

## Output files

The script writes the following files to `out_dir/`:

* `canonical_macros.json`
* `canonical_categories.json`
* `macro_category_map.json`
* `assignments.jsonl`
* `records.jsonl` *(recommended for UI)*
* `report.md`
* `assignments_skipped.jsonl` *(if produced)*

Downstream apps should treat `assignments.jsonl` + `macro_category_map.json` as the **source of truth** for navigation.

---

## Concepts and IDs

### Stable IDs

Macros and categories are referenced by stable IDs:

* Macro IDs: `macro_<slug>`
* Category IDs: `cat_<slug>`

**Apps must never key on `label`.** Labels and definitions may be refined later, but IDs are the stable references across files.

### Structure

Each **category belongs to exactly one macro** via `macro_category_map.json`.

Each **article has**:

* exactly one **primary** (macro, category),
* optionally up to two **secondary** (macro, category) pairs,
* plus free-form tags.

---

## File formats

### 1) `canonical_macros.json`

Defines the macro nodes.

Typical shape:

```json
{
  "canonical": [
    {
      "id": "macro_artificial_intelligence",
      "label": "Artificial Intelligence",
      "definition": "Research, engineering, policy, and applications of AI systems.",
      "aliases": ["AI", "Machine Intelligence"]
    }
  ],
  "notes": "..."
}
```

Fields:

* `id`: stable identifier
* `label`: UI label
* `definition`: one-line help text
* `aliases`: optional synonyms (useful for search)

---

### 2) `canonical_categories.json`

Defines the category nodes (same schema as macros).

```json
{
  "canonical": [
    {
      "id": "cat_large_language_models",
      "label": "Large Language Models",
      "definition": "Training, behavior, and deployment of modern LLMs.",
      "aliases": ["LLMs", "Language Models"]
    }
  ],
  "notes": "..."
}
```

---

### 3) `macro_category_map.json`

Defines taxonomy edges: which categories live under which macro.

```json
{
  "macro_to_categories": {
    "macro_artificial_intelligence": [
      "cat_large_language_models",
      "cat_ai_safety_and_ethics"
    ],
    "macro_software_development": [
      "cat_ai_code_assistants"
    ]
  },
  "notes": "..."
}
```

Invariants:

* Each `category_id` should appear **exactly once** across all macros.
* A macro may be empty (`[]`). Apps may hide empty macros.

---

### 4) `records.jsonl`

Normalized metadata per article: one JSON object per line.

```json
{
  "id": "8f23a1b9c1a2d3e4",
  "title": "Why LLM Agents Fail at Planning",
  "file_name": "why_agents_fail.md",
  "date": null,
  "summary": "…",
  "key_points": ["…", "…", "…"]
}
```

Fields:

* `id`: article identifier
* `title`: cleaned display title
* `file_name`: file name of the original markdown article
* `date`: optional (may be null)
* `summary`: English summary
* `key_points`: 3–8 concise bullets

---

### 5) `assignments.jsonl`

Primary output for navigation/filtering: one JSON object per article per line.

```json
{
  "id": "8f23a1b9c1a2d3e4",
  "primary": {
    "macro_id": "macro_artificial_intelligence",
    "category_id": "cat_large_language_models"
  },
  "secondary": [
    {"macro_id": "macro_software_development", "category_id": "cat_ai_code_assistants"}
  ],
  "tags": ["llm", "agents", "planning", "evaluation"],
  "confidence": 0.78,
  "why": "The article focuses on …"
}
```

Fields:

* `id`: join key with `records.jsonl`
* `primary`: required (macro/category)
* `secondary`: optional (up to 2)
* `tags`: 4–14 lowercase tags
* `confidence`: 0..1
* `why`: explanation (useful for debugging and QA)

---

### 6) `assignments_skipped.jsonl` (if present)

If the pipeline rejects an assignment (schema mismatch, invalid macro/category pairing, etc.), it may record a skipped entry here.
Most apps should ignore this file, but it is useful for QA and improving mapping prompts.

---

### 7) `report.md`

Human-readable summary counts by macro and category. Useful for auditing; apps typically do not need it.

---

## Recommended loading & indexing (for apps)

Most downstream apps build an in-memory index:

1. Load `canonical_macros.json` → `macro_by_id`
2. Load `canonical_categories.json` → `category_by_id`
3. Load `macro_category_map.json` → `categories_by_macro`
4. Load `records.jsonl` → `record_by_article_id`
5. Load `assignments.jsonl` → `assignment_by_article_id`

Then compute derived views:

* counts per macro/category/tag,
* lists of article IDs per category,
* search indexes over `title`, `summary`, `key_points`, `tags`.

---

## How to load the full article content (file_name resolution)

Given:

* `input_dir`: the directory of `.md` articles,
* an `article_id`,
* a `RecordOut` entry containing `file_name`,

the app loads the actual markdown like this:

```python
from pathlib import Path

ARTICLE_DIR = Path(input_dir)

record = record_by_article_id[article_id]
path = ARTICLE_DIR / record["file_name"]
markdown_text = path.read_text(encoding="utf-8", errors="ignore")
```

Important:

* Ensure article file names are unique within `input_dir` to avoid collisions.
* If you later introduce subfolders with duplicate names, you’ll want to switch to a `path`-based approach. For this project, `file_name` is intentionally chosen as the simplest contract.

---

## Invariants and validation checks (recommended)

A healthy run typically satisfies:

* Every `assignments.jsonl` `id` exists in `records.jsonl`.
* Every `macro_id` exists in `canonical_macros.json`.
* Every `category_id` exists in `canonical_categories.json`.
* `primary.category_id` is listed under `primary.macro_id` in `macro_category_map.json`.

If an app detects violations, treat them as “needs review” and optionally:

* show the article under macro only,
* or display a warning for manual inspection.

---
