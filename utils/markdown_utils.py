import re
import html
from datetime import datetime, timezone
from typing import Mapping


_FRONT_MATTER_KEYS = {
    "source": "docflow-source",
    "source_url": "docflow-source-url",
    "source_name": "docflow-source-name",
    "title": "docflow-title",
    "docflow_source_type": "docflow-source-type",
    "docflow_ingested_at": "docflow-ingested-at",
    "docflow_extractor": "docflow-extractor",
    "docflow_extraction_attempt": "docflow-extraction-attempt",
    "docflow_final_url": "docflow-final-url",
    "docflow_original_url": "docflow-original-url",
    "docflow_word_count": "docflow-word-count",
    "docflow_body_chars": "docflow-body-chars",
    "instapaper_id": "docflow-instapaper-id",
    "tweet_url": "docflow-tweet-url",
    "tweet_id": "docflow-tweet-id",
    "tweet_author": "docflow-tweet-author",
    "tweet_author_name": "docflow-tweet-author-name",
    "tweet_capture_source": "docflow-tweet-capture-source",
    "tweet_posted_kind": "docflow-tweet-posted-kind",
    "tweet_thread": "docflow-tweet-thread",
    "tweet_thread_count": "docflow-tweet-thread-count",
}


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
        or text.startswith(("-", "{", "}", "[", "]", "&", "*", "!", "|", ">", "%", "@", "`"))
        or text.lower() in {"true", "false", "null", "yes", "no", "on", "off"}
        or not plain_pattern.match(text)
    )
    if not needs_quotes:
        return text

    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _serialize_front_matter(meta: Mapping[str, object]) -> str:
    lines = ["---"]
    for key, value in meta.items():
        if value is None:
            continue
        lines.append(f"{key}: {_format_front_matter_value(value)}")
    lines.append("---")
    return "\n".join(lines)


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


def upsert_front_matter(
    md_text: str,
    values: Mapping[str, object],
    *,
    defaults: Mapping[str, object] | None = None,
) -> str:
    """Insert or update leading YAML front matter while preserving key order."""
    bounds = _front_matter_bounds(md_text)
    if bounds is None:
        meta: dict[str, object] = {}
        body = md_text.lstrip("\n")
    else:
        parsed, front_lines, body = bounds
        meta = dict(parsed)
        for line in front_lines:
            if ":" not in line:
                continue
            key = line.split(":", 1)[0].strip()
            if key and key not in meta:
                meta[key] = ""

    for mapping, overwrite in ((defaults or {}, False), (values, True)):
        for key, value in mapping.items():
            if value is None or value == "":
                continue
            if not overwrite and key in meta and str(meta[key]).strip() != "":
                continue
            meta[key] = value

    front = _serialize_front_matter(meta)
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
    """Add canonical docflow metadata without removing existing source fields."""
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


def convert_urls_to_links(text: str) -> str:
    """Convert plain-text URLs to Markdown links robustly."""
    text = clean_duplicate_markdown_links(text)

    lines = text.split('\n')
    processed_lines = []

    for line in lines:
        if 'http' in line:
            url_pattern = r'https?://[^\s\)\]>"\']+'
            matches = list(re.finditer(url_pattern, line))

            for match in reversed(matches):
                url = match.group()
                start_pos = match.start()

                prefix = line[:start_pos].lower()

                prefix_lines = prefix.split('\n')
                is_in_markdown_link = '](' in prefix_lines[-1] if prefix_lines else False

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


def convert_newlines_to_br(html_text: str) -> str:
    """
    Convert single line breaks to <br> elements, but only inside content,
    not between HTML block elements.
    """
    def replace_in_content(match):
        tag_open = match.group(1)
        content = match.group(2)
        tag_close = match.group(3)

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
    md_body = convert_urls_to_links(md_body)

    try:
        html_body = markdown.markdown(
            md_body,
            extensions=[
                "fenced_code",
                "tables",
                "toc",
                "attr_list",
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
