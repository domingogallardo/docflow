import re
import html


_FRONT_MATTER_KEYS = {
    "source": "docflow-source",
    "tweet_url": "docflow-tweet-url",
    "tweet_author": "docflow-tweet-author",
    "tweet_author_name": "docflow-tweet-author-name",
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


def front_matter_meta_tags(meta: dict[str, str]) -> str:
    tags: list[str] = []
    for key, meta_name in _FRONT_MATTER_KEYS.items():
        if key not in meta:
            continue
        value = html.escape(str(meta[key]), quote=True)
        tags.append(f'<meta name="{meta_name}" content="{value}">')
    return "\n".join(tags) + ("\n" if tags else "")


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

    html_text = re.sub(r'(<p[^>]*>)(.*?)(</p>)', replace_in_content, html_text, flags=re.DOTALL)
    html_text = re.sub(r'(<li[^>]*>)(.*?)(</li>)', replace_in_content, html_text, flags=re.DOTALL)
    return re.sub(r'(<div[^>]*>)(.*?)(</div>)', replace_in_content, html_text, flags=re.DOTALL)


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
    return (
        "<!DOCTYPE html>\n"
        "<html>\n<head>\n<meta charset=\"UTF-8\">\n"
        f"{meta_tags}"
        f"{title_tag}"
        "</head>\n<body>\n"
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
