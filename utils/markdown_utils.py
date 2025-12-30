import re


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
            return f'[Ver enlace]({url})'

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
    html_text = re.sub(r'(<div[^>]*>)(.*?)(</div>)', replace_in_content, html_text, flags=re.DOTALL)

    return html_text


def markdown_to_html(md_text: str, title: str = None) -> str:
    """
    Convert Markdown text to full HTML with cleanup and clickable URLs.
    """
    import markdown

    md_text = md_text.replace('\xa0', ' ')
    md_text = convert_urls_to_links(md_text)

    try:
        html_body = markdown.markdown(
            md_text,
            extensions=[
                "fenced_code",
                "tables",
                "toc",
                "attr_list",
            ],
            output_format="html5",
        )
    except Exception as e:
        print(f"⚠️  Error en conversión markdown, intentando sin extensiones: {e}")
        html_body = markdown.markdown(md_text, output_format="html5")

    html_body = convert_newlines_to_br(html_body)

    title_tag = f"<title>{title}</title>\n" if title else ""
    full_html = (
        "<!DOCTYPE html>\n"
        "<html>\n<head>\n<meta charset=\"UTF-8\">\n"
        f"{title_tag}"
        "</head>\n<body>\n"
        f"{html_body}\n"
        "</body>\n</html>\n"
    )

    return full_html


def extract_html_body(html: str) -> str:
    """Extract content inside the <body> tag."""
    body = re.search(r"<body>(.*)</body>", html, re.DOTALL | re.IGNORECASE)
    return body.group(1).strip() if body else html


def markdown_to_html_body(md_text: str, title: str = None) -> str:
    """Convert Markdown to HTML and return only the <body> content."""
    return extract_html_body(markdown_to_html(md_text, title))
