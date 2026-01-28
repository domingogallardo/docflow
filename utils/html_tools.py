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
    viewer_css = (
        ".image-viewer-overlay { position: fixed; inset: 0; background: #111; display: none; "
        "align-items: center; justify-content: center; z-index: 9999; }\n"
        ".image-viewer-overlay.is-visible { display: flex; }\n"
        ".image-viewer-overlay img { max-width: 100%; max-height: 100%; }\n"
        "body.image-viewer-active { overflow: hidden; }\n"
    )
    viewer_script = (
        "(function(){\n"
        "  function ensureOverlay(){\n"
        "    var overlay = document.getElementById(\"image-viewer-overlay\");\n"
        "    if(!overlay){\n"
        "      overlay = document.createElement(\"div\");\n"
        "      overlay.id = \"image-viewer-overlay\";\n"
        "      overlay.className = \"image-viewer-overlay\";\n"
        "      var img = document.createElement(\"img\");\n"
        "      overlay.appendChild(img);\n"
        "      overlay.addEventListener(\"click\", function(){\n"
        "        if(history.state && history.state.imageViewer){\n"
        "          history.back();\n"
        "        }\n"
        "      });\n"
        "      document.body.appendChild(overlay);\n"
        "    }\n"
        "    return overlay;\n"
        "  }\n"
        "  function showOverlay(src, alt){\n"
        "    var overlay = ensureOverlay();\n"
        "    var img = overlay.querySelector(\"img\");\n"
        "    img.src = src;\n"
        "    img.alt = alt || \"\";\n"
        "    overlay.classList.add(\"is-visible\");\n"
        "    document.body.classList.add(\"image-viewer-active\");\n"
        "    if(!history.state || !history.state.imageViewer){\n"
        "      history.pushState({imageViewer:true}, \"\", \"#image-viewer\");\n"
        "    } else {\n"
        "      history.replaceState({imageViewer:true}, \"\", \"#image-viewer\");\n"
        "    }\n"
        "  }\n"
        "  function hideOverlay(){\n"
        "    var overlay = document.getElementById(\"image-viewer-overlay\");\n"
        "    if(!overlay){ return; }\n"
        "    overlay.classList.remove(\"is-visible\");\n"
        "    document.body.classList.remove(\"image-viewer-active\");\n"
        "  }\n"
        "  window.addEventListener(\"popstate\", function(){\n"
        "    hideOverlay();\n"
        "  });\n"
        "  document.addEventListener(\"click\", function(e){\n"
        "    var link = e.target.closest(\"a.image-zoom\");\n"
        "    if(!link){ return; }\n"
        "    var src = link.getAttribute(\"href\");\n"
        "    if(!src){ return; }\n"
        "    var img = link.querySelector(\"img\");\n"
        "    var alt = img ? (img.getAttribute(\"alt\") || \"\") : \"\";\n"
        "    e.preventDefault();\n"
        "    showOverlay(src, alt);\n"
        "  });\n"
        "})();\n"
    )

    html_files = [
        file_path for file_path in iter_html_files(directory, file_filter)
    ]

    if not html_files:
        print("📏 No HTML files to add margins to")
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
                    classes = list(parent.get("class") or [])
                    if "image-zoom" not in classes:
                        classes.append("image-zoom")
                        parent["class"] = classes
                    continue
                link = soup.new_tag("a", href=src, target="_blank", rel="noopener", class_="image-zoom")
                img.replace_with(link)
                link.append(img)

            head = soup.head
            if head is None:
                head = soup.new_tag("head")
                style_tag = soup.new_tag("style")
                style_tag.string = margin_style + "\n" + img_rule + "\n" + viewer_css
                head.append(style_tag)
                script_tag = soup.new_tag("script", id="image-viewer")
                script_tag.string = viewer_script
                head.append(script_tag)
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
                    if viewer_css not in (style_tag.string or ""):
                        style_tag.string += "\n" + viewer_css
                else:
                    style_tag = soup.new_tag("style")
                    style_tag.string = margin_style + "\n" + img_rule + "\n" + viewer_css
                    head.append(style_tag)
                script_tag = head.find("script", id="image-viewer")
                if not script_tag:
                    script_tag = soup.new_tag("script", id="image-viewer")
                    head.append(script_tag)
                script_tag.string = viewer_script

            output_html = str(soup)
            output_html = output_html.replace("<br/>", "<br>").replace("<br />", "<br>")
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(output_html)
            print(f"📏 Margins added: {html_file.name}")

        except Exception as e:
            print(f"❌ Error adding margins to {html_file}: {e}")


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


def wrap_html(title: str, body: str, accent_color: str, meta_tags: str = "") -> str:
    """Wrap content in minimal HTML with base styles and an accent color."""
    return (
        "<!DOCTYPE html>\n"
        "<html>\n<head>\n<meta charset=\"UTF-8\">\n"
        f"{meta_tags}"
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
