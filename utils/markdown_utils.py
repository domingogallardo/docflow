import re
import html
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from uuid import uuid4


_FRONT_MATTER_KEYS = {
    "docflow_id": "docflow-id",
    "docflow_markdown_path": "docflow-markdown-path",
    "docflow_html_path": "docflow-html-path",
    "docflow_render_status": "docflow-render-status",
    "source": "docflow-source",
    "source_url": "docflow-source-url",
    "source_name": "docflow-source-name",
    "title": "docflow-title",
    "docflow_source_type": "docflow-source-type",
    "docflow_ingested_at": "docflow-ingested-at",
    "docflow_html_generated_at": "docflow-html-generated-at",
    "docflow_extractor": "docflow-extractor",
    "docflow_extraction_attempt": "docflow-extraction-attempt",
    "docflow_final_url": "docflow-final-url",
    "docflow_original_url": "docflow-original-url",
    "docflow_word_count": "docflow-word-count",
    "docflow_body_chars": "docflow-body-chars",
    "docflow_last_read": "docflow-last-read",
    "docflow_removed_data_images": "docflow-removed-data-images",
    "instapaper_id": "docflow-instapaper-id",
    "podcast_show": "docflow-podcast-show",
    "podcast_episode_title": "docflow-podcast-episode-title",
    "podcast_publish_date": "docflow-podcast-publish-date",
    "podcast_export_date": "docflow-podcast-export-date",
    "tweet_url": "docflow-tweet-url",
    "tweet_id": "docflow-tweet-id",
    "tweet_author": "docflow-tweet-author",
    "tweet_author_name": "docflow-tweet-author-name",
    "tweet_capture_source": "docflow-tweet-capture-source",
    "tweet_posted_kind": "docflow-tweet-posted-kind",
    "tweet_thread": "docflow-tweet-thread",
    "tweet_thread_count": "docflow-tweet-thread-count",
    "tweet_reply_to_url": "docflow-tweet-reply-to-url",
    "tweet_reply_context_included": "docflow-tweet-reply-context-included",
    "tweet_conversation_count": "docflow-tweet-conversation-count",
}

_REMOVED_IMPORTED_FRONT_MATTER_KEYS = frozenset({"description", "tags"})


def split_front_matter(md_text: str) -> tuple[dict[str, str], str]:
    lines = md_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, md_text

    front_lines: list[str] = []
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            meta = _parse_front_matter(front_lines)
            if not meta:
                return {}, md_text
            body = "\n".join(lines[idx + 1 :])
            if md_text.endswith("\n") and not body.endswith("\n"):
                body += "\n"
            return meta, body
        front_lines.append(lines[idx])

    return {}, md_text


def _parse_front_matter(lines: list[str]) -> dict[str, str]:
    meta: dict[str, str] = {}
    for line in lines:
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        value = raw.strip()
        if not key:
            continue
        if value.startswith(("\"", "'")) and value.endswith(("\"", "'")) and len(value) >= 2:
            value = value[1:-1]
        if value:
            meta[key] = value
    return meta


def _format_front_matter_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)

    text = str(value)
    if text == "":
        return '""'

    plain_pattern = re.compile(r"^[A-Za-z0-9_@./:+%?&=#, -]+$")
    needs_quotes = (
        text != text.strip()
        or "\n" in text
        or '"' in text
        or "\\" in text
        or bool(re.search(r":\s|\s#", text))
        or text.startswith(("-", "{", "}", "[", "]", "&", "*", "!", "|", ">", "%", "@", "`"))
        or text.lower() in {"true", "false", "null", "yes", "no", "on", "off"}
        or not plain_pattern.match(text)
    )
    if not needs_quotes:
        return text

    escaped = (
        text.replace("\\", "\\\\")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace('"', '\\"')
    )
    return f'"{escaped}"'


def _serialize_front_matter(meta: Mapping[str, object]) -> str:
    lines = ["---"]
    for key, value in meta.items():
        if value is None:
            continue
        lines.append(f"{key}: {_format_front_matter_value(value)}")
    lines.append("---")
    return "\n".join(lines)


def front_matter_block(meta: Mapping[str, object]) -> str:
    """Serialize a YAML front matter block followed by one blank line."""
    return _serialize_front_matter(meta) + "\n\n"


def _front_matter_bounds(md_text: str) -> tuple[dict[str, str], list[str], str] | None:
    lines = md_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    front_lines: list[str] = []
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            body = "\n".join(lines[idx + 1 :])
            if md_text.endswith("\n") and not body.endswith("\n"):
                body += "\n"
            return _parse_front_matter(front_lines), front_lines, body
        front_lines.append(lines[idx])
    return None


def _line_key(line: str) -> str:
    match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_-]*)\s*:", line)
    return match.group(1) if match else ""


def remove_front_matter_keys(md_text: str, keys: set[str] | frozenset[str]) -> str:
    """Remove selected top-level front matter keys, including YAML continuation lines."""
    if not keys:
        return md_text

    bounds = _front_matter_bounds(md_text)
    if bounds is None:
        return md_text

    _, front_lines, body = bounds
    filtered_lines: list[str] = []
    index = 0

    while index < len(front_lines):
        line = front_lines[index]
        key = _line_key(line)
        if key and key in keys:
            index += 1
            while index < len(front_lines):
                next_line = front_lines[index]
                next_key = _line_key(next_line)
                if next_key:
                    break
                if next_line.startswith((" ", "\t")) or next_line.strip() == "":
                    index += 1
                    continue
                break
            continue

        filtered_lines.append(line)
        index += 1

    front = "\n".join(["---", *filtered_lines, "---"])
    return f"{front}\n\n{body.lstrip()}"


def upsert_front_matter(
    md_text: str,
    values: Mapping[str, object],
    *,
    defaults: Mapping[str, object] | None = None,
) -> str:
    """Insert or update leading YAML front matter while preserving key order."""
    bounds = _front_matter_bounds(md_text)
    if bounds is None:
        front_lines: list[str] = []
        parsed: dict[str, str] = {}
        body = md_text.lstrip("\n")
    else:
        parsed, front_lines, body = bounds

    defaults = defaults or {}
    applied: set[str] = set()
    new_front_lines: list[str] = []

    for line in front_lines:
        key = _line_key(line)
        if key in values and values[key] not in (None, ""):
            new_front_lines.append(f"{key}: {_format_front_matter_value(values[key])}")
            applied.add(key)
            continue
        if (
            key in defaults
            and defaults[key] not in (None, "")
            and str(parsed.get(key, "")).strip() == ""
        ):
            new_front_lines.append(f"{key}: {_format_front_matter_value(defaults[key])}")
            applied.add(key)
            continue
        if key:
            applied.add(key)
        new_front_lines.append(line)

    for mapping, overwrite in ((defaults, False), (values, True)):
        for key, value in mapping.items():
            if value is None or value == "":
                continue
            if key in applied:
                continue
            if not overwrite and str(parsed.get(key, "")).strip() != "":
                continue
            new_front_lines.append(f"{key}: {_format_front_matter_value(value)}")
            applied.add(key)

    front = "\n".join(["---", *new_front_lines, "---"])
    return f"{front}\n\n{body.lstrip()}"


def extract_markdown_title(md_text: str) -> str:
    """Return the first H1 title from Markdown text, ignoring front matter."""
    _, body = split_front_matter(md_text)
    for line in body.splitlines():
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            return match.group(1).strip()
    return ""


def markdown_body_stats(md_text: str) -> dict[str, int]:
    """Return simple body-only stats suitable for front matter."""
    _, body = split_front_matter(md_text)
    words = re.findall(r"\w+", body, flags=re.UNICODE)
    return {
        "docflow_body_chars": len(body.strip()),
        "docflow_word_count": len(words),
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def infer_source_type(meta: Mapping[str, str], source_url: str | None = None) -> str:
    source = str(meta.get("source", "")).strip().lower()
    if source in {"tweet", "podcast", "instapaper"}:
        return source
    candidate = source_url or str(meta.get("source_url", "")).strip() or source
    if candidate.startswith(("http://", "https://")):
        return "web"
    return "markdown"


def enrich_markdown_metadata(
    md_text: str,
    *,
    source_url: str | None = None,
    title: str | None = None,
    extra: Mapping[str, object] | None = None,
    now: str | None = None,
) -> str:
    """Add canonical docflow metadata and drop imported fields Docflow does not use."""
    md_text = remove_front_matter_keys(md_text, _REMOVED_IMPORTED_FRONT_MATTER_KEYS)
    meta, _ = split_front_matter(md_text)
    candidate_source = str(meta.get("source", "")).strip()
    effective_source_url = source_url
    if not effective_source_url and candidate_source.startswith(("http://", "https://")):
        effective_source_url = candidate_source

    defaults: dict[str, object] = {
        "title": title or extract_markdown_title(md_text),
        "source_url": effective_source_url or "",
        "docflow_source_type": infer_source_type(meta, effective_source_url),
        "docflow_ingested_at": now or utc_now_iso(),
    }
    values: dict[str, object] = {}
    values.update(markdown_body_stats(md_text))
    if extra:
        values.update(extra)

    return upsert_front_matter(md_text, values, defaults=defaults)


def front_matter_meta_tags(meta: dict[str, str]) -> str:
    tags: list[str] = []
    for key, meta_name in _FRONT_MATTER_KEYS.items():
        if key not in meta:
            continue
        value = html.escape(str(meta[key]), quote=True)
        tags.append(f'<meta name="{meta_name}" content="{value}">')
    return "\n".join(tags) + ("\n" if tags else "")


def _relative_docflow_path(path: Path, base_dir: Path | None) -> str:
    candidate = Path(path)
    if base_dir is None:
        return candidate.as_posix()
    try:
        return candidate.resolve().relative_to(Path(base_dir).resolve()).as_posix()
    except ValueError:
        return candidate.as_posix()


def update_html_meta_tags(html_path: Path, meta: Mapping[str, object]) -> None:
    """Upsert supported docflow metadata tags into an HTML document."""
    from bs4 import BeautifulSoup

    html_text = html_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html_text, "html.parser")

    if soup.html is None:
        html_tag = soup.new_tag("html")
        html_tag.extend(list(soup.contents))
        soup.clear()
        soup.append(html_tag)

    head = soup.head
    if head is None:
        head = soup.new_tag("head")
        soup.html.insert(0, head)

    for key, meta_name in _FRONT_MATTER_KEYS.items():
        if key not in meta or meta[key] in (None, ""):
            continue
        tags = head.find_all("meta", attrs={"name": meta_name})
        tag = tags[0] if tags else soup.new_tag("meta")
        tag["name"] = meta_name
        tag["content"] = str(meta[key])
        if not tags:
            head.append(tag)
        for duplicate in tags[1:]:
            duplicate.decompose()

    output_html = str(soup).replace("<br/>", "<br>").replace("<br />", "<br>")
    html_path.write_text(output_html, encoding="utf-8")


def sync_markdown_html_pair_metadata(
    md_path: Path,
    html_path: Path,
    *,
    base_dir: Path | None = None,
) -> None:
    """Store reciprocal Markdown/HTML identity metadata in both files."""
    if not md_path.exists() or not html_path.exists():
        return

    md_text = md_path.read_text(encoding="utf-8", errors="replace")
    meta, _ = split_front_matter(md_text)
    docflow_id = (meta.get("docflow_id") or "").strip() or str(uuid4())
    relation_meta = {
        "docflow_id": docflow_id,
        "docflow_markdown_path": _relative_docflow_path(md_path, base_dir),
        "docflow_html_path": _relative_docflow_path(html_path, base_dir),
        "docflow_render_status": "paired_html",
    }

    updated_md = upsert_front_matter(md_text, relation_meta)
    if updated_md != md_text:
        md_path.write_text(updated_md, encoding="utf-8")
        meta, _ = split_front_matter(updated_md)
    else:
        meta = {**meta, **relation_meta}

    update_html_meta_tags(html_path, meta)


def sync_markdown_only_metadata(
    md_path: Path,
    *,
    base_dir: Path | None = None,
) -> None:
    """Store identity metadata for Markdown files without an associated HTML file."""
    if not md_path.exists():
        return

    md_text = md_path.read_text(encoding="utf-8", errors="replace")
    meta, _ = split_front_matter(md_text)
    docflow_id = (meta.get("docflow_id") or "").strip() or str(uuid4())
    markdown_meta = {
        "docflow_id": docflow_id,
        "docflow_markdown_path": _relative_docflow_path(md_path, base_dir),
        "docflow_render_status": "markdown_only",
    }

    updated_md = upsert_front_matter(md_text, markdown_meta)
    if updated_md != md_text:
        md_path.write_text(updated_md, encoding="utf-8")


