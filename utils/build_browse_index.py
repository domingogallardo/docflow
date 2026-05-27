"""Generate static browse pages under BASE_DIR/_site/browse.

The generated browse UI mirrors the intranet local reading workflow while
keeping pages static.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import shutil
import time
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from dataclasses import dataclass, replace
from pathlib import Path
import sys
from urllib.parse import quote

# Support direct execution: `python utils/build_browse_index.py ...`
if __package__ in (None, ""):
    _REPO_ROOT = Path(__file__).resolve().parents[1]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from utils.site_paths import (
    library_roots,
    normalize_rel_path,
    rel_path_from_abs,
    resolve_base_dir,
    resolve_library_path,
    site_root,
    viewer_url_for_rel_path,
)
from utils.highlight_store import highlight_status_for_path
from utils.markdown_utils import split_front_matter
from utils.reading_position_store import reading_positions_state_root
from utils.site_state import load_done_state, load_reading_state

CATEGORY_KEYS = ("posts", "tweets", "podcasts", "pdfs", "images")
CATEGORY_LABELS = {
    "posts": "Posts",
    "tweets": "Tweets",
    "pdfs": "Pdfs",
    "images": "Images",
    "podcasts": "Podcasts",
}

SKIP_DIR_NAMES = {"highlights", "__pycache__"}
YEAR_SUFFIX_RE = re.compile(r"(\d{4})$")
YEAR_COUNT_CATEGORIES = {"posts", "tweets", "pdfs", "images"}
YEAR_SORT_CATEGORIES = {"posts", "tweets", "pdfs", "images"}
TEMPORAL_GROUP_CATEGORIES = {"posts", "tweets", "podcasts"}
SEARCH_SUGGESTION_LIMIT = 400
CONTENT_FILTER_BUTTON_COUNT = 7
CONTENT_FILTER_POOL_LIMIT = 400
CONTENT_FILTER_MAX_DOC_FRACTION = 0.30
CONTENT_FILTER_MIN_DOC_COUNT = 3
CONTENT_FILTER_TARGET_MIN_FRACTION = 0.10
CONTENT_FILTER_TARGET_MAX_FRACTION = 0.30
CONTENT_FILTER_MIN_DOC_FRACTION = 0.01
CONTENT_FILTER_DIVERSITY_OVERLAP = 0.55
SEARCH_SUGGESTION_STOPWORDS = {
    "a",
    "al",
    "an",
    "and",
    "are",
    "as",
    "at",
    "after",
    "but",
    "by",
    "con",
    "de",
    "del",
    "el",
    "en",
    "for",
    "from",
    "how",
    "his",
    "have",
    "in",
    "into",
    "is",
    "it",
    "its",
    "la",
    "las",
    "le",
    "lo",
    "los",
    "of",
    "on",
    "or",
    "over",
    "para",
    "por",
    "que",
    "se",
    "según",
    "their",
    "them",
    "the",
    "they",
    "to",
    "un",
    "una",
    "via",
    "what",
    "why",
    "without",
    "with",
    "y",
}
CONTENT_FILTER_STOPWORDS = SEARCH_SUGGESTION_STOPWORDS | {
    "about",
    "also",
    "ante",
    "aqui",
    "across",
    "around",
    "article",
    "articulo",
    "asi",
    "between",
    "build",
    "can",
    "cada",
    "como",
    "common",
    "could",
    "cuando",
    "desde",
    "despite",
    "esta",
    "este",
    "estos",
    "esto",
    "here",
    "has",
    "just",
    "large",
    "like",
    "local",
    "more",
    "most",
    "must",
    "many",
    "muy",
    "new",
    "not",
    "other",
    "otra",
    "otro",
    "otros",
    "pero",
    "post",
    "posts",
    "rather",
    "recent",
    "shared",
    "sobre",
    "son",
    "sus",
    "that",
    "than",
    "three",
    "this",
    "through",
    "tras",
    "using",
    "where",
    "when",
    "while",
    "will",
}
SEARCH_SUGGESTION_GENERIC_WORDS = {
    "complete",
    "comprehensive",
    "deep",
    "dive",
    "episode",
    "explained",
    "exploring",
    "guide",
    "insights",
    "introduction",
    "journey",
    "notes",
    "overview",
    "part",
    "review",
    "ultimate",
    "understanding",
}
CONTENT_FILTER_GENERIC_WORDS = SEARCH_SUGGESTION_GENERIC_WORDS | {
    "ability",
    "analysis",
    "approach",
    "approaches",
    "argumenta",
    "arguing",
    "argues",
    "author",
    "case",
    "central",
    "clave",
    "concept",
    "covers",
    "debate",
    "dgfilterboundary",
    "document",
    "example",
    "forma",
    "future",
    "general",
    "generic",
    "highlights",
    "idea",
    "important",
    "context",
    "links",
    "manera",
    "major",
    "may",
    "mundo",
    "mas",
    "need",
    "note",
    "paper",
    "parte",
    "personas",
    "perspective",
    "piece",
    "possible",
    "process",
    "presents",
    "puede",
    "pueden",
    "relacion",
    "relationship",
    "role",
    "should",
    "show",
    "signal",
    "studies",
    "summary",
    "sistema",
    "systems",
    "tema",
    "texto",
    "time",
    "topic",
    "trabajo",
    "traces",
    "tweet",
    "tweets",
    "unique",
    "use",
    "way",
    "work",
    "world",
}
CONTENT_FILTER_GENERIC_SINGLE_WORDS = {
    "real",
}
SEARCH_SUGGESTION_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9][A-Za-zÀ-ÖØ-öø-ÿ0-9'’.-]*")
SPANISH_MONTH_NAMES = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre",
}


@dataclass(frozen=True)
class BrowseItem:
    rel_path: str
    name: str
    mtime: float
    reading: bool
    highlighted: bool
    highlight_last_epoch: float | None = None
    sort_mtime: float | None = None


@dataclass(frozen=True)
class BrowseEntry:
    name: str
    href: str
    mtime: float
    is_dir: bool
    icon: str
    rel_path: str | None = None
    highlighted: bool = False
    highlight_last_epoch: float | None = None
    sort_mtime: float | None = None
    temporal_epoch: float | None = None
    item_count: int | None = None
    filter_text: str = ""
    filter_terms: tuple[str, ...] = ()


def _safe_quote_component(value: str) -> str:
    return quote(value, safe="~!*()'")


def _is_hidden_name(name: str) -> bool:
    return name.startswith(".")


def _skip_directory(name: str) -> bool:
    return _is_hidden_name(name) or name in SKIP_DIR_NAMES


def _is_visible_file_name(name: str) -> bool:
    if _is_hidden_name(name):
        return False
    lower = name.lower()
    return lower.endswith((".html", ".htm", ".pdf"))


def _icon_for_filename(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".pdf"):
        return "📕 "
    if lower.endswith((".html", ".htm")):
        return "📄 "
    return ""


def _browse_controls_html(filter_pool: list[str]) -> str:
    buttons = [
        (
            "<button type='button' class='dg-sort-toggle' data-dg-sort-toggle aria-pressed='false'>"
            "Highlight: off"
            "</button>"
        )
    ]
    buttons.append(
        "<span class='dg-content-filter-slot' "
        f"data-dg-content-filter-pool='{html.escape(json.dumps(filter_pool, ensure_ascii=False, separators=(',', ':')), quote=True)}' "
        f"data-dg-content-filter-count='{CONTENT_FILTER_BUTTON_COUNT}'></span>"
    )
    buttons.append(
        "<button type='button' class='dg-content-filter-random' data-dg-content-filter-random "
        "aria-label='Random content filters' title='Random content filters'>🎲</button>"
    )
    buttons.append("<span class='dg-filter-summary' data-dg-filter-summary aria-live='polite'></span>")
    return "".join(buttons)


def _filter_text_part(value: str) -> str:
    return " ".join(str(value).split())


def _filter_text_for_path(path: Path) -> str:
    parts = [path.stem]
    md_path = path if path.suffix.lower() == ".md" else path.with_suffix(".md")
    if md_path.is_file():
        try:
            meta, _ = split_front_matter(md_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            meta = {}
        for key in (
            "title",
            "docflow_summary",
            "podcast_episode_title",
        ):
            value = meta.get(key, "")
            if value:
                parts.append(_filter_text_part(value))

    text = " ".join(part for part in parts if part)
    return _filter_text_part(text)


def _normalize_filter_term(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return normalized.lower()


def _content_filter_tokens(value: str) -> list[str]:
    return [
        match.group(0).strip(" .,:;!?()[]{}\"'’-/–—")
        for match in SEARCH_SUGGESTION_WORD_RE.finditer(value)
    ]


def _content_filter_token_value(token: str) -> str:
    return _normalize_filter_term(token.strip(" .,:;!?()[]{}\"'’-/–—"))


def _is_content_filter_term(term: str) -> bool:
    words = term.split()
    if not 1 <= len(words) <= 2:
        return False

    short_specific_words = {"ai", "ia", "ui", "ux"}
    excluded = CONTENT_FILTER_STOPWORDS | CONTENT_FILTER_GENERIC_WORDS
    for word in words:
        if not word or word.isdigit() or not re.search(r"[a-z]", word):
            return False
        if len(word) < 3 and word not in short_specific_words:
            return False

    if len(words) == 1:
        return words[0] not in excluded and words[0] not in CONTENT_FILTER_GENERIC_SINGLE_WORDS
    if words[0] in excluded or words[-1] in CONTENT_FILTER_STOPWORDS:
        return False
    return True


def _content_filter_candidate_phrases(text: str) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for segment in re.split(r"[.!?;:\n\r]+", text):
        words = [word for word in _content_filter_tokens(re.sub(r"[_|]+", " ", segment)) if word]
        if not words:
            continue
        for size in (2, 1):
            for index in range(0, len(words) - size + 1):
                phrase_words = words[index : index + size]
                normalized_words = [_content_filter_token_value(word) for word in phrase_words]
                if any(re.search(r"[a-z][A-Z]", word) for word in phrase_words):
                    continue
                normalized_phrase = " ".join(normalized_words)
                if not _is_content_filter_term(normalized_phrase):
                    continue
                if normalized_phrase in seen:
                    continue
                seen.add(normalized_phrase)
                candidates.append((" ".join(phrase_words), normalized_phrase))
    return candidates


def _content_filter_analyzer(text: str) -> list[str]:
    return [normalized for _, normalized in _content_filter_candidate_phrases(text)]


def _content_filter_tokenizer(text: str) -> list[str]:
    return [_content_filter_token_value(token) for token in _content_filter_tokens(text)]


def _content_filter_preprocessor(text: str) -> str:
    normalized = _normalize_filter_term(text)
    return re.sub(r"[.!?;:\n\r]+", " dgfilterboundary ", normalized)


def _content_filter_display_phrase(term: str) -> str:
    words = term.split()
    return " ".join(word.upper() if word in {"ai", "ia", "ui", "ux"} else word for word in words)


def _binary_entropy(probability: float) -> float:
    if probability <= 0 or probability >= 1:
        return 0.0
    return -(probability * math.log2(probability) + (1 - probability) * math.log2(1 - probability))


def _coverage_target_score(coverage: float) -> float:
    target_midpoint = (CONTENT_FILTER_TARGET_MIN_FRACTION + CONTENT_FILTER_TARGET_MAX_FRACTION) / 2
    target_half_width = (CONTENT_FILTER_TARGET_MAX_FRACTION - CONTENT_FILTER_TARGET_MIN_FRACTION) / 2
    if target_half_width <= 0:
        return 1.0
    distance = abs(coverage - target_midpoint)
    return max(0.0, 1.0 - distance / target_half_width)


def _coverage_signal(total_docs: int, coverage: float) -> float:
    entropy = _binary_entropy(coverage)
    if total_docs <= 5:
        return max(entropy, 0.25)
    return entropy


def _content_filter_term_tokens(term: str) -> set[str]:
    tokens: set[str] = set()
    for token in term.split():
        tokens.add(token)
        if len(token) > 4 and token.endswith("s"):
            tokens.add(token[:-1])
    return tokens


def _content_filter_term_similarity(left: str, right: str) -> float:
    left_words = set(left.split())
    right_words = set(right.split())
    if not left_words or not right_words:
        return 0.0
    if len(left_words) == 1 and len(right_words) == 1:
        left_tokens = _content_filter_term_tokens(left)
        right_tokens = _content_filter_term_tokens(right)
        return len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
    return len(left_words & right_words) / max(1, max(len(left_words), len(right_words)))


def _select_diverse_content_terms(ranked_terms: list[tuple[str, float]], limit: int) -> list[str]:
    selected: list[str] = []
    for term, _score in ranked_terms:
        if not term.split():
            continue
        is_too_similar = False
        for existing in selected:
            if _content_filter_term_similarity(term, existing) > CONTENT_FILTER_DIVERSITY_OVERLAP:
                is_too_similar = True
                break
        if is_too_similar:
            continue
        selected.append(term)
        if len(selected) >= limit:
            break
    return selected


def _content_filter_min_doc_count(total_docs: int) -> int:
    if total_docs <= 5:
        return 1
    return max(CONTENT_FILTER_MIN_DOC_COUNT, math.ceil(total_docs * CONTENT_FILTER_MIN_DOC_FRACTION))


def _content_filter_pool_sklearn(texts: list[str], limit: int) -> list[str] | None:
    try:
        from sklearn.feature_extraction.text import CountVectorizer
    except Exception:
        return None

    total_docs = len(texts)
    if total_docs == 0:
        return []

    min_df = _content_filter_min_doc_count(total_docs)
    max_df = max(min_df, int(total_docs * CONTENT_FILTER_MAX_DOC_FRACTION))
    try:
        vectorizer = CountVectorizer(
            preprocessor=_content_filter_preprocessor,
            tokenizer=_content_filter_tokenizer,
            token_pattern=None,
            ngram_range=(1, 2),
            lowercase=False,
            binary=False,
            min_df=min_df,
            max_df=max_df,
        )
        matrix = vectorizer.fit_transform(texts)
    except ValueError:
        return []

    try:
        terms = vectorizer.get_feature_names_out()
    except AttributeError:
        terms = vectorizer.get_feature_names()

    if len(terms) == 0:
        return []

    binary_matrix = matrix.copy()
    binary_matrix.data.fill(1)
    doc_counts = binary_matrix.sum(axis=0).A1
    term_counts = matrix.sum(axis=0).A1

    ranked_terms: list[tuple[str, float]] = []
    for index, term in enumerate(terms):
        term = str(term)
        if not _is_content_filter_term(term):
            continue
        doc_count = int(doc_counts[index])
        if doc_count < min_df or doc_count > max_df:
            continue
        coverage = doc_count / total_docs
        entropy = _coverage_signal(total_docs, coverage)
        target_bonus = 1.0 + _coverage_target_score(coverage)
        word_count = len(term.split())
        ngram_bonus = 1.0 if word_count >= 2 else 0.86
        frequency = 1.0 + math.log1p(float(term_counts[index]))
        score = entropy * target_bonus * ngram_bonus * frequency
        ranked_terms.append((term, score))

    ranked_terms.sort(key=lambda item: (-item[1], item[0]))
    return [_content_filter_display_phrase(term) for term in _select_diverse_content_terms(ranked_terms, limit)]


def _content_filter_pool_fallback(texts: list[str], limit: int) -> list[str]:
    total_docs = len(texts)
    if total_docs == 0:
        return []

    term_frequency: Counter[str] = Counter()
    document_frequency: Counter[str] = Counter()
    max_doc_count = max(2, int(total_docs * CONTENT_FILTER_MAX_DOC_FRACTION))
    min_doc_count = _content_filter_min_doc_count(total_docs)

    for text in texts:
        doc_terms = _content_filter_analyzer(text)
        doc_counter = Counter(doc_terms)
        term_frequency.update(doc_counter)
        document_frequency.update(doc_counter.keys())

    ranked_terms: list[tuple[str, float]] = []
    for term, doc_count in document_frequency.items():
        if doc_count < min_doc_count or doc_count > max_doc_count:
            continue
        coverage = doc_count / total_docs
        entropy = _coverage_signal(total_docs, coverage)
        target_bonus = 1.0 + _coverage_target_score(coverage)
        word_count = len(term.split())
        ngram_bonus = 1.0 if word_count >= 2 else 0.86
        frequency = 1.0 + math.log1p(term_frequency[term])
        score = entropy * target_bonus * ngram_bonus * frequency
        ranked_terms.append((term, score))

    ranked_terms.sort(key=lambda item: (-item[1], item[0]))
    return [_content_filter_display_phrase(term) for term in _select_diverse_content_terms(ranked_terms, limit)]


def _content_filter_pool(entries: list[BrowseEntry], limit: int = CONTENT_FILTER_POOL_LIMIT) -> list[str]:
    texts = [entry.filter_text for entry in entries if not entry.is_dir and entry.filter_text]
    if not texts:
        return []

    sklearn_pool = _content_filter_pool_sklearn(texts, limit)
    if sklearn_pool is not None:
        return sklearn_pool
    return _content_filter_pool_fallback(texts, limit)


def _content_filter_match_tokens(value: str) -> set[str]:
    normalized = _normalize_filter_term(value)
    return set(token for token in re.split(r"[^a-z0-9]+", normalized) if token)


def _content_filter_token_coverage_match(filter_tokens: list[str], document_tokens: set[str]) -> bool:
    if not filter_tokens:
        return False

    matches = sum(1 for token in filter_tokens if token in document_tokens)
    required = len(filter_tokens) if len(filter_tokens) <= 2 else math.ceil(len(filter_tokens) * 0.67)
    return matches >= required


def _content_filter_term_matches_text(term: str, normalized_text: str, document_tokens: set[str]) -> bool:
    normalized_term = _normalize_filter_term(term.strip())
    filter_tokens = [token for token in re.split(r"[^a-z0-9]+", normalized_term) if token]
    if not filter_tokens:
        return False
    if len(filter_tokens) == 1:
        return filter_tokens[0] in document_tokens
    if normalized_term in normalized_text:
        return True
    return _content_filter_token_coverage_match(filter_tokens, document_tokens)


def _content_filter_terms_for_text(text: str, filter_pool: list[str]) -> tuple[str, ...]:
    if not text or not filter_pool:
        return ()

    normalized_text = _normalize_filter_term(text)
    document_tokens = _content_filter_match_tokens(text)
    return tuple(
        term
        for term in filter_pool
        if _content_filter_term_matches_text(term, normalized_text, document_tokens)
    )


def _entries_with_content_filter_terms(entries: list[BrowseEntry], filter_pool: list[str]) -> list[BrowseEntry]:
    if not filter_pool:
        return entries

    return [
        replace(entry, filter_terms=_content_filter_terms_for_text(entry.filter_text, filter_pool))
        if not entry.is_dir
        else entry
        for entry in entries
    ]


def _highlight_status(base_dir: Path, rel_path: str) -> tuple[bool, float | None]:
    low_name = Path(rel_path).name.lower()
    if not low_name.endswith((".html", ".htm")):
        return False, None
    return highlight_status_for_path(base_dir, rel_path)


def _entry_classes(entry: BrowseEntry) -> str:
    classes: list[str] = []
    if entry.highlighted:
        classes.append("dg-hl")
    return f' class="{" ".join(classes)}"' if classes else ""


def _render_entry(entry: BrowseEntry) -> str:
    display_name = entry.name + ("/" if entry.is_dir else "")
    esc_name = html.escape(display_name)
    count_html = f" <span class='dg-count'>({entry.item_count})</span>" if entry.item_count is not None else ""

    prefix = (
        ("🟡 " if entry.highlighted else "")
        + entry.icon
    )
    cls_attr = _entry_classes(entry)
    attr_bits = [
        "data-dg-sortable='1'",
        f"data-dg-highlighted='{'1' if entry.highlighted else '0'}'",
        f"data-dg-highlight-last='{(entry.highlight_last_epoch or 0):.6f}'",
        f"data-dg-sort-mtime='{_sort_mtime(entry):.6f}'",
        f"data-dg-name='{html.escape(entry.name.lower(), quote=True)}'",
        "data-dg-filter-terms='"
        + html.escape(json.dumps(entry.filter_terms, ensure_ascii=False, separators=(",", ":")), quote=True)
        + "'",
    ]
    attrs = f"{cls_attr} " + " ".join(attr_bits) if cls_attr else " " + " ".join(attr_bits)
    return (
        f"<li{attrs}><span>{prefix}<a href=\"{entry.href}\">{esc_name}</a>{count_html}</span></li>"
    )


def _sort_mtime(entry: BrowseEntry) -> float:
    if entry.sort_mtime is not None:
        return entry.sort_mtime
    return entry.mtime


def _iso_to_epoch(value: object) -> float | None:
    if not isinstance(value, str):
        return None

    iso_value = value.strip()
    if not iso_value:
        return None

    if iso_value.endswith("Z"):
        iso_value = iso_value[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(iso_value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _entry_sort_key(entry: BrowseEntry) -> tuple[float, str]:
    return (-_sort_mtime(entry), entry.name.lower())


def _local_today() -> date:
    return datetime.now().astimezone().date()


def _base_head(title: str) -> str:
    return (
        f"<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>{html.escape(title)}</title>"
        "<style>"
        "body{margin:14px 18px;font:14px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;color:#222;background:#fff}"
        "h2{margin:6px 0 10px;font-weight:600}"
        "hr{border:0;border-top:1px solid #e6e6e6;margin:8px 0}"
        "ul.dg-index{list-style:none;padding-left:0}"
        ".dg-index li{padding:2px 6px;border-radius:6px;margin:2px 0;display:flex;justify-content:space-between;align-items:center;gap:10px}"
        ".dg-legendbar{display:flex;align-items:center;justify-content:flex-start;column-gap:6px;row-gap:5px;flex-wrap:wrap;margin-bottom:8px}"
        ".dg-content-filter-slot{display:inline-flex;align-items:center;column-gap:6px;row-gap:5px;flex-wrap:wrap}"
        ".dg-nav{color:#666;font:13px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;margin-bottom:8px}"
        ".dg-nav a{text-decoration:none;color:#0a7}"
        ".dg-actions{display:inline-flex;gap:6px}"
        ".dg-actions button, .dg-actions a, .dg-rebuild{padding:2px 6px;border:1px solid #ccc;border-radius:6px;background:#f7f7f7;text-decoration:none;color:#333;font:12px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;cursor:pointer}"
        ".dg-actions button[disabled], .dg-actions a[disabled], .dg-rebuild[disabled]{opacity:.6;pointer-events:none}"
        ".dg-count{color:#666;margin-left:8px;white-space:nowrap}"
        ".dg-search{display:inline-flex;align-items:center;gap:6px}"
        ".dg-search input[type='text']{padding:3px 8px;border:1px solid #ccc;border-radius:6px;min-width:420px;max-width:100%;font:13px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial}"
        ".dg-search button{padding:2px 8px;border:1px solid #ccc;border-radius:6px;background:#f7f7f7;color:#333;font:12px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;cursor:pointer}"
        ".dg-search-toggle{display:inline-flex;align-items:center;gap:4px;color:#555;font:13px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;white-space:nowrap}"
        ".dg-search-toggle input{margin:0}"
        ".dg-search-hit{margin:6px 0 2px;font:13px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;color:#444}"
        ".dg-search-hit a{color:#0a7;text-decoration:none}"
        ".dg-search-results{list-style:none;padding-left:0;margin:6px 0 0}"
        ".dg-search-results li{margin:3px 0}"
        ".dg-search-folder{color:#666;margin-left:6px}"
        ".dg-sort-toggle,.dg-content-filter,.dg-content-filter-random{padding:2px 8px;border:1px solid #ccc;border-radius:6px;background:#f7f7f7;color:#333;font:12px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;cursor:pointer}"
        ".dg-sort-toggle.is-active{border-color:#c8a400;background:#fff6e5}"
        ".dg-content-filter.is-active{border-color:#0a7;background:#eaf8f2}"
        ".dg-sort-toggle[disabled],.dg-content-filter[disabled],.dg-content-filter-random[disabled]{opacity:.55;cursor:default}"
        ".dg-filter-summary{color:#666;font:12px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial}"
        ".dg-time-heading[hidden],.dg-time-section[hidden],.dg-index li[hidden]{display:none!important}"
        ".dg-parent-index{list-style:none;padding-left:0;margin:0 0 8px}"
        ".dg-time-heading{font-size:13px;margin:14px 0 4px;color:#555;font-weight:600}"
        ".dg-time-section{margin-top:0;margin-bottom:8px}"
        "</style>"
        "<script src='/assets/actions.js' defer></script>"
        "<script src='/assets/browse-sort.js' defer></script>"
        "</head><body>"
    )


def _render_directory_page(
    *,
    title: str,
    display_path: str,
    entries: list[BrowseEntry],
    parent_href: str | None,
    controls_html: str | None = None,
    pre_list_html: str = "",
    entry_sections: list[tuple[str, list[BrowseEntry]]] | None = None,
) -> str:
    rows: list[str] = [_base_head(title)]
    rows.append("<div class='dg-nav'><a href='/'>Home</a> · <a href='/browse/'>Browse</a> · <a href='/reading/'>Reading</a> · <a href='/done/'>Done</a></div>")
    rows.append(f"<h2>Index of {html.escape(display_path)}</h2>")
    if controls_html is None:
        section_entries = (
            [entry for _, section in entry_sections for entry in section]
            if entry_sections is not None
            else entries
        )
        if any(not entry.is_dir for entry in section_entries):
            filter_pool = _content_filter_pool(section_entries)
            if entry_sections is not None:
                entry_sections = [
                    (label, _entries_with_content_filter_terms(section, filter_pool))
                    for label, section in entry_sections
                ]
            else:
                entries = _entries_with_content_filter_terms(entries, filter_pool)
            controls_html = _browse_controls_html(filter_pool)
        else:
            controls_html = ""
    if controls_html:
        rows.append(f"<div class='dg-legendbar'>{controls_html}</div>")
    if pre_list_html:
        rows.append(pre_list_html)

    if parent_href:
        rows.append(f'<hr><ul class="dg-parent-index"><li data-dg-parent="1"><a href="{parent_href}">../</a></li></ul>')
    else:
        rows.append("<hr>")

    if entry_sections is not None:
        for label, section_entries in entry_sections:
            if not section_entries:
                continue
            rows.append(f"<h3 class='dg-time-heading'>{html.escape(label)}</h3>")
            rows.append("<ul class='dg-index dg-time-section'>")
            for entry in section_entries:
                rows.append(_render_entry(entry))
            rows.append("</ul>")
        rows.append("<hr></body></html>")
        return "\n".join(rows)

    rows.append("<ul class='dg-index'>")

    for entry in entries:
        rows.append(_render_entry(entry))

    rows.append("</ul><hr></body></html>")
    return "\n".join(rows)


def _collect_browse_search_entries(base_dir: Path, category_roots: dict[str, Path]) -> list[dict[str, str]]:
    scanned: list[tuple[float, dict[str, str]]] = []
    for category in CATEGORY_KEYS:
        root = category_roots[category]
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel_to_root = path.relative_to(root)
            if any(_skip_directory(part) for part in rel_to_root.parts[:-1]):
                continue
            if category == "tweets" and path.suffix.lower() == ".md":
                tweet_entry = _tweet_markdown_search_entry(path)
                if tweet_entry is None:
                    continue
                try:
                    mtime = path.stat().st_mtime
                except Exception:
                    continue
                scanned.append((_search_entry_sort_epoch(path, mtime), tweet_entry))
                continue
            if not _is_visible_file_name(path.name):
                continue
            if category == "tweets" and _has_tweet_consolidated_url(path.with_suffix(".md")):
                continue
            try:
                rel = rel_path_from_abs(base_dir, path)
                href = viewer_url_for_rel_path(rel)
                mtime = path.stat().st_mtime
            except Exception:
                continue
            scanned.append(
                (
                    _search_entry_sort_epoch(path, mtime),
                    {
                        "stem": path.stem,
                        "name": path.name,
                        "href": href,
                        "folder": path.parent.name,
                        "category": category,
                    },
                )
            )
    scanned.sort(key=lambda item: item[0], reverse=True)
    return [entry for _, entry in scanned]


def _search_entry_sort_epoch(path: Path, fallback_epoch: float) -> float:
    """Prefer docflow ingest time from the sibling Markdown sidecar."""
    ingested_epoch = _markdown_docflow_ingested_epoch(path if path.suffix.lower() == ".md" else path.with_suffix(".md"))
    return ingested_epoch if ingested_epoch is not None else fallback_epoch


def _markdown_docflow_ingested_epoch(path: Path) -> float | None:
    meta = _read_markdown_front_matter(path)
    if meta is None:
        return None
    return _iso_to_epoch(meta.get("docflow_ingested_at"))


def _post_effective_date_epoch(path: Path) -> float | None:
    md_path = path if path.suffix.lower() == ".md" else path.with_suffix(".md")
    meta = _read_markdown_front_matter(md_path)
    if meta is None:
        return None
    for key in ("docflow_ingested_at", "docflow_original_published_at"):
        epoch = _iso_to_epoch(meta.get(key))
        if epoch is not None:
            return epoch
    return None


def _read_markdown_front_matter(path: Path) -> dict[str, str] | None:
    if path.suffix.lower() != ".md" or not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    meta, _ = split_front_matter(text)
    return meta


def _read_tweet_markdown_meta(path: Path) -> tuple[dict[str, str], str] | None:
    if path.suffix.lower() != ".md" or not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    meta, _ = split_front_matter(text)
    if meta.get("source", "").strip().lower() != "tweet":
        return None
    return meta, text


def _has_tweet_consolidated_url(path: Path) -> bool:
    parsed = _read_tweet_markdown_meta(path)
    if parsed is None:
        return False
    meta, _ = parsed
    return bool(meta.get("tweet_consolidated_url", "").strip())


def _tweet_markdown_search_entry(path: Path) -> dict[str, str] | None:
    parsed = _read_tweet_markdown_meta(path)
    if parsed is None:
        return None
    meta, _ = parsed
    href = meta.get("tweet_consolidated_url", "").strip()
    if not href:
        return None
    title = path.stem.strip()
    return {
        "stem": title,
        "name": title,
        "href": href,
        "folder": f"{path.parent.name} / Tweet",
        "category": "tweets",
    }


def _search_suggestion_token_value(token: str) -> str:
    return token.strip(" .,:;!?()[]{}\"'’-/–—").lower()


def _search_suggestion_candidates(stem: str) -> list[str]:
    text = re.sub(r"[_|]+", " ", stem)
    words = [match.group(0).strip(" .,:;!?()[]{}\"'’-/–—") for match in SEARCH_SUGGESTION_WORD_RE.finditer(text)]
    words = [word for word in words if word]
    if not words:
        return []

    candidates: list[str] = []
    seen: set[str] = set()
    for size in (3, 2):
        for index in range(0, len(words) - size + 1):
            phrase_words = words[index : index + size]
            normalized_words = [_search_suggestion_token_value(word) for word in phrase_words]
            if any(not word or word.isdigit() for word in normalized_words):
                continue
            if normalized_words[0] in SEARCH_SUGGESTION_STOPWORDS or normalized_words[-1] in SEARCH_SUGGESTION_STOPWORDS:
                continue
            if normalized_words[0] in SEARCH_SUGGESTION_GENERIC_WORDS or normalized_words[-1] in SEARCH_SUGGESTION_GENERIC_WORDS:
                continue
            phrase = " ".join(phrase_words)
            normalized_phrase = " ".join(normalized_words)
            if len(normalized_phrase) < 4 or normalized_phrase in seen:
                continue
            seen.add(normalized_phrase)
            candidates.append(phrase)
    return candidates


def _collect_browse_search_suggestions(search_entries: list[dict[str, str]], limit: int = SEARCH_SUGGESTION_LIMIT) -> list[str]:
    ranked: dict[str, dict[str, object]] = {}
    for recency_rank, entry in enumerate(search_entries):
        if entry.get("category") != "posts":
            continue
        stem = entry.get("stem", "")
        for candidate in _search_suggestion_candidates(stem):
            normalized = candidate.lower()
            existing = ranked.get(normalized)
            if existing is None:
                ranked[normalized] = {
                    "phrase": candidate,
                    "count": 1,
                    "first_rank": recency_rank,
                    "word_count": len(candidate.split()),
                }
                continue
            existing["count"] = int(existing["count"]) + 1

    ordered = sorted(
        ranked.values(),
        key=lambda item: (-int(item["count"]), -int(item["word_count"]), int(item["first_rank"]), str(item["phrase"]).lower()),
    )
    return [str(item["phrase"]) for item in ordered[:limit]]


def _search_controls_html() -> str:
    return (
        "<form class='dg-search' data-dg-search-form autocomplete='off'>"
        "<input type='text' data-dg-search-input "
        "placeholder='Search title text or term + term' "
        "aria-label='Search title text or term plus term'>"
        "<label class='dg-search-toggle'><input type='checkbox' data-dg-search-tweets checked>Tweets</label>"
        "<button type='submit' data-dg-search-button aria-label='Search'>🔍</button>"
        "<button type='button' data-dg-search-random aria-label='Random search suggestion' title='Random search suggestion'>🎲</button>"
        "</form>"
    )


def _search_result_html() -> str:
    return "<div class='dg-search-hit' data-dg-search-hit></div>"


def _home_history_link_html() -> str:
    return "<p><a href='#' data-dg-history-link>History</a></p>"


def _read_json_object(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _history_entry_from_position(base_dir: Path, payload: dict[str, object]) -> tuple[float, dict[str, object]] | None:
    raw_path = payload.get("path")
    updated_at = str(payload.get("updated_at") or "").strip()
    updated_epoch = _iso_to_epoch(updated_at)
    if not isinstance(raw_path, str) or updated_epoch is None:
        return None

    try:
        rel_path = normalize_rel_path(raw_path)
        abs_path = resolve_library_path(base_dir, rel_path)
    except Exception:
        return None
    if not abs_path.is_file() or not _is_visible_file_name(abs_path.name):
        return None

    return (
        updated_epoch,
        {
            "name": abs_path.name,
            "href": viewer_url_for_rel_path(rel_path),
            "folder": abs_path.parent.name,
            "path": rel_path,
            "updated_at": updated_at,
            "progress": payload.get("progress"),
            "page": payload.get("page"),
        },
    )


def collect_site_history_entries(base_dir: Path) -> list[dict[str, object]]:
    history_root = reading_positions_state_root(base_dir)
    if not history_root.is_dir():
        return []

    scanned: list[tuple[float, dict[str, object]]] = []
    for state_path in history_root.rglob("*.json"):
        payload = _read_json_object(state_path)
        if payload is None:
            continue
        history_entry = _history_entry_from_position(base_dir, payload)
        if history_entry is not None:
            scanned.append(history_entry)

    scanned.sort(key=lambda item: (item[0], str(item[1].get("path") or "")), reverse=True)
    return [entry for _, entry in scanned]


def _history_index_payload(base_dir: Path) -> dict[str, object]:
    return {
        "version": 1,
        "entries": collect_site_history_entries(base_dir),
    }


def write_site_history_index(base_dir: Path) -> Path:
    output = site_root(base_dir) / "history-index.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(_history_index_payload(base_dir), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return output


def _search_index_payload(search_entries: list[dict[str, str]]) -> dict[str, object]:
    return {
        "version": 1,
        "entries": search_entries,
        "suggestions": _collect_browse_search_suggestions(search_entries),
    }


def _write_site_search_index(base_dir: Path, search_entries: list[dict[str, str]]) -> None:
    output = site_root(base_dir) / "search-index.json"
    output.write_text(
        json.dumps(_search_index_payload(search_entries), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _search_script_html() -> str:
    return (
        "<script>"
        + "(function(){"
        + "function norm(v){return String(v||'').trim().replace(/\\.(html?|pdf)$/i,'');}"
        + "function queryTerms(v){return norm(v).split(/\\s+\\+\\s+/).map(norm).filter(Boolean);}"
        + "function escRe(v){return String(v||'').replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&');}"
        + "function wholeTermMatch(title,term){return new RegExp('(^|[^\\\\p{L}\\\\p{N}])'+escRe(term)+'(?=$|[^\\\\p{L}\\\\p{N}])','iu').test(title);}"
        + "const form=document.querySelector('[data-dg-search-form]');"
        + "const input=document.querySelector('[data-dg-search-input]');"
        + "const tweetsToggle=document.querySelector('[data-dg-search-tweets]');"
        + "const randomButton=document.querySelector('[data-dg-search-random]');"
        + "const historyLink=document.querySelector('[data-dg-history-link]');"
        + "const hit=document.querySelector('[data-dg-search-hit]');"
        + "if(!form||!input||!hit)return;"
        + "const searchStateKey='docflow.home.search';"
        + "const tweetsStateKey='docflow.home.search.tweets';"
        + "let entries=[];"
        + "let suggestions=[];"
        + "let searchIndexReady=false;"
        + "let showingHistory=false;"
        + "function loadSavedSearch(){try{return window.sessionStorage.getItem(searchStateKey)||'';}catch(_){return '';}}"
        + "function saveSearch(q){try{if(q){window.sessionStorage.setItem(searchStateKey,q);}else{window.sessionStorage.removeItem(searchStateKey);}}catch(_){}}"
        + "function loadTweetsEnabled(){try{return window.sessionStorage.getItem(tweetsStateKey)!=='0';}catch(_){return true;}}"
        + "function saveTweetsEnabled(v){try{window.sessionStorage.setItem(tweetsStateKey,v?'1':'0');}catch(_){}}"
        + "function esc(v){return String(v||'').replace(/[&<>\"']/g,function(ch){return {'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[ch];});}"
        + "function render(matches,emptyText){"
        + "if(!matches){hit.textContent='';return;}"
        + "if(!matches.length){hit.textContent=emptyText||'No matching titles found.';return;}"
        + "hit.innerHTML='<div>'+matches.length+' result'+(matches.length===1?'':'s')+'</div><ul class=\"dg-search-results\">'+matches.map(function(e){return '<li><a href=\"'+esc(e.href)+'\">'+esc(e.name)+'</a> <span class=\"dg-search-folder\">'+esc(e.folder)+'</span></li>';}).join('')+'</ul>';"
        + "}"
        + "function run(){"
        + "showingHistory=false;"
        + "const q=norm(input.value);"
        + "saveSearch(q);"
        + "if(!q){render(null);return;}"
        + "if(!searchIndexReady){hit.textContent='Loading search index...';return;}"
        + "const terms=queryTerms(q);"
        + "const includeTweets=!tweetsToggle||tweetsToggle.checked;"
        + "render(entries.filter(function(e){if(!includeTweets&&e&&e.category==='tweets')return false;const title=e&&String(e.stem||'');return title&&terms.every(function(term){return wholeTermMatch(title,term);});}));"
        + "}"
        + "function loadSearchIndex(){"
        + "return fetch('/search-index.json').then(function(res){if(!res.ok)throw new Error('load failed');return res.json();}).then(function(payload){entries=Array.isArray(payload&&payload.entries)?payload.entries:[];suggestions=Array.isArray(payload&&payload.suggestions)?payload.suggestions:[];searchIndexReady=true;}).catch(function(){entries=[];suggestions=[];searchIndexReady=true;});"
        + "}"
        + "function showHistory(){"
        + "showingHistory=true;"
        + "hit.textContent='Loading history...';"
        + "return fetch('/history-index.json',{cache:'no-store'}).then(function(res){if(!res.ok)throw new Error('load failed');return res.json();}).then(function(payload){render(Array.isArray(payload&&payload.entries)?payload.entries:[],'No reading history found.');}).catch(function(){hit.textContent='Could not load history.';});"
        + "}"
        + "form.addEventListener('submit',function(ev){ev.preventDefault();run();});"
        + "if(tweetsToggle){tweetsToggle.checked=loadTweetsEnabled();tweetsToggle.addEventListener('change',function(){saveTweetsEnabled(tweetsToggle.checked);run();});}"
        + "if(randomButton){randomButton.addEventListener('click',function(){if(!suggestions.length)return;input.value=suggestions[Math.floor(Math.random()*suggestions.length)];saveSearch(norm(input.value));render(null);input.focus();});}"
        + "if(historyLink){historyLink.addEventListener('click',function(ev){ev.preventDefault();showHistory();});}"
        + "window.addEventListener('pageshow',function(){if(input.value){run();}});"
        + "const savedSearch=loadSavedSearch();"
        + "if(savedSearch&&!input.value){input.value=savedSearch;}"
        + "loadSearchIndex().then(function(){if(input.value&&!showingHistory){run();}});"
        + "})();"
        + "</script>"
    )


def _dir_has_visible_entries(
    path: Path,
    cache: dict[str, bool],
    *,
    base_dir: Path,
    reading_items: dict[str, dict],
    done_items: dict[str, dict],
) -> bool:
    key = str(path.resolve())
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        with os.scandir(path) as it:
            for entry in it:
                name = entry.name
                if _skip_directory(name) and entry.is_dir(follow_symlinks=False):
                    continue
                if _is_hidden_name(name):
                    continue

                try:
                    if entry.is_dir(follow_symlinks=False):
                        if _dir_has_visible_entries(
                            Path(entry.path),
                            cache,
                            base_dir=base_dir,
                            reading_items=reading_items,
                            done_items=done_items,
                        ):
                            cache[key] = True
                            return True
                    else:
                        if _is_visible_file_name(name):
                            try:
                                rel = rel_path_from_abs(base_dir, Path(entry.path))
                            except Exception:
                                continue
                            if rel in reading_items or rel in done_items:
                                continue
                            cache[key] = True
                            return True
                except OSError:
                    continue
    except OSError:
        cache[key] = False
        return False

    cache[key] = False
    return False


def _count_visible_files(
    path: Path,
    cache: dict[str, int],
    *,
    base_dir: Path,
    reading_items: dict[str, dict],
    done_items: dict[str, dict],
) -> int:
    key = str(path.resolve())
    cached = cache.get(key)
    if cached is not None:
        return cached

    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                name = entry.name
                if _is_hidden_name(name):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if _skip_directory(name):
                            continue
                        total += _count_visible_files(
                            Path(entry.path),
                            cache,
                            base_dir=base_dir,
                            reading_items=reading_items,
                            done_items=done_items,
                        )
                    else:
                        if _is_visible_file_name(name):
                            try:
                                rel = rel_path_from_abs(base_dir, Path(entry.path))
                            except Exception:
                                continue
                            if rel in reading_items or rel in done_items:
                                continue
                            total += 1
                except OSError:
                    continue
    except OSError:
        total = 0

    cache[key] = total
    return total


def _annotate_root_year_counts(
    *,
    category: str,
    rel_dir: Path,
    abs_dir: Path,
    entries: list[BrowseEntry],
    base_dir: Path,
    reading_items: dict[str, dict],
    done_items: dict[str, dict],
) -> list[BrowseEntry]:
    if rel_dir != Path(".") or category not in YEAR_COUNT_CATEGORIES:
        return entries

    count_cache: dict[str, int] = {}
    annotated: list[BrowseEntry] = []
    for entry in entries:
        if entry.is_dir and _extract_entry_year(entry) is not None:
            child_abs = abs_dir / entry.name
            item_count = _count_visible_files(
                child_abs,
                count_cache,
                base_dir=base_dir,
                reading_items=reading_items,
                done_items=done_items,
            )
            annotated.append(replace(entry, item_count=item_count))
            continue
        annotated.append(entry)
    return annotated


def _category_for_root_segment(segment: str) -> str | None:
    mapping = {
        "Posts": "posts",
        "Tweets": "tweets",
        "Pdfs": "pdfs",
        "PDFs": "pdfs",
        "Images": "images",
        "Podcasts": "podcasts",
    }
    return mapping.get(segment)


def _category_and_rel_dir(rel_path: str) -> tuple[str | None, Path | None]:
    normalized = normalize_rel_path(rel_path)
    parts = Path(normalized).parts
    if not parts:
        return None, None

    category = _category_for_root_segment(parts[0])
    if category is None:
        return None, None

    tail_parts = parts[1:]
    if not tail_parts:
        return category, Path(".")
    return category, Path(*tail_parts).parent


def _display_path_for_category_dir(category: str, rel_dir: Path) -> str:
    if rel_dir == Path("."):
        return f"/browse/{category}/"
    return f"/browse/{category}/{rel_dir.as_posix()}/"


def _cleanup_obsolete_incoming_dir(base_dir: Path) -> None:
    browse_dir = site_root(base_dir) / "browse"
    incoming_dir = browse_dir / "incoming"
    if incoming_dir.exists():
        shutil.rmtree(incoming_dir)


def _reset_browse_category_output(base_dir: Path, category: str) -> None:
    category_dir = site_root(base_dir) / "browse" / category
    if category_dir.exists():
        shutil.rmtree(category_dir)


def _scan_directory(
    *,
    base_dir: Path,
    category: str,
    abs_dir: Path,
    reading_items: dict[str, dict],
    done_items: dict[str, dict],
    visibility_cache: dict[str, bool],
) -> tuple[list[BrowseEntry], list[str], int]:
    entries: list[BrowseEntry] = []
    child_dirs: list[str] = []
    file_count = 0

    try:
        with os.scandir(abs_dir) as it:
            for fs_entry in it:
                name = fs_entry.name
                if _is_hidden_name(name):
                    continue

                try:
                    st = fs_entry.stat()
                except OSError:
                    continue

                try:
                    if fs_entry.is_dir(follow_symlinks=False):
                        if _skip_directory(name):
                            continue
                        child_abs = Path(fs_entry.path)
                        if not _dir_has_visible_entries(
                            child_abs,
                            visibility_cache,
                            base_dir=base_dir,
                            reading_items=reading_items,
                            done_items=done_items,
                        ):
                            continue

                        child_dirs.append(name)
                        entries.append(
                            BrowseEntry(
                                name=name,
                                href=f"{_safe_quote_component(name)}/",
                                mtime=st.st_mtime,
                                sort_mtime=st.st_mtime,
                                is_dir=True,
                                icon="📁 ",
                            )
                        )
                        continue
                except OSError:
                    continue

                if not _is_visible_file_name(name):
                    continue

                abs_path = Path(fs_entry.path)
                rel = rel_path_from_abs(base_dir, abs_path)
                if rel in reading_items or rel in done_items:
                    continue

                file_count += 1

                display_mtime = st.st_mtime
                effective_mtime = display_mtime
                temporal_epoch = effective_mtime
                if category == "posts":
                    post_epoch = _post_effective_date_epoch(abs_path)
                    if post_epoch is not None:
                        effective_mtime = post_epoch
                    temporal_epoch = post_epoch
                highlighted, highlight_last_epoch = _highlight_status(base_dir, rel)
                entries.append(
                    BrowseEntry(
                        name=name,
                        href=viewer_url_for_rel_path(rel),
                        mtime=display_mtime,
                        sort_mtime=effective_mtime,
                        is_dir=False,
                        icon=_icon_for_filename(name),
                        rel_path=rel,
                        highlighted=highlighted,
                        highlight_last_epoch=highlight_last_epoch,
                        temporal_epoch=temporal_epoch,
                        filter_text=_filter_text_for_path(abs_path),
                    )
                )
    except OSError:
        return [], [], 0

    entries.sort(key=_entry_sort_key)
    child_dirs.sort()
    return entries, child_dirs, file_count


def _write_category_directory_page(
    *,
    base_dir: Path,
    category: str,
    category_root: Path,
    rel_dir: Path,
    reading_items: dict[str, dict],
    done_items: dict[str, dict],
    visibility_cache: dict[str, bool],
) -> tuple[list[str], int]:
    out_root = site_root(base_dir) / "browse" / category
    out_root.mkdir(parents=True, exist_ok=True)

    abs_dir = category_root / rel_dir
    out_dir = out_root / rel_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    entries, child_dirs, direct_files = _scan_directory(
        base_dir=base_dir,
        category=category,
        abs_dir=abs_dir,
        reading_items=reading_items,
        done_items=done_items,
        visibility_cache=visibility_cache,
    )
    if category in YEAR_SORT_CATEGORIES and rel_dir == Path("."):
        entries = _sort_root_year_entries(entries)
    entries = _annotate_root_year_counts(
        category=category,
        rel_dir=rel_dir,
        abs_dir=abs_dir,
        entries=entries,
        base_dir=base_dir,
        reading_items=reading_items,
        done_items=done_items,
    )
    display_path = _display_path_for_category_dir(category, rel_dir)
    entry_sections = _temporal_sections_for_category_year(
        category=category,
        rel_dir=rel_dir,
        entries=entries,
    )
    html_doc = _render_directory_page(
        title=f"Index of {display_path}",
        display_path=display_path,
        entries=entries,
        parent_href="../",
        entry_sections=entry_sections,
    )
    (out_dir / "index.html").write_text(html_doc, encoding="utf-8")
    return child_dirs, direct_files


def _extract_entry_year(entry: BrowseEntry) -> int | None:
    if not entry.is_dir:
        return None
    match = YEAR_SUFFIX_RE.search(entry.name)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _sort_root_year_entries(entries: list[BrowseEntry]) -> list[BrowseEntry]:
    year_dirs: list[tuple[int, BrowseEntry]] = []
    others: list[BrowseEntry] = []
    for entry in entries:
        year = _extract_entry_year(entry)
        if year is None:
            others.append(entry)
        else:
            year_dirs.append((year, entry))

    year_dirs.sort(key=lambda item: item[0], reverse=True)
    others.sort(key=_entry_sort_key)
    return [entry for _, entry in year_dirs] + others


def _year_from_name(name: str) -> int | None:
    match = YEAR_SUFFIX_RE.search(name)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _temporal_group_year(category: str, rel_dir: Path) -> int | None:
    if category not in TEMPORAL_GROUP_CATEGORIES or rel_dir == Path("."):
        return None

    return _year_from_name(rel_dir.name)


def _entry_local_date(entry: BrowseEntry) -> date | None:
    if entry.temporal_epoch is None:
        return None
    return datetime.fromtimestamp(entry.temporal_epoch).astimezone().date()


def _temporal_sections_for_entries(entries: list[BrowseEntry]) -> list[tuple[str, list[BrowseEntry]]]:
    today = _local_today()
    return _relative_temporal_sections_for_entries(entries, today)


def _relative_temporal_sections_for_entries(
    entries: list[BrowseEntry],
    today: date,
) -> list[tuple[str, list[BrowseEntry]]]:
    yesterday = today - timedelta(days=1)
    last_7_start = today - timedelta(days=7)
    last_30_start = today - timedelta(days=30)

    labels: list[str] = ["Hoy", "Ayer", "Últimos 7 días", "Últimos 30 días"]
    for month in range(today.month - 1, 0, -1):
        labels.append(f"{SPANISH_MONTH_NAMES[month]} {today.year}")

    buckets: dict[str, list[BrowseEntry]] = {label: [] for label in labels}
    extra_months: dict[tuple[int, int], list[BrowseEntry]] = {}
    undated: list[BrowseEntry] = []

    for entry in entries:
        entry_date = _entry_local_date(entry)
        if entry_date is None:
            undated.append(entry)
        elif entry_date == today:
            buckets["Hoy"].append(entry)
        elif entry_date == yesterday:
            buckets["Ayer"].append(entry)
        elif entry_date >= last_7_start:
            buckets["Últimos 7 días"].append(entry)
        elif entry_date >= last_30_start:
            buckets["Últimos 30 días"].append(entry)
        elif entry_date.year == today.year and entry_date.month < today.month:
            buckets[f"{SPANISH_MONTH_NAMES[entry_date.month]} {entry_date.year}"].append(entry)
        else:
            extra_months.setdefault((entry_date.year, entry_date.month), []).append(entry)

    sections = [(label, buckets[label]) for label in labels if buckets[label]]
    for year, month in sorted(extra_months, reverse=True):
        month_name = SPANISH_MONTH_NAMES.get(month, f"{month:02d}")
        sections.append((f"{month_name} {year}", extra_months[(year, month)]))
    if undated:
        sections.append(("Sin fecha", undated))
    return sections


def _monthly_sections_for_entries(
    entries: list[BrowseEntry],
    year: int,
) -> list[tuple[str, list[BrowseEntry]]]:
    buckets: dict[int, list[BrowseEntry]] = {month: [] for month in range(12, 0, -1)}
    extra_months: dict[tuple[int, int], list[BrowseEntry]] = {}
    undated: list[BrowseEntry] = []

    for entry in entries:
        entry_date = _entry_local_date(entry)
        if entry_date is None:
            undated.append(entry)
        elif entry_date.year == year:
            buckets[entry_date.month].append(entry)
        else:
            extra_months.setdefault((entry_date.year, entry_date.month), []).append(entry)

    sections: list[tuple[str, list[BrowseEntry]]] = []
    for month in range(12, 0, -1):
        month_entries = buckets[month]
        if month_entries:
            sections.append((f"{SPANISH_MONTH_NAMES[month]} {year}", month_entries))

    for extra_year, month in sorted(extra_months, reverse=True):
        month_name = SPANISH_MONTH_NAMES.get(month, f"{month:02d}")
        sections.append((f"{month_name} {extra_year}", extra_months[(extra_year, month)]))
    if undated:
        sections.append(("Sin fecha", undated))
    return sections


def _yearly_sections_for_entries(entries: list[BrowseEntry]) -> list[tuple[str, list[BrowseEntry]]]:
    buckets: dict[int, list[BrowseEntry]] = {}
    undated: list[BrowseEntry] = []

    for entry in entries:
        entry_date = _entry_local_date(entry)
        if entry_date is None:
            undated.append(entry)
        else:
            buckets.setdefault(entry_date.year, []).append(entry)

    sections = [(str(year), buckets[year]) for year in sorted(buckets, reverse=True)]
    if undated:
        sections.append(("Sin fecha", undated))
    return sections


def _temporal_sections_for_category_year(
    *,
    category: str,
    rel_dir: Path,
    entries: list[BrowseEntry],
) -> list[tuple[str, list[BrowseEntry]]] | None:
    year = _temporal_group_year(category, rel_dir)
    if year is None:
        return None
    if category == "posts" and year == 1990:
        return _yearly_sections_for_entries(entries)

    today = _local_today()
    if year == today.year:
        return _relative_temporal_sections_for_entries(entries, today)
    return _monthly_sections_for_entries(entries, year)


def _write_category_tree(
    *,
    base_dir: Path,
    category: str,
    category_root: Path,
    reading_items: dict[str, dict],
    done_items: dict[str, dict],
) -> int:
    visibility_cache: dict[str, bool] = {}

    def walk(rel_dir: Path) -> int:
        child_dirs, direct_files = _write_category_directory_page(
            base_dir=base_dir,
            category=category,
            category_root=category_root,
            rel_dir=rel_dir,
            reading_items=reading_items,
            done_items=done_items,
            visibility_cache=visibility_cache,
        )

        total_files = direct_files
        for child in child_dirs:
            total_files += walk(rel_dir / child)
        return total_files

    return walk(Path("."))


def _write_browse_home(base_dir: Path, category_roots: dict[str, Path], counts: dict[str, int]) -> None:
    out_dir = site_root(base_dir) / "browse"
    out_dir.mkdir(parents=True, exist_ok=True)

    now = time.time()
    entries: list[BrowseEntry] = []
    for category in CATEGORY_KEYS:
        root = category_roots[category]
        label = CATEGORY_LABELS[category]
        count = counts.get(category, 0)
        if root.exists():
            try:
                mtime = root.stat().st_mtime
            except OSError:
                mtime = now
        else:
            mtime = now

        entries.append(
            BrowseEntry(
                name=label,
                href=f"{category}/",
                mtime=mtime,
                sort_mtime=mtime,
                is_dir=True,
                icon="📁 ",
                item_count=count,
            )
        )

    html_doc = _render_directory_page(
        title="Index of /browse/",
        display_path="/browse/",
        entries=entries,
        parent_href="/",
        controls_html="",
    )
    html_doc = html_doc.replace(
        "</ul><hr></body></html>",
        "</ul><p><button class='dg-rebuild' data-api-action='rebuild'>Rebuild browse + reading + done</button></p><hr></body></html>",
    )
    (out_dir / "index.html").write_text(html_doc, encoding="utf-8")


def write_site_home(base_dir: Path, category_roots: dict[str, Path] | None = None) -> None:
    out_dir = site_root(base_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if category_roots is None:
        category_roots = _category_roots(base_dir)
    search_entries = _collect_browse_search_entries(base_dir, category_roots)
    _write_site_search_index(base_dir, search_entries)
    write_site_history_index(base_dir)
    search_controls = _search_controls_html()
    search_result = _search_result_html()
    search_js = _search_script_html()

    html_doc = (
        "<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>Docflow</title>"
        "<style>body{margin:14px 18px;font:14px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;color:#222}"
        "h1{margin:6px 0 10px;font-weight:600}a{color:#0a7;text-decoration:none}"
        ".dg-search{display:inline-flex;align-items:center;gap:6px}"
        ".dg-search input[type='text']{padding:3px 8px;border:1px solid #ccc;border-radius:6px;min-width:420px;max-width:100%;font:13px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial}"
        ".dg-search button{padding:2px 8px;border:1px solid #ccc;border-radius:6px;background:#f7f7f7;color:#333;font:12px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;cursor:pointer}"
        ".dg-search-toggle{display:inline-flex;align-items:center;gap:4px;color:#555;font:13px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;white-space:nowrap}"
        ".dg-search-toggle input{margin:0}"
        ".dg-search-hit{margin:6px 0 10px;font:13px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;color:#444}"
        ".dg-search-hit a{color:#0a7;text-decoration:none}"
        ".dg-search-results{list-style:none;padding-left:0;margin:6px 0 0}"
        ".dg-search-results li{margin:3px 0}"
        ".dg-search-folder{color:#666;margin-left:6px}"
        ".dg-actions button{padding:2px 6px;border:1px solid #ccc;border-radius:6px;background:#f7f7f7;color:#333;font:12px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;cursor:pointer}"
        "</style><script src='/assets/actions.js' defer></script></head><body>"
        "<h1>Docflow Intranet</h1>"
        "<p><a href='/browse/'>Browse</a> · <a href='/reading/'>Reading</a> · <a href='/done/'>Done</a></p>"
        f"{_home_history_link_html()}"
        "<p><button data-api-action='rebuild'>Rebuild browse + reading + done</button></p>"
        f"{search_controls}"
        f"{search_result}"
        f"{search_js}"
        "</body></html>"
    )

    output = out_dir / "index.html"
    output.write_text(html_doc, encoding="utf-8")


def ensure_assets(base_dir: Path) -> None:
    assets_dir = site_root(base_dir) / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    js = """
