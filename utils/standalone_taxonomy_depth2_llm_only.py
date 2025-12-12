#!/usr/bin/env python3
"""
taxonomy_depth2_llm_only.py

LLM-only taxonomy builder with depth=2 (Macro -> Category) + tags.
Designed for ~1000 articles; each article is capped at 15k characters for processing.

Pipeline:
  0) Load articles from input_dir (.md).
  1) Build normalized record per article (one-pass summary on first 15k chars).
  2) Open (free) classification per article: macro_candidate + category_candidate + tags.
  3) Canonicalize categories (merge synonyms; define; id; aliases).
  4) Canonicalize macros similarly.
  5) Assign each canonical category to exactly one macro (balanced).
  6) Final closed classification per article into existing taxonomy.

Outputs in out_dir:
  - records.jsonl
  - raw_votes.jsonl
  - canonical_categories.json
  - canonical_macros.json
  - macro_category_map.json
  - assignments.jsonl
  - report.md

Notes:
  - Uses OpenAI Responses API via openai Python SDK.
  - Enforces JSON output with JSON Schema ("structured outputs").
  - Retries & caches results (append-only JSONL).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError
from tqdm import tqdm

from openai import OpenAI


# ---------------------------
# Models / validation
# ---------------------------

class RecordOut(BaseModel):
    id: str
    title: str
    file_name: Optional[str] = None
    date: Optional[str] = None
    summary: str
    key_points: List[str] = Field(min_length=3, max_length=8)


class VoteOut(BaseModel):
    id: str
    macro_candidate: Dict[str, str]     # {"label","definition"}
    category_candidate: Dict[str, str]  # {"label","definition"}
    tags: List[str] = Field(min_length=4, max_length=14)
    confidence: float = Field(ge=0.0, le=1.0)


class CanonicalItem(BaseModel):
    id: str
    label: str
    definition: str
    aliases: List[str] = Field(default_factory=list)


class CanonicalizeOut(BaseModel):
    canonical: List[CanonicalItem]
    alias_map: Dict[str, str] = Field(default_factory=dict)  # input_label -> canonical_id
    notes: Optional[str] = None


class MacroCategoryEntry(BaseModel):
    macro_id: str
    category_ids: List[str]


class MacroCategoryMapOut(BaseModel):
    macro_to_categories: List[MacroCategoryEntry]
    notes: Optional[str] = None


class AssignmentOut(BaseModel):
    id: str
    primary: Dict[str, str]  # {"macro_id","category_id"}
    secondary: List[Dict[str, str]] = Field(default_factory=list)  # up to 2
    tags: List[str] = Field(min_length=4, max_length=14)
    confidence: float = Field(ge=0.0, le=1.0)
    why: str


# ---------------------------
# JSON Schemas (Structured Outputs)
# ---------------------------

def schema_record() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "key_points": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 8},
        },
        "required": ["id", "title", "summary", "key_points"],
    }


def schema_vote() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "macro_candidate": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"label": {"type": "string"}, "definition": {"type": "string"}},
                "required": ["label", "definition"],
            },
            "category_candidate": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"label": {"type": "string"}, "definition": {"type": "string"}},
                "required": ["label", "definition"],
            },
            "tags": {"type": "array", "items": {"type": "string"}, "minItems": 4, "maxItems": 14},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": ["id", "macro_candidate", "category_candidate", "tags", "confidence"],
    }


def schema_canonicalize() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "canonical": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "id": {"type": "string"},
                        "label": {"type": "string"},
                        "definition": {"type": "string"},
                        "aliases": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
                    },
                    "required": ["id", "label", "definition", "aliases"],
                },
            },
            "notes": {"type": ["string", "null"]},
        },
        "required": ["canonical", "notes"],
    }


def schema_macro_category_map() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "macro_to_categories": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "macro_id": {"type": "string"},
                        "category_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["macro_id", "category_ids"],
                },
            },
            "notes": {"type": ["string", "null"]},
        },
        "required": ["macro_to_categories", "notes"],
    }


def schema_assignment() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "primary": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"macro_id": {"type": "string"}, "category_id": {"type": "string"}},
                "required": ["macro_id", "category_id"],
            },
            "secondary": {
                "type": "array",
                "maxItems": 2,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"macro_id": {"type": "string"}, "category_id": {"type": "string"}},
                    "required": ["macro_id", "category_id"],
                },
            },
            "tags": {"type": "array", "items": {"type": "string"}, "minItems": 4, "maxItems": 14},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "why": {"type": "string"},
        },
        "required": ["id", "primary", "secondary", "tags", "confidence", "why"],
    }


# ---------------------------
# Helpers
# ---------------------------

def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def jsonl_append(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def jsonl_load_by_id(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                _id = obj.get("id")
                if _id:
                    out[_id] = obj
            except json.JSONDecodeError:
                continue
    return out


def dump_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_article_files(input_dir: Path) -> List[Path]:
    exts = {".md"}
    files = [p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in exts]
    files.sort()
    return files


def read_text_file(path: Path, max_chars: int = 15_000) -> str:
    return path.read_text(errors="ignore")[:max_chars]


def extract_title_from_text(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:160]
    return fallback[:160]


def strip_frontmatter_md(text: str) -> str:
    lines = text.splitlines()
    if len(lines) >= 3 and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i+1:])
    return text


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def slugify_id(s: str) -> str:
    """Lowercase slug with underscores; alnum only."""
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "item"


def normalize_canonical_ids(items: List["CanonicalItem"], prefix: str) -> List["CanonicalItem"]:
    """Force ids to be prefix + slug(label); resolve collisions with suffix _2, _3..."""
    used: set[str] = set()
    out: List[CanonicalItem] = []
    for it in items:
        base = f"{prefix}{slugify_id(it.label)}"
        new_id = base
        k = 2
        while new_id in used:
            new_id = f"{base}_{k}"
            k += 1
        used.add(new_id)
        if it.id != new_id:
            it = CanonicalItem(id=new_id, label=it.label, definition=it.definition, aliases=it.aliases)
        out.append(it)
    return out


# ---------------------------
# OpenAI wrapper
# ---------------------------

@dataclass
class LLMConfig:
    model: str
    reasoning_effort: str = "minimal"
    verbosity: str = "low"
    max_output_tokens: int = 900
    max_retries: int = 6
    base_sleep: float = 1.2


class LLMClient:
    def __init__(self, cfg: LLMConfig, debug: bool = False):
        self.cfg = cfg
        self.debug = debug
        self.client = OpenAI()

    def _extract_text(self, response: Any) -> str:
        if hasattr(response, "output_text") and response.output_text:
            return response.output_text
        try:
            for it in (response.output or []):
                if getattr(it, "type", None) == "message":
                    for c in (getattr(it, "content", None) or []):
                        t = getattr(c, "text", None)
                        if t:
                            return t
        except Exception:
            pass
        return ""

    def call_json(self, *, name: str, schema: Dict[str, Any], messages: List[Dict[str, str]]) -> Dict[str, Any]:
        last_err: Optional[Exception] = None
        last_text: Optional[str] = None
        for attempt in range(self.cfg.max_retries):
            try:
                resp = self.client.responses.create(
                    model=self.cfg.model,
                    input=messages,
                    reasoning={"effort": self.cfg.reasoning_effort},
                    text={
                        "verbosity": self.cfg.verbosity,
                        "format": {"type": "json_schema", "name": name, "schema": schema, "strict": True},
                    },
                    max_output_tokens=self.cfg.max_output_tokens,
                )
                txt = self._extract_text(resp).strip()
                last_text = txt
                return json.loads(txt)
            except Exception as e:
                last_err = e
                if self.debug:
                    snippet = (last_text or "")[:800]
                    print(f"[LLM DEBUG] name={name} attempt={attempt+1}/{self.cfg.max_retries} error={e} text_snippet={snippet!r}", file=sys.stderr)
                sleep = self.cfg.base_sleep * (2 ** attempt) + random.random() * 0.25
                time.sleep(sleep)
        raise RuntimeError(f"LLM call failed after retries. last_error={last_err!r} last_text={last_text!r}")


# ---------------------------
# Prompts
# ---------------------------

DEV_STYLE = (
    "You are a careful taxonomy builder. "
    "Follow the JSON schema strictly. "
    "Always respond in English (translate content if needed). "
    "Use concise, consistent labels in English. "
    "Never output markdown fences."
)

def prompt_record_onepass(article_id: str, title_hint: str, text: str, file_name: str) -> List[Dict[str, str]]:
    dev = {"role": "developer", "content": DEV_STYLE}
    user = {"role": "user", "content": (
        "Create a normalized record for this article.\n\n"
        "Constraints:\n"
        "- summary: ~120–180 words in English, faithful, no opinions\n"
        "- key_points: 4–7 bullets in English, each <= 18 words\n"
        "- title: clean title in English (<= 120 chars) based on title_hint and article\n\n"
        f"Metadata:\n- id: {article_id}\n- title_hint: {title_hint}\n- file_name: {file_name}\n\n"
        f"ARTICLE TEXT:\n{text}"
    )}
    return [dev, user]


def prompt_vote(record: RecordOut) -> List[Dict[str, str]]:
    dev = {"role": "developer", "content": DEV_STYLE}
    user = {"role": "user", "content": (
        "Propose ONE macro and ONE category (depth=2 taxonomy) for this article, plus tags.\n\n"
        "Rules:\n"
        "- Macro label: 2–5 words, Title Case, broad but meaningful\n"
        "- Category label: 2–5 words, Title Case, specific but not ultra-narrow\n"
        "- Provide one-line definitions for both macro and category\n"
        "- No 'Misc', 'General', 'Other'\n"
        "- Output every field (labels, definitions, tags) in English only\n"
        "- tags: 5–12 short tags (lowercase), include key entities/terms\n\n"
        f"RECORD JSON:\n{json.dumps(record.model_dump(), ensure_ascii=False)}"
    )}
    return [dev, user]


def prompt_canonicalize(kind: str, items: List[Dict[str, Any]], id_prefix: str) -> List[Dict[str, str]]:
    dev = {"role": "developer", "content": DEV_STYLE}
    user = {"role": "user", "content": (
        f"Canonicalize (deduplicate) these {kind} candidates.\n\n"
        "Task:\n"
        "- Merge synonyms and trivial variants\n"
        "- Keep labels short and consistent (Title Case)\n"
        "- Produce fewer, stable canonicals\n"
        "- Return as FEW canonical items as possible (aggressively merge synonyms)\n"
        "- definition: <= 16 words\n"
        "- aliases: at most 3 items; each alias <= 6 words\n"
        "- Each canonical item must have: id, label, one-line definition, aliases[]\n"
        "- Output all labels/definitions/aliases in English only\n"
        f"ID rules:\n- Use ids with prefix '{id_prefix}', snake_case, e.g. '{id_prefix}ai_regulation'\n\n"
        f"INPUT ITEMS JSON:\n{json.dumps(items, ensure_ascii=False)}"
    )}
    return [dev, user]


def prompt_macro_category_map(macros: List[CanonicalItem], categories: List[CanonicalItem]) -> List[Dict[str, str]]:
    dev = {"role": "developer", "content": DEV_STYLE}
    user = {"role": "user", "content": (
        "Assign each category to exactly ONE macro (depth=2 taxonomy).\n\n"
        "Constraints:\n"
        "- Balance categories across macros; aim 3–12 categories per macro\n"
        "- Every category_id must appear exactly once\n"
        "- Output macro_to_categories as an ARRAY of objects: [{\"macro_id\":..., \"category_ids\": [...]}] ONLY (do NOT output a dict)\n"
        "- Macro definition must subsume its categories; if not, pick a better macro\n"
        "- You may refine macro labels/definitions, but macro_id values MUST remain exactly the same.\n"
        "- Do NOT invent, modify, or delete any macro_id or category_id.\n"
        "- Keep all labels/definitions/ids in English only\n\n"
        f"VALID MACRO IDS:\n{json.dumps([m.id for m in macros], ensure_ascii=False)}\n\n"
        f"VALID CATEGORY IDS:\n{json.dumps([c.id for c in categories], ensure_ascii=False)}\n\n"
        f"MACROS JSON:\n{json.dumps([m.model_dump() for m in macros], ensure_ascii=False)}\n\n"
        f"CATEGORIES JSON:\n{json.dumps([c.model_dump() for c in categories], ensure_ascii=False)}"
    )}
    return [dev, user]


def prompt_assignment(record: RecordOut, macros: List[CanonicalItem], categories: List[CanonicalItem], macro_to_categories: Dict[str, List[str]]) -> List[Dict[str, str]]:
    dev = {"role": "developer", "content": DEV_STYLE}
    cats_by_id = {c.id: c.model_dump() for c in categories}
    macro_ids = list(macro_to_categories.keys())
    user = {"role": "user", "content": (
        "Classify this article into the EXISTING taxonomy (depth=2).\n\n"
        "Rules:\n"
        "- Choose exactly one primary macro_id and one category_id under that macro\n"
        "- You may add up to 2 secondary pairs if truly multi-topic\n"
        "- tags: 5–12 short lowercase tags in English\n"
        "- why: max 35 words (1–2 sentences), concise rationale\n"
        "- Use definitions; choose best fit\n\n"
        "- macro_id MUST be one of these IDs only:\n"
        f"{json.dumps(macro_ids, ensure_ascii=False)}\n"
        "- category_id MUST be one of these IDs only:\n"
        f"{json.dumps(list(cats_by_id.keys()), ensure_ascii=False)}\n"
        "- Never invent new ids; if unsure, pick the closest valid id.\n\n"
        f"TAXONOMY MACROS:\n{json.dumps([m.model_dump() for m in macros], ensure_ascii=False)}\n\n"
        f"MACRO->CATEGORIES:\n{json.dumps(macro_to_categories, ensure_ascii=False)}\n\n"
        f"CATEGORIES BY ID:\n{json.dumps(cats_by_id, ensure_ascii=False)}\n\n"
        f"ARTICLE RECORD:\n{json.dumps(record.model_dump(), ensure_ascii=False)}"
    )}
    return [dev, user]


# ---------------------------
# Core processing
# ---------------------------

def build_article_object(path: Path) -> Tuple[str, str, str, str]:
    rel = str(path)
    article_id = sha1(rel)[:16]
    raw = read_text_file(path)
    raw = strip_frontmatter_md(raw)
    body = raw
    body = normalize_whitespace(body)
    title_hint = extract_title_from_text(body, fallback=path.stem)
    file_name = path.name
    return article_id, title_hint, body, file_name


def build_record_for_article(
    llm: LLMClient,
    article_id: str,
    title_hint: str,
    body: str,
    *,
    body_limit_chars: int,
    file_name: str,
) -> RecordOut:
    obj = llm.call_json(
        name="article_record",
        schema=schema_record(),
        messages=prompt_record_onepass(article_id, title_hint, body[:body_limit_chars], file_name),
    )
    rec = RecordOut.model_validate(obj)
    rec.file_name = file_name
    rec.date = rec.date or None
    return rec


def summarize_records(
    llm: LLMClient,
    files: List[Path],
    out_dir: Path,
    *,
    body_limit_chars: int,
) -> Dict[str, RecordOut]:
    records_path = out_dir / "records.jsonl"
    existing = jsonl_load_by_id(records_path)
    out: Dict[str, RecordOut] = {}

    for path in tqdm(files, desc="0/4 records"):
        article_id, title_hint, body, file_name = build_article_object(path)
        obj: Optional[Dict[str, Any]]
        if article_id in existing:
            obj = existing[article_id]
        else:
            rec = build_record_for_article(
                llm, article_id, title_hint, body,
                body_limit_chars=body_limit_chars,
                file_name=file_name,
            )
            obj = rec.model_dump()

        if not obj:
            continue
        try:
            rec = RecordOut.model_validate(obj)
            out[rec.id] = rec
            if rec.id not in existing:
                jsonl_append(records_path, rec.model_dump())
        except ValidationError:
            continue

    merged: Dict[str, RecordOut] = {}
    for _id, obj in {**existing, **{k: v.model_dump() for k, v in out.items()}}.items():
        try:
            merged[_id] = RecordOut.model_validate(obj)
        except ValidationError:
            pass
    return merged


def collect_votes(
    llm: LLMClient,
    records: Dict[str, RecordOut],
    out_dir: Path,
    *,
    votes_per_article: int,
) -> List[VoteOut]:
    votes_path = out_dir / "raw_votes.jsonl"
    debug_bad_path = out_dir / "raw_votes_invalid.jsonl"
    all_votes: List[VoteOut] = []

    for _id, rec in tqdm(records.items(), total=len(records), desc="1/4 open votes"):
        for _ in range(votes_per_article):
            try:
                obj = llm.call_json(
                    name="open_vote", schema=schema_vote(), messages=prompt_vote(rec)
                )
                v = VoteOut.model_validate(obj)
                all_votes.append(v)
                jsonl_append(votes_path, v.model_dump())
            except ValidationError as e:
                jsonl_append(debug_bad_path, {"id": _id, "error": str(e), "raw": obj})
                continue
            except Exception as e:
                jsonl_append(debug_bad_path, {"id": _id, "error": f"call_failed: {e!r}"})
                continue

    return all_votes


def aggregate_candidates(votes: Iterable[VoteOut]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    # Aggregate by just label (definitions vary); we’ll pass top definitions as examples
    macro_bucket: Dict[str, Dict[str, Any]] = {}
    cat_bucket: Dict[str, Dict[str, Any]] = {}

    for v in votes:
        ml = v.macro_candidate["label"].strip()
        md = v.macro_candidate["definition"].strip()
        cl = v.category_candidate["label"].strip()
        cd = v.category_candidate["definition"].strip()

        m = macro_bucket.setdefault(ml, {"label": ml, "definitions": {}, "count": 0})
        m["count"] += 1
        m["definitions"][md] = m["definitions"].get(md, 0) + 1

        c = cat_bucket.setdefault(cl, {"label": cl, "definitions": {}, "count": 0})
        c["count"] += 1
        c["definitions"][cd] = c["definitions"].get(cd, 0) + 1

    def finalize(bucket: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        items = []
        for label, d in bucket.items():
            defs = sorted(d["definitions"].items(), key=lambda x: -x[1])
            top_def = defs[0][0] if defs else ""
            items.append({
                "label": label,
                "definition": top_def,
                "count": d["count"],
                "alt_definitions": [x[0] for x in defs[1:4]],
            })
        return sorted(items, key=lambda x: (-x["count"], x["label"]))

    return finalize(macro_bucket), finalize(cat_bucket)


def canonicalize_iterative(
    llm: LLMClient,
    kind: str,
    items: List[Dict[str, Any]],
    out_path: Path,
    *,
    id_prefix: str,
    batch_size: int,
    target_max: int,
    max_rounds: int = 4,
    debug_dir: Optional[Path] = None,
) -> CanonicalizeOut:
    if out_path.exists():
        try:
            return CanonicalizeOut.model_validate(load_json(out_path))
        except Exception:
            pass

    def dedup_canonicals(objs: List[CanonicalItem]) -> Tuple[List[CanonicalItem], int]:
        merged: Dict[str, Dict[str, Any]] = {}
        dup_count = 0
        for o in objs:
            if o.id not in merged:
                merged[o.id] = {"id": o.id, "label": o.label, "definition": o.definition, "aliases": list(o.aliases)}
            else:
                dup_count += 1
                # keep first definition/label; treat differing labels as aliases
                if merged[o.id]["label"] != o.label:
                    merged[o.id]["aliases"].append(o.label)
                merged[o.id]["aliases"].extend(o.aliases)
        deduped = []
        for v in merged.values():
            v["aliases"] = sorted(set(a for a in v["aliases"] if a))
            deduped.append(CanonicalItem(**v))
        return deduped, dup_count

    def chunks(xs: List[Dict[str, Any]], n: int) -> List[List[Dict[str, Any]]]:
        return [xs[i:i+n] for i in range(0, len(xs), n)]

    current = items
    round_num = 0
    last_size = None
    dup_total = 0

    while True:
        round_num += 1
        random.shuffle(current)
        batches = chunks(current, batch_size)

        partials: List[CanonicalItem] = []

        for bi, b in enumerate(tqdm(batches, desc=f"2/4 canonicalize {kind} (round {round_num})"), start=1):
            try:
                out = llm.call_json(
                    name=f"canonicalize_{kind}",
                    schema=schema_canonicalize(),
                    messages=prompt_canonicalize(kind, b, id_prefix),
                )
                parsed = CanonicalizeOut.model_validate(out)
                partials.extend(parsed.canonical)
            except Exception as e:
                if debug_dir:
                    dbg = debug_dir / f"debug_canonicalize_{kind}_round{round_num}_batch{bi}.txt"
                    dbg.parent.mkdir(parents=True, exist_ok=True)
                    dbg.write_text(f"error: {e}\n\nbatch:\n{json.dumps(b, ensure_ascii=False, indent=2)}", encoding="utf-8")
                raise

        partials, dup_round = dedup_canonicals(partials)
        dup_total += dup_round

        # Final global merge: when we're close enough, do one last call with ALL items at once
        # to let the model see cross-batch synonyms.
        if len(partials) <= max(batch_size * 2, target_max + 8) and len(partials) > target_max:
            b_all = [{"label": c.label, "definition": c.definition, "count": 1, "alt_definitions": c.aliases[:3]} for c in partials]
            out = llm.call_json(
                name=f"canonicalize_{kind}_final",
                schema=schema_canonicalize(),
                messages=prompt_canonicalize(kind, b_all, id_prefix),
            )
            parsed = CanonicalizeOut.model_validate(out)
            partials = parsed.canonical
            partials, dup_round2 = dedup_canonicals(partials)
            dup_total += dup_round2

        # stop conditions
        if len(partials) <= target_max:
            note = f"stopped at round {round_num}; dedup={dup_total}"
            final = CanonicalizeOut(canonical=partials, notes=note)
            dump_json(out_path, final.model_dump())
            return final

        if last_size is not None and len(partials) >= last_size:
            note = f"no shrink; forced stop at round {round_num}; dedup={dup_total}"
            final = CanonicalizeOut(canonical=partials, notes=note)
            dump_json(out_path, final.model_dump())
            return final

        if round_num >= max_rounds:
            note = f"max rounds reached; dedup={dup_total}"
            final = CanonicalizeOut(canonical=partials, notes=note)
            dump_json(out_path, final.model_dump())
            return final

        last_size = len(partials)
        current = [{"label": c.label, "definition": c.definition, "count": 1, "alt_definitions": c.aliases[:3]} for c in partials]


def build_macro_category_map(
    llm: LLMClient,
    macros: List[CanonicalItem],
    categories: List[CanonicalItem],
    out_path: Path,
) -> MacroCategoryMapOut:
    if out_path.exists():
        try:
            return MacroCategoryMapOut.model_validate(load_json(out_path))
        except Exception:
            pass

    out = llm.call_json(
        name="macro_category_map",
        schema=schema_macro_category_map(),
        messages=prompt_macro_category_map(macros, categories),
    )
    # Accept either list or dict and normalize to list for validation
    if isinstance(out, dict) and "macro_to_categories" in out:
        mtc = out["macro_to_categories"]
        if isinstance(mtc, dict):
            out["macro_to_categories"] = [{"macro_id": k, "category_ids": v} for k, v in mtc.items()]

    parsed = MacroCategoryMapOut.model_validate(out)
    dump_json(out_path, parsed.model_dump())
    return parsed


def sanitize_mapping(mapping: Dict[str, List[str]], macros: List[CanonicalItem], categories: List[CanonicalItem]) -> Dict[str, List[str]]:
    macro_ids = {m.id for m in macros}
    cat_ids = {c.id for c in categories}
    cleaned: Dict[str, List[str]] = {}
    for mid, cids in mapping.items():
        if mid not in macro_ids:
            continue
        seen = set()
        filtered = []
        for cid in cids:
            if cid in cat_ids and cid not in seen:
                filtered.append(cid)
                seen.add(cid)
        cleaned[mid] = filtered
    return cleaned


def validate_full_coverage(mapping: Dict[str, List[str]], categories: List[CanonicalItem]) -> None:
    cat_ids = {c.id for c in categories}
    assigned = [cid for cids in mapping.values() for cid in cids]
    missing = cat_ids - set(assigned)
    duplicates = {cid for cid in assigned if assigned.count(cid) > 1}
    if missing or duplicates:
        raise RuntimeError(f"Mapping coverage issue: missing={missing} duplicates={duplicates}")


def build_round_robin_mapping(macros: List[CanonicalItem], categories: List[CanonicalItem]) -> Dict[str, List[str]]:
    if not macros:
        return {}
    mapping: Dict[str, List[str]] = {m.id: [] for m in macros}
    for idx, cat in enumerate(categories):
        mid = macros[idx % len(macros)].id
        mapping[mid].append(cat.id)
    return mapping


def repair_mapping(mapping: Dict[str, List[str]], macros: List[CanonicalItem], categories: List[CanonicalItem]) -> Dict[str, List[str]]:
    """
    Deduplicate categories (first occurrence wins) and assign missing categories
    to the macros with the smallest load (round-robin).
    """
    macro_ids = [m.id for m in macros]
    cat_ids = {c.id for c in categories}

    # Dedup and drop non-canonical cats
    seen = set()
    cleaned: Dict[str, List[str]] = {mid: [] for mid in macro_ids}
    for mid in macro_ids:
        for cid in mapping.get(mid, []):
            if cid in cat_ids and cid not in seen:
                cleaned[mid].append(cid)
                seen.add(cid)

    # Missing categories
    missing = list(cat_ids - seen)
    if missing:
        # sort macros by current load
        macro_ids_sorted = sorted(macro_ids, key=lambda m: len(cleaned.get(m, [])))
        mi = 0
        for cid in missing:
            mid = macro_ids_sorted[mi % len(macro_ids_sorted)]
            cleaned[mid].append(cid)
            mi += 1

    return cleaned


def mapping_list_to_dict(entries: List[Any]) -> Dict[str, List[str]]:
    """Normalize list of entries (Pydantic or dict) into dict[macro_id] = [category_ids]."""
    mapping: Dict[str, List[str]] = {}
    for entry in entries:
        mid = getattr(entry, "macro_id", None)
        cids = getattr(entry, "category_ids", None)
        if mid is None and isinstance(entry, dict):
            mid = entry.get("macro_id")
            cids = entry.get("category_ids")
        if isinstance(mid, str):
            if isinstance(cids, list):
                mapping[mid] = [x for x in cids if isinstance(x, str)]
            else:
                mapping[mid] = []
    return mapping


def final_assign(
    llm: LLMClient,
    records: Dict[str, RecordOut],
    macros: List[CanonicalItem],
    categories: List[CanonicalItem],
    macro_to_categories: Dict[str, List[str]],
    out_dir: Path,
) -> Dict[str, AssignmentOut]:
    out_path = out_dir / "assignments.jsonl"
    existing = jsonl_load_by_id(out_path)
    skipped_path = out_dir / "assignments_skipped.jsonl"

    macro_ids = {m.id for m in macros}
    cat_ids = {c.id for c in categories}
    cats_by_macro = {k: set(v) for k, v in macro_to_categories.items()}

    results: Dict[str, AssignmentOut] = {}
    for _id, rec in tqdm(records.items(), total=len(records), desc="3/4 final assigns"):
        if _id in existing:
            obj = existing[_id]
        else:
            try:
                obj = llm.call_json(
                    name="final_assignment",
                    schema=schema_assignment(),
                    messages=prompt_assignment(rec, macros, categories, macro_to_categories),
                )
            except Exception as e:
                jsonl_append(skipped_path, {"id": _id, "reason": "llm_call_failed", "error": repr(e)})
                continue

        if not obj:
            jsonl_append(skipped_path, {"id": _id, "reason": "empty_obj"})
            continue
        try:
            a = AssignmentOut.model_validate(obj)
        except ValidationError as e:
            jsonl_append(skipped_path, {"id": _id, "reason": "validation_error", "error": str(e)})
            continue

        pm, pc = a.primary["macro_id"], a.primary["category_id"]
        if pm not in macro_ids or pc not in cat_ids:
            jsonl_append(skipped_path, {"id": _id, "reason": "unknown_ids", "macro_id": pm, "category_id": pc})
            continue
        if pc not in cats_by_macro.get(pm, set()):
            jsonl_append(skipped_path, {"id": _id, "reason": "category_not_under_macro", "macro_id": pm, "category_id": pc})
            continue

        # secondary cleanup
        cleaned_sec = []
        for sec in a.secondary[:2]:
            sm, sc = sec["macro_id"], sec["category_id"]
            if sm in macro_ids and sc in cat_ids and sc in cats_by_macro.get(sm, set()):
                cleaned_sec.append(sec)
        a.secondary = cleaned_sec[:2]

        results[a.id] = a
        if a.id not in existing:
            jsonl_append(out_path, a.model_dump())

    merged: Dict[str, AssignmentOut] = {}
    for _id, obj in {**existing, **{k: v.model_dump() for k, v in results.items()}}.items():
        try:
            merged[_id] = AssignmentOut.model_validate(obj)
        except ValidationError:
            pass
    return merged


def build_report(
    out_dir: Path,
    macros: List[CanonicalItem],
    categories: List[CanonicalItem],
    mapping: Dict[str, List[str]],
    assigns: Dict[str, AssignmentOut],
) -> None:
    macro_by_id = {m.id: m for m in macros}
    cat_by_id = {c.id: c for c in categories}

    macro_counts: Dict[str, int] = {m.id: 0 for m in macros}
    cat_counts: Dict[str, int] = {c.id: 0 for c in categories}

    for a in assigns.values():
        macro_counts[a.primary["macro_id"]] = macro_counts.get(a.primary["macro_id"], 0) + 1
        cat_counts[a.primary["category_id"]] = cat_counts.get(a.primary["category_id"], 0) + 1

    lines: List[str] = []
    lines.append("# Taxonomy report\n")
    lines.append(f"- generated: {datetime.now().isoformat(timespec='seconds')}\n")
    lines.append(f"- articles assigned: {len(assigns)}\n")
    lines.append(f"- macros: {len(macros)}\n")
    lines.append(f"- categories: {len(categories)}\n\n")

    lines.append("## Macros (frequency)\n")
    for mid, cnt in sorted(macro_counts.items(), key=lambda x: -x[1]):
        m = macro_by_id[mid]
        lines.append(f"- **{m.label}** (`{mid}`): {cnt} — {m.definition}\n")

    lines.append("\n## Categories by Macro\n")
    for mid, cat_ids in mapping.items():
        m = macro_by_id.get(mid)
        if not m:
            continue
        lines.append(f"\n### {m.label} (`{mid}`)\n")
        for cid in sorted(cat_ids, key=lambda c: -cat_counts.get(c, 0)):
            c = cat_by_id.get(cid)
            if not c:
                lines.append(f"- MISSING CATEGORY (`{cid}`) — not found in canonical list\n")
                continue
            lines.append(f"- **{c.label}** (`{cid}`): {cat_counts.get(cid, 0)} — {c.definition}\n")

    (out_dir / "report.md").write_text("".join(lines), encoding="utf-8")


# ---------------------------
# Main
# ---------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input_dir", required=True, type=Path)
    ap.add_argument("--out_dir", required=True, type=Path)
    ap.add_argument("--model", default="gpt-5-nano")

    # records: max chars per article sent to LLM
    ap.add_argument("--body_limit_chars", type=int, default=15_000)

    # voting
    ap.add_argument("--votes_per_article", type=int, default=1, help="Set to 3 for self-consistency (more tokens).")

    # canonicalization targets
    ap.add_argument("--target_categories", type=int, default=20)
    ap.add_argument("--target_macros", type=int, default=8)

    # output tokens
    ap.add_argument("--max_output_tokens", type=int, default=2000)
    ap.add_argument("--debug", action="store_true", help="Print LLM errors while retrying.")
    ap.add_argument("--stop_after_votes", action="store_true", help="Stop after collecting votes (for debugging).")

    args = ap.parse_args()

    if not args.input_dir.exists():
        print(f"input_dir not found: {args.input_dir}", file=sys.stderr)
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)

    llm = LLMClient(LLMConfig(
        model=args.model,
        reasoning_effort="minimal",
        verbosity="low",
        max_output_tokens=args.max_output_tokens,
    ), debug=args.debug)

    files = iter_article_files(args.input_dir)
    if not files:
        print("No article files found (.md).", file=sys.stderr)
        return 2

    # 1) records (content capped at body_limit_chars)
    records = summarize_records(
        llm, files, args.out_dir,
        body_limit_chars=args.body_limit_chars,
    )

    # 2) open votes
    votes = collect_votes(
        llm, records, args.out_dir,
        votes_per_article=args.votes_per_article,
    )

    if args.stop_after_votes:
        print("stop_after_votes enabled; exiting after votes.")
        return 0

    macro_items, cat_items = aggregate_candidates(votes)

    # 3) canonicalize categories (pre-trim to reduce size)
    cat_items = cat_items[: args.target_categories * 2]
    canonical_categories = canonicalize_iterative(
        llm, "categories", cat_items, args.out_dir / "canonical_categories.json",
        id_prefix="cat_",
        batch_size=10,
        target_max=args.target_categories,
        debug_dir=args.out_dir if args.debug else None,
    )
    categories = normalize_canonical_ids(canonical_categories.canonical, "cat_")
    dump_json(args.out_dir / "canonical_categories.json", CanonicalizeOut(canonical=categories, notes=canonical_categories.notes).model_dump())

    # 4) canonicalize macros (pre-trim)
    macro_items = macro_items[: args.target_macros * 2]
    canonical_macros = canonicalize_iterative(
        llm, "macros", macro_items, args.out_dir / "canonical_macros.json",
        id_prefix="macro_",
        batch_size=8,
        target_max=args.target_macros,
        debug_dir=args.out_dir if args.debug else None,
    )
    macros = normalize_canonical_ids(canonical_macros.canonical, "macro_")
    dump_json(args.out_dir / "canonical_macros.json", CanonicalizeOut(canonical=macros, notes=canonical_macros.notes).model_dump())

    # 5) macro->categories mapping
    mapping_out = build_macro_category_map(
        llm, macros, categories, args.out_dir / "macro_category_map.json"
    )

    # 6) final assignment (closed) using LLM mapping + repair for full coverage
    mapping_dict = mapping_list_to_dict(mapping_out.macro_to_categories)
    if not mapping_dict:
        raise RuntimeError("macro_to_categories normalized to empty mapping; check LLM output format.")
    mapping_dict = sanitize_mapping(mapping_dict, macros, categories)
    mapping_dict = repair_mapping(mapping_dict, macros, categories)
    dump_json(
        args.out_dir / "macro_category_map.json",
        {"macro_to_categories": mapping_dict, "notes": "LLM mapping + repaired for full coverage"},
    )

    assigns = final_assign(
        llm, records, macros, categories, mapping_dict,
        args.out_dir
    )

    build_report(args.out_dir, macros, categories, mapping_dict, assigns)

    print("\nDone.")
    print(f"- out_dir: {args.out_dir}")
    print(f"- report:  {args.out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