def update_markdown_docflow_last_read(
    md_path: Path,
    docflow_last_read: str,
    *,
    html_path: Path | None = None,
) -> bool:
    """Update docflow_last_read in Markdown and mirror it to associated HTML meta tags."""
    if not md_path.exists() or not str(docflow_last_read).strip():
        return False

    md_text = md_path.read_text(encoding="utf-8", errors="replace")
    updated_md = upsert_front_matter(md_text, {"docflow_last_read": docflow_last_read})
    changed = updated_md != md_text
    if changed:
        md_path.write_text(updated_md, encoding="utf-8")

    target_html = html_path if html_path is not None else md_path.with_suffix(".html")
    if target_html.exists():
        meta, _ = split_front_matter(updated_md if changed else md_text)
        original_html_stat = target_html.stat()
        update_html_meta_tags(target_html, meta)
        os.utime(target_html, (original_html_stat.st_atime, original_html_stat.st_mtime))

    return changed


def sync_markdown_html_pairs_metadata(
    paths: list[Path],
    *,
    base_dir: Path | None = None,
) -> None:
    """Sync reciprocal metadata for every Markdown/HTML pair in a path list."""
    by_stem: dict[tuple[Path, str], dict[str, Path]] = {}
    for raw_path in paths:
        path = Path(raw_path)
        suffix = path.suffix.lower()
        if suffix not in {".md", ".html", ".htm"}:
            continue
        group = by_stem.setdefault((path.parent, path.stem), {})
        if suffix == ".md":
            group["md"] = path
        elif suffix in {".html", ".htm"}:
            group["html"] = path

    for group in by_stem.values():
        md_path = group.get("md")
        html_path = group.get("html")
        if md_path and html_path:
            sync_markdown_html_pair_metadata(md_path, html_path, base_dir=base_dir)


def original_source_link_html(meta: dict[str, str]) -> str:
    """Render a visible original-source link for external clipped articles."""
    source = (meta.get("source_url") or meta.get("source", "")).strip()
    if not source.startswith(("http://", "https://")):
        return ""

    escaped_source = html.escape(source, quote=True)
    return (
        '<p class="docflow-original-link">'
        f'Original link: <a href="{escaped_source}" target="_blank" '
        f'rel="noopener">{escaped_source}</a>'
        "</p>\n"
    )


def clean_duplicate_markdown_links(text: str) -> str:
    """Clean Markdown links where the text and URL are identical."""
    duplicate_link_pattern = r'\[(https?://[^\]]+)\]\(\1\)'

    def replace_duplicate_link(match):
        url = match.group(1)
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc
            path = parsed.path
            if len(path) > 30:
                path = path[:27] + "..."
            display_text = f"{domain}{path}"
            return f'[{display_text}]({url})'
        except Exception:
            return f'[View link]({url})'

    return re.sub(duplicate_link_pattern, replace_duplicate_link, text)


def _raw_html_block_end_tag(line: str) -> str:
    match = re.match(r"^\s*<([A-Za-z][A-Za-z0-9:-]*)\b", line)
    if not match:
        return ""
    tag_name = match.group(1).lower()
    if tag_name not in {"iframe", "script", "style"}:
        return ""
    end_tag = f"</{tag_name}>"
    return "" if end_tag in line.lower() else end_tag


