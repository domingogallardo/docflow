"""Generate static browse pages under BASE_DIR/_site/browse.

The generated browse UI mirrors the intranet local reading workflow while
keeping pages static.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import time
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
    site_root,
    viewer_url_for_rel_path,
)
from utils.highlight_store import highlight_status_for_path
from utils.markdown_utils import split_front_matter
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
SEARCH_SUGGESTION_STOPWORDS = {
    "a",
    "al",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "con",
    "de",
    "del",
    "el",
    "en",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "la",
    "las",
    "le",
    "lo",
    "los",
    "of",
    "on",
    "or",
    "para",
    "por",
    "que",
    "se",
    "según",
    "the",
    "to",
    "un",
    "una",
    "what",
    "why",
    "with",
    "y",
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
    item_count: int | None = None


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
        "body{margin:14px 18px;font:14px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;color:#222}"
        "h2{margin:6px 0 10px;font-weight:600}"
        "hr{border:0;border-top:1px solid #e6e6e6;margin:8px 0}"
        "ul.dg-index{list-style:none;padding-left:0}"
        ".dg-index li{padding:2px 6px;border-radius:6px;margin:2px 0;display:flex;justify-content:space-between;align-items:center;gap:10px}"
        ".dg-legendbar{display:flex;align-items:center;justify-content:flex-start;gap:6px;flex-wrap:wrap;margin-bottom:6px}"
        ".dg-legend{color:#666;font:13px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial}"
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
        ".dg-sort-toggle{padding:2px 8px;border:1px solid #ccc;border-radius:6px;background:#f7f7f7;color:#333;font:12px -apple-system,system-ui,Segoe UI,Roboto,Helvetica,Arial;cursor:pointer}"
        ".dg-sort-toggle.is-active{border-color:#c8a400;background:#fff6e5}"
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
        controls_html = (
            "<button type='button' class='dg-sort-toggle' data-dg-sort-toggle aria-pressed='false'>"
            "Highlight: off"
            "</button>"
        )
    rows.append(
        "<div class='dg-legendbar'>"
        "<div class='dg-legend'>🟡 highlight</div>"
        f"{controls_html}"
        "</div>"
    )
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
    if path.suffix.lower() != ".md" or not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    meta, _ = split_front_matter(text)
    return _iso_to_epoch(meta.get("docflow_ingested_at"))


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


def _search_script_html(search_entries: list[dict[str, str]]) -> str:
    search_payload = json.dumps(search_entries, ensure_ascii=False).replace("</", "<\\/")
    suggestion_payload = json.dumps(_collect_browse_search_suggestions(search_entries), ensure_ascii=False).replace("</", "<\\/")
    return (
        "<script id='dg-browse-search-data' type='application/json'>"
        + search_payload
        + "</script>"
        + "<script id='dg-search-suggestions' type='application/json'>"
        + suggestion_payload
        + "</script>"
        + "<script>"
        + "(function(){"
        + "function norm(v){return String(v||'').trim().replace(/\\.(html?|pdf)$/i,'');}"
        + "function queryTerms(v){return norm(v).split(/\\s+\\+\\s+/).map(norm).filter(Boolean);}"
        + "function escRe(v){return String(v||'').replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&');}"
        + "function wholeTermMatch(title,term){return new RegExp('(^|[^\\\\p{L}\\\\p{N}])'+escRe(term)+'(?=$|[^\\\\p{L}\\\\p{N}])','iu').test(title);}"
        + "const form=document.querySelector('[data-dg-search-form]');"
        + "const input=document.querySelector('[data-dg-search-input]');"
        + "const tweetsToggle=document.querySelector('[data-dg-search-tweets]');"
        + "const randomButton=document.querySelector('[data-dg-search-random]');"
        + "const hit=document.querySelector('[data-dg-search-hit]');"
        + "const dataEl=document.getElementById('dg-browse-search-data');"
        + "const suggestionsEl=document.getElementById('dg-search-suggestions');"
        + "if(!form||!input||!hit||!dataEl)return;"
        + "const searchStateKey='docflow.home.search';"
        + "const tweetsStateKey='docflow.home.search.tweets';"
        + "let entries=[];"
        + "let suggestions=[];"
        + "try{entries=JSON.parse(dataEl.textContent||'[]');}catch(_){entries=[];}"
        + "try{suggestions=JSON.parse((suggestionsEl&&suggestionsEl.textContent)||'[]');}catch(_){suggestions=[];}"
        + "function loadSavedSearch(){try{return window.sessionStorage.getItem(searchStateKey)||'';}catch(_){return '';}}"
        + "function saveSearch(q){try{if(q){window.sessionStorage.setItem(searchStateKey,q);}else{window.sessionStorage.removeItem(searchStateKey);}}catch(_){}}"
        + "function loadTweetsEnabled(){try{return window.sessionStorage.getItem(tweetsStateKey)!=='0';}catch(_){return true;}}"
        + "function saveTweetsEnabled(v){try{window.sessionStorage.setItem(tweetsStateKey,v?'1':'0');}catch(_){}}"
        + "function esc(v){return String(v||'').replace(/[&<>\"']/g,function(ch){return {'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[ch];});}"
        + "function render(matches){"
        + "if(!matches){hit.textContent='';return;}"
        + "if(!matches.length){hit.textContent='No matching titles found.';return;}"
        + "hit.innerHTML='<div>'+matches.length+' result'+(matches.length===1?'':'s')+'</div><ul class=\"dg-search-results\">'+matches.map(function(e){return '<li><a href=\"'+esc(e.href)+'\">'+esc(e.name)+'</a> <span class=\"dg-search-folder\">'+esc(e.folder)+'</span></li>';}).join('')+'</ul>';"
        + "}"
        + "function run(){"
        + "const q=norm(input.value);"
        + "saveSearch(q);"
        + "if(!q){render(null);return;}"
        + "const terms=queryTerms(q);"
        + "const includeTweets=!tweetsToggle||tweetsToggle.checked;"
        + "render(entries.filter(function(e){if(!includeTweets&&e&&e.category==='tweets')return false;const title=e&&String(e.stem||'');return title&&terms.every(function(term){return wholeTermMatch(title,term);});}));"
        + "}"
        + "form.addEventListener('submit',function(ev){ev.preventDefault();run();});"
        + "if(tweetsToggle){tweetsToggle.checked=loadTweetsEnabled();tweetsToggle.addEventListener('change',function(){saveTweetsEnabled(tweetsToggle.checked);run();});}"
        + "if(randomButton){randomButton.addEventListener('click',function(){if(!suggestions.length)return;input.value=suggestions[Math.floor(Math.random()*suggestions.length)];saveSearch(norm(input.value));render(null);input.focus();});}"
        + "window.addEventListener('pageshow',function(){if(input.value){run();}});"
        + "const savedSearch=loadSavedSearch();"
        + "if(savedSearch&&!input.value){input.value=savedSearch;run();}"
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


def _scan_directory(
    *,
    base_dir: Path,
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


def _entry_local_date(entry: BrowseEntry) -> date:
    return datetime.fromtimestamp(_sort_mtime(entry)).astimezone().date()


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

    for entry in entries:
        entry_date = _entry_local_date(entry)
        if entry_date == today:
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
    return sections


def _monthly_sections_for_entries(
    entries: list[BrowseEntry],
    year: int,
) -> list[tuple[str, list[BrowseEntry]]]:
    buckets: dict[int, list[BrowseEntry]] = {month: [] for month in range(12, 0, -1)}
    extra_months: dict[tuple[int, int], list[BrowseEntry]] = {}

    for entry in entries:
        entry_date = _entry_local_date(entry)
        if entry_date.year == year:
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
    search_controls = _search_controls_html()
    search_result = _search_result_html()
    search_js = _search_script_html(search_entries)

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
  window.addEventListener('pageshow', (event) => {
    let navType = '';
    try {
      const entries = performance.getEntriesByType('navigation');
      if (entries && entries.length > 0) navType = entries[0].type || '';
    } catch (error) {}
    if (event.persisted || navType === 'back_forward') {
      window.location.reload();
    }
  });

  function asNumber(value) {
    const num = Number(value);
    return Number.isFinite(num) ? num : 0;
  }

  const highlightPreferenceKey = 'docflow.highlight-sort';

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

  function syncToggleState(toggle, highlightsFirst) {
    toggle.textContent = highlightsFirst ? 'Highlight: on' : 'Highlight: off';
    toggle.classList.toggle('is-active', highlightsFirst);
    toggle.setAttribute('aria-pressed', highlightsFirst ? 'true' : 'false');
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
    if (!toggle || lists.length === 0) return;

    const groups = lists.map((list) => {
      const sortable = Array.from(list.querySelectorAll('li[data-dg-sortable=\"1\"]'));
      const sortableFiles = sortable.filter((node) => {
        const link = node.querySelector('a[href]');
        if (!link) return false;
        const href = (link.getAttribute('href') || '').trim();
        return href !== '' && !href.endsWith('/');
      });
      return { list, sortableFiles };
    }).filter((group) => group.sortableFiles.length > 0);

    let highlightsFirst = loadHighlightPreference();

    if (groups.length === 0) {
      syncToggleState(toggle, highlightsFirst);
      toggle.setAttribute('disabled', '');
      return;
    }

    const defaultSortDirection = (toggle.getAttribute('data-dg-sort-direction') || 'desc').toLowerCase() === 'asc'
      ? 'asc'
      : 'desc';

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
    }

    toggle.addEventListener('click', () => {
      highlightsFirst = !highlightsFirst;
      saveHighlightPreference(highlightsFirst);
      renderOrder();
    });

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