(function() {
  window.addEventListener('pageshow', (event) => {
    if (document.querySelector('[data-dg-search-form]')) return;
    let navType = '';
    try {
      const entries = performance.getEntriesByType('navigation');
      if (entries && entries.length > 0) navType = entries[0].type || '';
    } catch (error) {}
    if (event.persisted || navType === 'back_forward') {
      window.location.reload();
    }
  });

  async function callApi(action, path) {
    const body = path ? { path } : {};
    const response = await fetch(`/api/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    return response.ok;
  }

  document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-api-action]');
    if (!button) return;
    event.preventDefault();

    const action = button.getAttribute('data-api-action');
    const path = button.getAttribute('data-docflow-path') || '';
    button.setAttribute('disabled', '');

    try {
      const ok = await callApi(action, path);
      if (!ok) {
        alert(`Action failed: ${action}`);
        button.removeAttribute('disabled');
        return;
      }
      window.location.reload();
    } catch (error) {
      alert(`Action error: ${action}`);
      button.removeAttribute('disabled');
    }
  });
})();
""".strip()

    browse_sort_js = """
(function() {
  function currentNavigationType() {
    try {
      const entries = performance.getEntriesByType('navigation');
      if (entries && entries.length > 0) return entries[0].type || '';
    } catch (error) {}
    return '';
  }

  window.addEventListener('pageshow', (event) => {
    const navType = currentNavigationType();
    if (event.persisted || navType === 'back_forward') {
      window.location.reload();
    }
  });

  function asNumber(value) {
    const num = Number(value);
    return Number.isFinite(num) ? num : 0;
  }

  const highlightPreferenceKey = 'docflow.highlight-sort';
  const contentFilterPreferencePrefix = 'docflow.content-filter.';
  const contentFilterSamplePrefix = 'docflow.content-filter-sample.';

  function loadHighlightPreference() {
    try {
      return window.localStorage.getItem(highlightPreferenceKey) === 'on';
    } catch (error) {
      return false;
    }
  }

  function saveHighlightPreference(highlightsFirst) {
    try {
      window.localStorage.setItem(highlightPreferenceKey, highlightsFirst ? 'on' : 'off');
    } catch (error) {}
  }

  function contentFilterPreferenceKey() {
    return contentFilterPreferencePrefix + window.location.pathname;
  }

  function contentFilterSampleKey() {
    return contentFilterSamplePrefix + window.location.pathname;
  }

  function loadContentFilterPreference() {
    try {
      const payload = JSON.parse(window.sessionStorage.getItem(contentFilterPreferenceKey()) || 'null');
      return payload && typeof payload.terms === 'string' ? payload.terms : '';
    } catch (error) {
      return '';
    }
  }

  function saveContentFilterPreference(terms) {
    try {
      if (terms) {
        window.sessionStorage.setItem(contentFilterPreferenceKey(), JSON.stringify({ terms }));
      } else {
        window.sessionStorage.removeItem(contentFilterPreferenceKey());
      }
    } catch (error) {}
  }

  function loadContentFilterSample() {
    try {
      const payload = JSON.parse(window.sessionStorage.getItem(contentFilterSampleKey()) || 'null');
      return Array.isArray(payload) ? payload.filter((item) => typeof item === 'string' && item.trim()) : [];
    } catch (error) {
      return [];
    }
  }

  function saveContentFilterSample(sample) {
    try {
      if (sample.length > 0) {
        window.sessionStorage.setItem(contentFilterSampleKey(), JSON.stringify(sample));
      } else {
        window.sessionStorage.removeItem(contentFilterSampleKey());
      }
    } catch (error) {}
  }

  function syncToggleState(toggle, highlightsFirst) {
    toggle.textContent = highlightsFirst ? 'Highlight: on' : 'Highlight: off';
    toggle.classList.toggle('is-active', highlightsFirst);
    toggle.setAttribute('aria-pressed', highlightsFirst ? 'true' : 'false');
  }

  function normalizeText(value) {
    return String(value || '')
      .normalize('NFD')
      .replace(/[\\u0300-\\u036f]/g, '')
      .toLowerCase();
  }

  function termsForFilter(button) {
    return (button.getAttribute('data-dg-filter-terms') || '')
      .split('|')
      .map((term) => normalizeText(term.trim()))
      .filter(Boolean);
  }

  function parseContentFilterPool(slot) {
    if (!slot) return [];
    try {
      const parsed = JSON.parse(slot.getAttribute('data-dg-content-filter-pool') || '[]');
      return Array.isArray(parsed) ? parsed.filter((item) => typeof item === 'string' && item.trim()) : [];
    } catch (error) {
      return [];
    }
  }

  function contentTermsForNode(node) {
    if (node._dgContentFilterTerms) return node._dgContentFilterTerms;
    try {
      const parsed = JSON.parse(node.dataset.dgFilterTerms || '[]');
      node._dgContentFilterTerms = Array.isArray(parsed)
        ? parsed.map((item) => normalizeText(item)).filter(Boolean)
        : [];
    } catch (error) {
      node._dgContentFilterTerms = [];
    }
    return node._dgContentFilterTerms;
  }

  function matchesFilterTerms(itemTerms, terms) {
    if (terms.length === 0) return true;
    const itemSet = new Set(itemTerms);
    return terms.some((term) => itemSet.has(term));
  }

  function shuffledSample(values, count) {
    const pool = [...values];
    for (let index = pool.length - 1; index > 0; index -= 1) {
      const swapIndex = Math.floor(Math.random() * (index + 1));
      const current = pool[index];
      pool[index] = pool[swapIndex];
      pool[swapIndex] = current;
    }
    return pool.slice(0, count);
  }

  function isMultiWordFilter(value) {
    return normalizeText(value).split(/\s+/).filter(Boolean).length > 1;
  }

  function suggestedFilterSample(values, count, preferredValue) {
    const multiWord = values.filter(isMultiWordFilter);
    const singleWord = values.filter((value) => !isMultiWordFilter(value));
    const multiWordCount = Math.min(multiWord.length, count, Math.max(1, Math.round(count * 0.3)));
    const selected = shuffledSample(multiWord, multiWordCount);
    const selectedSet = new Set(selected);
    const remaining = singleWord.concat(multiWord.filter((value) => !selectedSet.has(value)));
    let sample = selected.concat(shuffledSample(remaining, count - selected.length));
    if (preferredValue && values.includes(preferredValue) && !sample.includes(preferredValue)) {
      sample = [preferredValue].concat(sample).slice(0, count);
    }
    return sample;
  }

  function renderSuggestedFilters(slot, preferredValue, reuseStoredSample) {
    const pool = parseContentFilterPool(slot);
    const count = Number(slot && slot.getAttribute('data-dg-content-filter-count')) || 7;
    if (!slot || pool.length === 0) return;
    const poolSet = new Set(pool);
    let sample = reuseStoredSample
      ? loadContentFilterSample().filter((value, index, values) => poolSet.has(value) && values.indexOf(value) === index)
      : [];
    sample = sample.slice(0, count);
    if (preferredValue && poolSet.has(preferredValue) && !sample.includes(preferredValue)) {
      sample = [preferredValue].concat(sample).slice(0, count);
    }
    if (sample.length < Math.min(count, pool.length)) {
      const sampleSet = new Set(sample);
      const remaining = pool.filter((value) => !sampleSet.has(value));
      sample = sample.concat(suggestedFilterSample(remaining, count - sample.length, ''));
    }
    if (sample.length === 0) {
      sample = suggestedFilterSample(pool, count, preferredValue);
    }
    saveContentFilterSample(sample);
    slot.replaceChildren();
    sample.forEach((term, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'dg-content-filter';
      button.setAttribute('data-dg-content-filter', `suggested-${index}`);
      button.setAttribute('data-dg-filter-terms', term);
      button.setAttribute('aria-pressed', 'false');
      button.textContent = term;
      slot.appendChild(button);
    });
  }

  function compareEntries(a, b, highlightsFirst, sortDirection) {
    if (highlightsFirst) {
      const aHl = a.dataset.dgHighlighted === '1' ? 0 : 1;
      const bHl = b.dataset.dgHighlighted === '1' ? 0 : 1;
      if (aHl !== bHl) return aHl - bHl;

      if (aHl === 0) {
        const aLast = asNumber(a.dataset.dgHighlightLast);
        const bLast = asNumber(b.dataset.dgHighlightLast);
        if (aLast !== bLast) return bLast - aLast;
      }
    }

    const aSort = asNumber(a.dataset.dgSortMtime);
    const bSort = asNumber(b.dataset.dgSortMtime);
    if (aSort !== bSort) {
      if (sortDirection === 'asc') return aSort - bSort;
      return bSort - aSort;
    }

    const aName = a.dataset.dgName || '';
    const bName = b.dataset.dgName || '';
    return aName.localeCompare(bName);
  }

  document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.querySelector('[data-dg-sort-toggle]');
    const doneDefaultView = document.querySelector('[data-dg-highlight-view="default"]');
    const doneHighlightView = document.querySelector('[data-dg-highlight-view="highlight"]');
    if (toggle && doneDefaultView && doneHighlightView) {
      const hasDoneItems = !!doneDefaultView.querySelector('li[data-dg-sortable="1"]');
      let highlightsFirst = loadHighlightPreference();

      if (!hasDoneItems) {
        syncToggleState(toggle, highlightsFirst);
        toggle.setAttribute('disabled', '');
        doneDefaultView.hidden = highlightsFirst;
        doneHighlightView.hidden = !highlightsFirst;
        return;
      }

      function renderDoneViews() {
        doneDefaultView.hidden = highlightsFirst;
        doneHighlightView.hidden = !highlightsFirst;
        syncToggleState(toggle, highlightsFirst);
      }

      toggle.addEventListener('click', () => {
        if (!hasDoneItems) return;
        highlightsFirst = !highlightsFirst;
        saveHighlightPreference(highlightsFirst);
        renderDoneViews();
      });

      renderDoneViews();
      return;
    }

    const lists = Array.from(document.querySelectorAll('ul.dg-index, ul.dg-done-list, ul.dg-reading-list'));
    const filterSlot = document.querySelector('[data-dg-content-filter-pool]');
    const randomFiltersButton = document.querySelector('[data-dg-content-filter-random]');
    const reuseStoredSample = true;
    const savedFilterTerms = loadContentFilterPreference();
    renderSuggestedFilters(filterSlot, savedFilterTerms, reuseStoredSample);
    let filterButtons = Array.from(document.querySelectorAll('[data-dg-content-filter]'));
    const filterSummary = document.querySelector('[data-dg-filter-summary]');
    if (!toggle || lists.length === 0) return;

    const groups = lists.map((list) => {
      const previous = list.previousElementSibling;
      const heading = previous && previous.classList.contains('dg-time-heading') ? previous : null;
      const sortable = Array.from(list.querySelectorAll('li[data-dg-sortable=\"1\"]'));
      const sortableFiles = sortable.filter((node) => {
        const link = node.querySelector('a[href]');
        if (!link) return false;
        const href = (link.getAttribute('href') || '').trim();
        return href !== '' && !href.endsWith('/');
      });
      return { list, heading, sortableFiles };
    }).filter((group) => group.sortableFiles.length > 0);

    let highlightsFirst = loadHighlightPreference();
    let activeFilterKey = '';

    if (groups.length === 0) {
      syncToggleState(toggle, highlightsFirst);
      toggle.setAttribute('disabled', '');
      filterButtons.forEach((button) => button.setAttribute('disabled', ''));
      if (randomFiltersButton) randomFiltersButton.setAttribute('disabled', '');
      return;
    }

    const defaultSortDirection = (toggle.getAttribute('data-dg-sort-direction') || 'desc').toLowerCase() === 'asc'
      ? 'asc'
      : 'desc';

    if (savedFilterTerms) {
      const savedButton = filterButtons.find(
        (button) => (button.getAttribute('data-dg-filter-terms') || '') === savedFilterTerms
      );
      activeFilterKey = savedButton ? (savedButton.getAttribute('data-dg-content-filter') || '') : '';
    }

    function syncFilterState() {
      for (const button of filterButtons) {
        const isActive = button.getAttribute('data-dg-content-filter') === activeFilterKey;
        button.classList.toggle('is-active', isActive);
        button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
      }
    }

    function applyContentFilter() {
      const activeButton = filterButtons.find(
        (button) => button.getAttribute('data-dg-content-filter') === activeFilterKey
      );
      const terms = activeButton ? termsForFilter(activeButton) : [];
      let visibleCount = 0;
      let totalCount = 0;

      for (const group of groups) {
        let groupVisible = 0;
        for (const node of group.sortableFiles) {
          totalCount += 1;
          const isVisible = matchesFilterTerms(contentTermsForNode(node), terms);
          node.hidden = !isVisible;
          if (isVisible) {
            visibleCount += 1;
            groupVisible += 1;
          }
        }
        const hideGroup = terms.length > 0 && groupVisible === 0;
        if (group.heading) group.heading.hidden = hideGroup;
        group.list.hidden = hideGroup;
      }

      syncFilterState();
      if (filterSummary) {
        filterSummary.textContent = terms.length > 0 ? `${visibleCount}/${totalCount} matches` : '';
      }
    }

    function renderOrder() {
      for (const group of groups) {
        const sorted = [...group.sortableFiles].sort((a, b) =>
          compareEntries(a, b, highlightsFirst, defaultSortDirection)
        );
        for (const node of sorted) {
          group.list.appendChild(node);
        }
      }
      syncToggleState(toggle, highlightsFirst);
      applyContentFilter();
    }

    toggle.addEventListener('click', () => {
      highlightsFirst = !highlightsFirst;
      saveHighlightPreference(highlightsFirst);
      renderOrder();
    });

    function bindFilterButtons() {
      for (const button of filterButtons) {
        button.addEventListener('click', () => {
          const key = button.getAttribute('data-dg-content-filter') || '';
          activeFilterKey = activeFilterKey === key ? '' : key;
          saveContentFilterPreference(activeFilterKey ? (button.getAttribute('data-dg-filter-terms') || '') : '');
          applyContentFilter();
        });
      }
    }

    bindFilterButtons();

    if (randomFiltersButton) {
      randomFiltersButton.addEventListener('click', () => {
        activeFilterKey = '';
        saveContentFilterPreference('');
        renderSuggestedFilters(filterSlot, '', false);
        filterButtons = Array.from(document.querySelectorAll('[data-dg-content-filter]'));
        bindFilterButtons();
        renderOrder();
      });
    }

    renderOrder();
  });
})();
""".strip()

    css = """
/* Base styles for shared intranet pages */
body { margin:14px 18px; font:14px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial; color:#222; }
header h1 { margin:6px 0 10px; font-weight:600; }
header nav a { color:#0a7; text-decoration:none; }
main { max-width: 1100px; }
.dg-list { list-style:none; padding-left:0; }
.dg-list li { padding:6px 0; border-bottom:1px solid #ececec; display:flex; justify-content:space-between; gap:10px; align-items:center; }
.dg-sub { color:#666; font-size:13px; }
.dg-actions { display:inline-flex; gap:6px; }
.dg-actions button, button[data-api-action] { padding:2px 6px; border:1px solid #ccc; border-radius:6px; background:#f7f7f7; color:#333; font:12px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial; cursor:pointer; }
.dg-actions button[disabled], button[data-api-action][disabled] { opacity:.6; pointer-events:none; }
""".strip()

    (assets_dir / "actions.js").write_text(js + "\n", encoding="utf-8")
    (assets_dir / "browse-sort.js").write_text(browse_sort_js + "\n", encoding="utf-8")
    (assets_dir / "site.css").write_text(css + "\n", encoding="utf-8")
    article_js_source = Path(__file__).resolve().parent / "static" / "article.js"
    (assets_dir / "article.js").write_text(article_js_source.read_text(encoding="utf-8"), encoding="utf-8")


def collect_category_items(base_dir: Path, category: str) -> list[BrowseItem]:
    """Compatibility helper used by tests (recursive file summary)."""
    roots = _category_roots(base_dir)
    root = roots[category]
    if not root.is_dir():
        return []

    done_state = load_done_state(base_dir)
    done_state_items = done_state.get("items", {})
    done_items = done_state_items if isinstance(done_state_items, dict) else {}
    reading_state = load_reading_state(base_dir)
    reading_state_items = reading_state.get("items", {})
    reading_items = reading_state_items if isinstance(reading_state_items, dict) else {}

    items: list[BrowseItem] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel_to_root = path.relative_to(root)
        if any(_skip_directory(part) for part in rel_to_root.parts[:-1]):
            continue
        if not _is_visible_file_name(path.name):
            continue

        rel = rel_path_from_abs(base_dir, path)
        reading_entry = reading_items.get(rel)
        is_reading = rel in reading_items
        st = path.stat()
        done_entry = done_items.get(rel)
        done_at_mtime = None
        if isinstance(done_entry, dict):
            done_at_mtime = _iso_to_epoch(done_entry.get("done_at"))
        is_done = rel in done_items
        if is_done:
            is_reading = False

        reading_at_mtime = None
        if isinstance(reading_entry, dict):
            reading_at_mtime = _iso_to_epoch(reading_entry.get("reading_at"))
        display_mtime = st.st_mtime
        if is_reading and reading_at_mtime is not None:
            effective_mtime = reading_at_mtime
        elif is_done and done_at_mtime is not None:
            effective_mtime = done_at_mtime
        else:
            effective_mtime = display_mtime
        highlighted, highlight_last_epoch = _highlight_status(base_dir, rel)

        items.append(
            BrowseItem(
                rel_path=rel,
                name=path.name,
                mtime=display_mtime,
                sort_mtime=effective_mtime,
                reading=is_reading,
                highlighted=highlighted,
                highlight_last_epoch=highlight_last_epoch,
            )
        )

    items.sort(
        key=lambda item: (
            0 if item.reading else 1,
            -(item.sort_mtime if item.sort_mtime is not None else item.mtime),
            item.name.lower(),
        )
    )
    return items


def _category_roots(base_dir: Path) -> dict[str, Path]:
    roots = library_roots(base_dir)
    return {
        "posts": roots["posts"],
        "tweets": roots["tweets"],
        "pdfs": roots["pdfs"],
        "images": roots["images"],
        "podcasts": roots["podcasts"],
    }


def rebuild_browse_for_path(base_dir: Path, rel_path: str) -> dict[str, object]:
    """Incremental browse rebuild for one affected library file path.

    Rebuilds only the containing directory and its ancestors in the matching category.
    Falls back to full rebuild for unsupported paths.
    """
    ensure_assets(base_dir)
    _cleanup_obsolete_incoming_dir(base_dir)

    try:
        normalized = normalize_rel_path(rel_path)
    except Exception:
        counts = build_browse_site(base_dir)
        return {"mode": "full", "reason": "invalid_path", "counts": counts}

    category, rel_dir = _category_and_rel_dir(normalized)
    if category is None or rel_dir is None:
        counts = build_browse_site(base_dir)
        return {"mode": "full", "reason": "unsupported_root", "counts": counts}

    reading_state = load_reading_state(base_dir)
    reading_state_items = reading_state.get("items", {})
    reading_items = reading_state_items if isinstance(reading_state_items, dict) else {}
    done_state = load_done_state(base_dir)
    done_state_items = done_state.get("items", {})
    done_items = done_state_items if isinstance(done_state_items, dict) else {}
    roots = _category_roots(base_dir)
    category_root = roots[category]
    visibility_cache: dict[str, bool] = {}

    dirs_to_update: list[Path] = []
    if rel_dir == Path("."):
        dirs_to_update.append(Path("."))
    else:
        cursor = rel_dir
        while True:
            dirs_to_update.append(cursor)
            if cursor.parent == Path("."):
                break
            cursor = cursor.parent

    updated_paths: list[str] = []
    for target_rel_dir in dirs_to_update:
        _write_category_directory_page(
            base_dir=base_dir,
            category=category,
            category_root=category_root,
            rel_dir=target_rel_dir,
            reading_items=reading_items,
            done_items=done_items,
            visibility_cache=visibility_cache,
        )
        updated_paths.append(_display_path_for_category_dir(category, target_rel_dir))

    return {
        "mode": "partial",
        "category": category,
        "updated": updated_paths,
    }


def build_browse_site(base_dir: Path) -> dict[str, int]:
    ensure_assets(base_dir)
    _cleanup_obsolete_incoming_dir(base_dir)

    reading_state = load_reading_state(base_dir)
    reading_state_items = reading_state.get("items", {})
    reading_items = reading_state_items if isinstance(reading_state_items, dict) else {}
    done_state = load_done_state(base_dir)
    done_state_items = done_state.get("items", {})
    done_items = done_state_items if isinstance(done_state_items, dict) else {}
    roots = _category_roots(base_dir)

    counts: dict[str, int] = {}
    for category in CATEGORY_KEYS:
        _reset_browse_category_output(base_dir, category)
        counts[category] = _write_category_tree(
            base_dir=base_dir,
            category=category,
            category_root=roots[category],
            reading_items=reading_items,
            done_items=done_items,
        )

    _write_browse_home(base_dir, roots, counts)
    write_site_home(base_dir, roots)
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate static browse pages for the local intranet site.")
    parser.add_argument("--base-dir", help="BASE_DIR containing Incoming/ Posts/ Tweets/ ...")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_dir = resolve_base_dir(args.base_dir)
    counts = build_browse_site(base_dir)
    print(f"✓ Generated browse pages in {site_root(base_dir) / 'browse'} ({counts})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