def _position_inside_markdown_link(line: str, position: int) -> bool:
    patterns = (
        r"\[!\[[^\]]*\]\([^)]+\)\]\([^)]+\)",
        r"!\[[^\]]*\]\([^)]+\)",
        r"\[[^\]]+\]\([^)]+\)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, line):
            if match.start() <= position < match.end():
                return True
    return False


def _fenced_code_marker(line: str) -> str:
    match = re.match(r"^\s*(`{3,}|~{3,})", line)
    if not match:
        return ""
    return match.group(1)[0]


def _closes_fenced_code(line: str, marker: str) -> bool:
    return bool(marker and re.match(rf"^\s*{re.escape(marker)}{{3,}}\s*$", line))


def convert_urls_to_links(text: str) -> str:
    """Convert plain-text URLs to Markdown links robustly."""
    text = clean_duplicate_markdown_links(text)

    lines = text.split('\n')
    processed_lines = []
    raw_html_end_tag = ""
    fenced_code_marker = ""

    for line in lines:
        if fenced_code_marker:
            processed_lines.append(line)
            if _closes_fenced_code(line, fenced_code_marker):
                fenced_code_marker = ""
            continue

        marker = _fenced_code_marker(line)
        if marker:
            fenced_code_marker = marker
            processed_lines.append(line)
            continue

        if raw_html_end_tag:
            processed_lines.append(line)
            if raw_html_end_tag in line.lower():
                raw_html_end_tag = ""
            continue

        raw_html_end_tag = _raw_html_block_end_tag(line)
        if raw_html_end_tag:
            processed_lines.append(line)
            continue

        if 'http' in line:
            url_pattern = r'https?://[^\s\)\]>"\']+'
            matches = list(re.finditer(url_pattern, line))

            for match in reversed(matches):
                url = match.group()
                start_pos = match.start()

                prefix = line[:start_pos].lower()

                prefix_lines = prefix.split('\n')
                is_in_markdown_link = (
                    ('](' in prefix_lines[-1] if prefix_lines else False)
                    or _position_inside_markdown_link(line, start_pos)
                )

                prefix_words = prefix.split()
                last_word = prefix_words[-1] if prefix_words else ""
                is_in_html_attribute = any(attr in last_word for attr in [
                    'href=', 'src=', 'srcset=', 'poster=', 'data-src=', 'action=', 'cite='
                ])
                is_in_css_url = 'url(' in last_word

                if not (is_in_markdown_link or is_in_html_attribute or is_in_css_url):
                    line = line[:start_pos] + f'[{url}]({url})' + line[match.end():]

        processed_lines.append(line)

    return '\n'.join(processed_lines)


_BLOCK_LINK_CLOSE_RE = re.compile(r"^\]\((https?://[^)]+)\)(.*)$")
_X_STATUS_LINK_CLOSE_RE = re.compile(
    r"^(?P<body>.*)\]\((?P<url>https?://(?:www\.)?(?:x|twitter)\.com/[^)]+/status/[^)]+)\)(?P<trailing>.*)$",
    flags=re.IGNORECASE,
)
_X_IMAGE_LINK_RE = re.compile(
    r"^\[!\[[^\]]*\]\((?P<img>https?://[^)]+)\)\]\((?P<url>https?://(?:www\.)?(?:x|twitter)\.com/[^)]+/status/[^)]+)\)\s*$",
    flags=re.IGNORECASE,
)
_YOUTUBE_IMAGE_RE = re.compile(
    r"^!\[[^\]]*\]\((?P<url>https?://(?:www\.)?(?:youtube\.com/watch|youtu\.be/)[^)]+)\)\s*$",
    flags=re.IGNORECASE,
)
_TIKTOK_IFRAME_RE = re.compile(
    r"<iframe\b[^>]*(?:tiktok|iframe\.ly)[^>]*>\s*</iframe>",
    flags=re.IGNORECASE,
)
_THIRD_PARTY_COOKIE_IFRAME_RE = re.compile(
    r"<iframe\b[^>]*third-party-cookie-check-iframe[^>]*>\s*</iframe>",
    flags=re.IGNORECASE,
)
_TIKTOK_IMAGE_LINK_RE = re.compile(
    r"^\[!\[[^\]]*\]\((?P<img>https?://[^)]+)\)\]\((?P<url>https?://(?:www\.)?tiktok\.com/[^)]+)\)\s*$",
    flags=re.IGNORECASE,
)
_TIKTOK_AUTHOR_LINK_RE = re.compile(
    r"^\[(?P<label>@[^\]]+)\]\((?P<profile>https?://(?:www\.)?tiktok\.com/[^)]+)\)",
    flags=re.IGNORECASE,
)
_READ_MORE_LABELS = {"read full story", "read more", "continue reading"}


def _embedded_link_label(url: str) -> str:
    lower = url.lower()
    if "x.com/" in lower or "twitter.com/" in lower:
        return "View on X"
    if "tiktok.com/" in lower:
        return "View on TikTok"
    if "youtube.com/" in lower or "youtu.be/" in lower:
        return "View on YouTube"
    if "monosestocasticos.com/" in lower or "substack.com/" in lower:
        return "Read full story"
    return "View embedded item"


def _is_substack_profile_url(url: str) -> bool:
    return bool(re.search(r"https?://(?:www\.)?substack\.com/@", url, flags=re.IGNORECASE))


def _is_image_only_block(lines: list[str]) -> bool:
    content = [line.strip() for line in lines if line.strip()]
    return bool(content) and all(line.startswith("![") for line in content)


def _find_block_link_close(lines: list[str], open_idx: int) -> tuple[int, str, str] | None:
    depth = 1
    idx = open_idx + 1
    while idx < len(lines):
        stripped = lines[idx].strip()
        if stripped == "[":
            depth += 1
        else:
            close_match = _BLOCK_LINK_CLOSE_RE.match(stripped)
            if close_match:
                depth -= 1
                if depth == 0:
                    return idx, close_match.group(1), close_match.group(2).strip()
        idx += 1
    return None


def _is_multiline_x_embed_start(line: str) -> bool:
    stripped = line.lstrip()
    if not stripped.startswith("[!["):
        return False
    return not re.match(r"^\[!\[[^\]]*\]\([^)]+\)\]\(", stripped)


def _strip_multiline_embed_open(line: str) -> str:
    return re.sub(r"^(\s*)\[!", r"\1!", line, count=1)


def normalize_multiline_x_embeds(text: str) -> str:
    """Collapse old multiline Substack/X captures into compact local cards."""
    lines = text.splitlines()
    output: list[str] = []
    idx = 0

    while idx < len(lines):
        image_link_match = _X_IMAGE_LINK_RE.match(lines[idx].strip())
        if image_link_match:
            output.append('<div class="docflow-embed" markdown="1">')
            output.append(f"![]({image_link_match.group('img')})")
            output.append("")
            output.append(
                f"[{_embedded_link_label(image_link_match.group('url'))}]"
                f"({image_link_match.group('url')}){{ .docflow-embed-source }}"
            )
            output.append("</div>")
            idx += 1
            continue

        if not _is_multiline_x_embed_start(lines[idx]):
            output.append(lines[idx])
            idx += 1
            continue

        close_idx = -1
        close_match = None
        for scan_idx in range(idx + 1, len(lines)):
            match = _X_STATUS_LINK_CLOSE_RE.match(lines[scan_idx].strip())
            if match:
                close_idx = scan_idx
                close_match = match
                break
            if lines[scan_idx].startswith("# "):
                break

        if close_match is None:
            output.append(lines[idx])
            idx += 1
            continue

        url = close_match.group("url")
        final_body = close_match.group("body").rstrip()
        trailing = close_match.group("trailing").strip()
        content = lines[idx:close_idx]
        content[0] = _strip_multiline_embed_open(content[0])
        if final_body:
            content.append(final_body)

        output.append('<div class="docflow-embed" markdown="1">')
        output.extend(content)
        output.append("")
        output.append(f"[{_embedded_link_label(url)}]({url}){{ .docflow-embed-source }}")
        output.append("</div>")
        if trailing:
            lines.insert(close_idx + 1, trailing)
        idx = close_idx + 1

    result = "\n".join(output)
    if text.endswith("\n"):
        result += "\n"
    return result


def normalize_youtube_image_links(text: str) -> str:
    """Turn clipped YouTube image syntax into a normal video link card."""
    lines = text.splitlines()
    output: list[str] = []
    for line in lines:
        match = _YOUTUBE_IMAGE_RE.match(line.strip())
        if not match:
            output.append(line)
            continue
        url = match.group("url")
        output.append('<div class="docflow-embed" markdown="1">')
        output.append(f"[{_embedded_link_label(url)}]({url}){{ .docflow-embed-source }}")
        output.append("</div>")

    result = "\n".join(output)
    if text.endswith("\n"):
        result += "\n"
    return result


def _collapse_nested_block_links(lines: list[str], outer_url: str) -> list[str]:
    collapsed: list[str] = []
    idx = 0
    while idx < len(lines):
        if lines[idx].strip() != "[":
            collapsed.append(lines[idx])
            idx += 1
            continue

        close = _find_block_link_close(lines, idx)
        if close is None:
            collapsed.append(lines[idx])
            idx += 1
            continue

        close_idx, url, trailing = close
        body = lines[idx + 1 : close_idx]
        body_text = " ".join(line.strip() for line in body if line.strip())
        normalized_text = body_text.lower()
        if url == outer_url and normalized_text in _READ_MORE_LABELS:
            if trailing:
                collapsed.append(trailing)
            idx = close_idx + 1
            continue
        if body_text and not any(line.lstrip().startswith(("!", "#", "<")) for line in body):
            collapsed.append(f"[{body_text}]({url})")
            if trailing:
                collapsed.append(trailing)
            idx = close_idx + 1
            continue

        collapsed.extend(lines[idx : close_idx + 1])
        if trailing:
            collapsed.append(trailing)
        idx = close_idx + 1

    return collapsed


def normalize_markdown_block_links(text: str) -> str:
    """Convert Substack-style block links into parseable Markdown embed blocks."""
    lines = text.splitlines()
    output: list[str] = []
    idx = 0

    while idx < len(lines):
        if lines[idx].strip() != "[":
            output.append(lines[idx])
            idx += 1
            continue

        close = _find_block_link_close(lines, idx)
        if close is None:
            output.append(lines[idx])
            idx += 1
            continue

        close_idx, url, trailing = close
        content = lines[idx + 1 : close_idx]
        if not any(line.strip() for line in content):
            if trailing:
                lines.insert(close_idx + 1, trailing)
            idx = close_idx + 1
            continue

        if _is_substack_profile_url(url) and _is_image_only_block(content):
            if trailing:
                lines.insert(close_idx + 1, trailing)
            idx = close_idx + 1
            continue

        label = _embedded_link_label(url)
        output.append('<div class="docflow-embed" markdown="1">')
        output.extend(_collapse_nested_block_links(content, url))
        output.append("")
        output.append(f"[{label}]({url}){{ .docflow-embed-source }}")
        output.append("</div>")
        if trailing:
            lines.insert(close_idx + 1, trailing)
        idx = close_idx + 1

    result = "\n".join(output)
    if text.endswith("\n"):
        result += "\n"
    return result


def strip_unstable_embed_artifacts(text: str) -> str:
    """Remove third-party embed chrome that renders poorly in local archived pages."""
    text = _THIRD_PARTY_COOKIE_IFRAME_RE.sub("", text)
    text = _TIKTOK_IFRAME_RE.sub("", text)

    cleaned_lines: list[str] = []
    skip_next_cookie_hint = False
    for line in text.splitlines():
        lowered = line.lower()
        if "tiktok failed to load" in lowered:
            skip_next_cookie_hint = True
            continue
        if "3rd party cookies" in lowered:
            skip_next_cookie_hint = False
            continue
        skip_next_cookie_hint = False
        cleaned_lines.append(line)

    result = "\n".join(cleaned_lines)
    if text.endswith("\n"):
        result += "\n"
    return result


def normalize_tiktok_fallbacks(text: str) -> str:
    """Collapse TikTok fallback captures into compact local cards."""
    lines = text.splitlines()
    output: list[str] = []
    idx = 0

    while idx < len(lines):
        image_match = _TIKTOK_IMAGE_LINK_RE.match(lines[idx].strip())
        if not image_match:
            output.append(lines[idx])
            idx += 1
            continue

        image_line = lines[idx].strip()
        tiktok_url = image_match.group("url")
        next_idx = idx + 1
        while next_idx < len(lines) and not lines[next_idx].strip():
            next_idx += 1

        author_line = ""
        if next_idx < len(lines) and tiktok_url in lines[next_idx]:
            author_match = _TIKTOK_AUTHOR_LINK_RE.match(lines[next_idx].strip())
            if author_match:
                label = author_match.group("label")
                profile = author_match.group("profile")
                author_line = f"[{label}]({profile})"
            next_idx += 1

        output.append('<div class="docflow-embed docflow-embed-tiktok" markdown="1">')
        output.append(image_line)
        if author_line:
            output.append("")
            output.append(author_line)
        output.append("")
        output.append(f"[{_embedded_link_label(tiktok_url)}]({tiktok_url}){{ .docflow-embed-source }}")
        output.append("</div>")
        idx = next_idx

    result = "\n".join(output)
    if text.endswith("\n"):
        result += "\n"
    return result


_X_HANDLE_LINE_RE = re.compile(r"^@[A-Za-z0-9_]{1,20}$")
_X_HANDLE_LINE_END_RE = re.compile(r"@[A-Za-z0-9_]{1,20}$")
_X_HANDLE_CONTINUATION_RE = re.compile(r"^[,;:!?]\s*(?:and|or|y|e)$", re.IGNORECASE)
_X_HANDLE_INLINE_CONTINUATION_RE = re.compile(r"^(?:and|or|y|e)\s+@[A-Za-z0-9_]{1,20}\b", re.IGNORECASE)


def normalize_x_handle_linebreaks(content: str) -> str:
    """Keep standalone X handles inline with their following text."""
    lines = content.split("\n")
    if len(lines) < 2:
        return content

    output: list[str] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()
        is_standalone_handle = bool(_X_HANDLE_LINE_RE.fullmatch(stripped))
        if not is_standalone_handle:
            next_text = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
            if not (
                _X_HANDLE_LINE_END_RE.search(stripped)
                and next_text
                and (
                    next_text[0] in ",.;:!?"
                    or next_text[0] == "·"
                    or _X_HANDLE_LINE_RE.fullmatch(next_text)
                    or _X_HANDLE_INLINE_CONTINUATION_RE.match(next_text)
                )
            ):
                output.append(line)
                idx += 1
                continue

        if not stripped:
            output.append(line)
            idx += 1
            continue

        combined = line.rstrip()
        idx += 1
        while idx < len(lines):
            next_line = lines[idx]
            next_text = next_line.strip()
            if not next_text:
                break
            if next_text.startswith("<"):
                break

            first_char = next_text[0]
            if first_char in ",.;:!?":
                combined += next_text
                idx += 1
                if _X_HANDLE_CONTINUATION_RE.fullmatch(next_text):
                    continue
                if len(next_text) > 1:
                    break
                continue
            if first_char == "·":
                combined += " " + next_text
                idx += 1
                if len(next_text) > 1:
                    break
                continue
            if _X_HANDLE_LINE_RE.fullmatch(next_text):
                combined += " " + next_text
                idx += 1
                continue
            if _X_HANDLE_INLINE_CONTINUATION_RE.match(next_text):
                combined += " " + next_text
                idx += 1
                break

            combined += " " + next_text
            idx += 1
            break

        output.append(combined)

    return "\n".join(output)


def convert_newlines_to_br(html_text: str) -> str:
    """
    Convert single line breaks to <br> elements, but only inside content,
    not between HTML block elements.
    """
    def replace_in_content(match):
        tag_open = match.group(1)
        content = match.group(2)
        tag_close = match.group(3)
        if "docflow-embed" in tag_open:
            return match.group(0)

        content = normalize_x_handle_linebreaks(content)
        content_with_br = content.replace('\n', '<br>\n')

        return f"{tag_open}{content_with_br}{tag_close}"

    html_text = re.sub(r'(<p\b[^>]*>)(.*?)(</p>)', replace_in_content, html_text, flags=re.DOTALL)
    return re.sub(r'(<div\b[^>]*>)(.*?)(</div>)', replace_in_content, html_text, flags=re.DOTALL)


def markdown_to_html(md_text: str, title: str = None) -> str:
    """
    Convert Markdown text to full HTML with cleanup and clickable URLs.
    """
    import markdown

    md_text = md_text.replace('\xa0', ' ')
    front_matter, md_body = split_front_matter(md_text)
    md_body = strip_unstable_embed_artifacts(md_body)
    md_body = normalize_tiktok_fallbacks(md_body)
    md_body = normalize_youtube_image_links(md_body)
    md_body = normalize_multiline_x_embeds(md_body)
    md_body = normalize_markdown_block_links(md_body)
    md_body = convert_urls_to_links(md_body)

    try:
        html_body = markdown.markdown(
            md_body,
            extensions=[
                "fenced_code",
                "tables",
                "toc",
                "attr_list",
                "md_in_html",
                "def_list",
            ],
            output_format="html5",
        )
    except Exception as e:
        print(f"⚠️  Error converting markdown, trying without extensions: {e}")
        html_body = markdown.markdown(md_body, output_format="html5")

    html_body = convert_newlines_to_br(html_body)

    title_tag = f"<title>{title}</title>\n" if title else ""
    meta_tags = front_matter_meta_tags(front_matter)
    original_link = original_source_link_html(front_matter)
    return (
        "<!DOCTYPE html>\n"
        "<html>\n<head>\n<meta charset=\"UTF-8\">\n"
        f"{meta_tags}"
        f"{title_tag}"
        "</head>\n<body>\n"
        f"{original_link}"
        f"{html_body}\n"
        "</body>\n</html>\n"
    )


def extract_html_body(html: str) -> str:
    """Extract content inside the <body> tag."""
    body = re.search(r"<body>(.*)</body>", html, re.DOTALL | re.IGNORECASE)
    return body.group(1).strip() if body else html


def markdown_to_html_body(md_text: str, title: str = None) -> str:
    """Convert Markdown to HTML and return only the <body> content."""
    return extract_html_body(markdown_to_html(md_text, title))
