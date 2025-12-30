from pathlib import Path

from utils.file_ops import iter_html_files


def add_margins_to_html_files(directory: Path, file_filter=None):
    """
    Add 6% margins to all HTML files in a directory.

    Args:
        directory: Directory where HTML files are searched
        file_filter: Optional function to filter which files to process (e.g., is_podcast_file)
    """
    from bs4 import BeautifulSoup

    margin_style = "body { margin-left: 6%; margin-right: 6%; }"
    img_rule = "img { max-width: 300px; height: auto; cursor: zoom-in; }"

    html_files = [
        file_path for file_path in iter_html_files(directory, file_filter)
    ]

    if not html_files:
        print('📏 No hay archivos HTML para añadir márgenes')
        return

    for html_file in html_files:
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f, 'html.parser')

            for img in soup.find_all("img"):
                src = img.get("src")
                if not src:
                    continue
                parent = img.parent
                if parent and parent.name == "a" and parent.get("href") == src:
                    continue
                link = soup.new_tag("a", href=src, target="_blank", rel="noopener")
                img.replace_with(link)
                link.append(img)

            head = soup.head
            if head is None:
                head = soup.new_tag("head")
                style_tag = soup.new_tag("style")
                style_tag.string = margin_style + "\n" + img_rule
                head.append(style_tag)
                if soup.html:
                    soup.html.insert(0, head)
            else:
                style_tag = head.find("style")
                if style_tag:
                    existing = style_tag.string or ""
                    if margin_style not in existing:
                        style_tag.string = (existing + ("\n" if existing else "") + margin_style)
                        existing = style_tag.string
                    if img_rule not in (style_tag.string or ""):
                        style_tag.string += "\n" + img_rule
                else:
                    style_tag = soup.new_tag("style")
                    style_tag.string = margin_style + "\n" + img_rule
                    head.append(style_tag)

            output_html = str(soup)
            output_html = output_html.replace("<br/>", "<br>").replace("<br />", "<br>")
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(output_html)
            print(f"📏 Márgenes añadidos: {html_file.name}")

        except Exception as e:
            print(f"❌ Error añadiendo márgenes a {html_file}: {e}")


def get_base_css() -> str:
    """Return base CSS with the system font and common styles."""
    return (
        "body { margin: 6%; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }\n"
        "h1, h2, h3 { font-weight: bold; border-bottom: 1px solid #eee; padding-bottom: 10px; }\n"
        "blockquote { margin-left: 0; padding-left: 20px; color: #666; }\n"
        "a { text-decoration: none; }\n"
        "a:hover { text-decoration: underline; }\n"
        "hr { border: none; border-top: 1px solid #eee; margin: 30px 0; }\n"
    )


def get_article_js_script_tag() -> str:
    """Deprecated: JS injection happens when publishing to /read/."""
    return ""


def wrap_html(title: str, body: str, accent_color: str) -> str:
    """Wrap content in minimal HTML with base styles and an accent color."""
    return (
        "<!DOCTYPE html>\n"
        "<html>\n<head>\n<meta charset=\"UTF-8\">\n"
        f"<title>{title}</title>\n"
        "<style>\n"
        f"{get_base_css()}"
        f"blockquote {{ border-left: 4px solid {accent_color}; }}\n"
        f"a {{ color: {accent_color}; }}\n"
        "</style>\n"
        ""
        "</head>\n<body>\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )
