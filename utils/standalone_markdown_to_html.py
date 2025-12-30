#!/usr/bin/env python3
"""Standalone command to convert Markdown to HTML without other repo modules."""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable, List, Tuple

import markdown
from bs4 import BeautifulSoup


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert Markdown files to HTML using the same transformations "
            "as the repository pipelines."
        )
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="File paths or directories with Markdown to convert",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        help="Directory to save generated HTML (default: alongside Markdown)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite HTML files if they already exist",
    )
    return parser.parse_args(argv)


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
    """Insert <br> inside paragraphs to preserve line breaks."""
    def replace_in_content(match):
        tag_open, content, tag_close = match.group(1), match.group(2), match.group(3)
        content_with_br = content.replace("\n", "<br>\n")
        return f"{tag_open}{content_with_br}{tag_close}"

    html_text = re.sub(r"(<p[^>]*>)(.*?)(</p>)", replace_in_content, html_text, flags=re.DOTALL)
    html_text = re.sub(r"(<li[^>]*>)(.*?)(</li>)", replace_in_content, html_text, flags=re.DOTALL)
    html_text = re.sub(r"(<div[^>]*>)(.*?)(</div>)", replace_in_content, html_text, flags=re.DOTALL)
    return html_text


def markdown_to_html(md_text: str, title: str) -> str:
    md_text = md_text.replace("\xa0", " ")
    md_text = convert_urls_to_links(md_text)
    html_body = markdown.markdown(
        md_text,
        extensions=["fenced_code", "tables", "toc", "attr_list"],
        output_format="html5",
    )
    html_body = convert_newlines_to_br(html_body)
    full_html = (
        "<!DOCTYPE html>\n"
        "<html>\n<head>\n<meta charset=\"UTF-8\">\n"
        f"<title>{title}</title>\n"
        "</head>\n<body>\n"
        f"{html_body}\n"
        "</body>\n</html>\n"
    )
    return full_html


def add_margins(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    margin_style = "body { margin-left: 6%; margin-right: 6%; }"
    img_rule = "img { max-width: 300px; height: auto; cursor: zoom-in; }"

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
        soup.html.insert(0, head) if soup.html else None
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
    html_out = str(soup).replace("<br/>", "<br>").replace("<br />", "<br>")
    return html_out


def collect_markdown_files(raw_paths: Iterable[str]) -> List[Path]:
    markdown_files: List[Path] = []
    for raw_path in raw_paths:
        path = Path(raw_path)
        if path.is_dir():
            markdown_files.extend(sorted(path.glob("*.md")))
            continue
        if path.suffix.lower() == ".md":
            markdown_files.append(path)
        else:
            print(f"⚠️  Ignoring non-Markdown path: {path}")
    return markdown_files


def convert_markdown_file(
    md_file: Path, output_dir: Path | None, *, force: bool
) -> Tuple[Path | None, bool]:
    if not md_file.exists():
        print(f"⚠️  File not found: {md_file}")
        return None, False

    target_dir = output_dir or md_file.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    html_path = target_dir / f"{md_file.stem}.html"

    if html_path.exists() and not force:
        print(f"⏭️  Skipping {md_file.name} (HTML already exists)")
        return html_path, False

    try:
        md_text = md_file.read_text(encoding="utf-8", errors="replace")
        full_html = markdown_to_html(md_text, title=md_file.stem)
        html_with_margins = add_margins(full_html)
        html_path.write_text(html_with_margins, encoding="utf-8")
        print(f"✅ HTML generated: {html_path}")
        return html_path, True
    except Exception as exc:
        print(f"❌ Error converting {md_file.name}: {exc}")
    return None, False


def apply_margins_to_paths(html_paths: Iterable[Path]) -> None:
    for html_path in html_paths:
        try:
            html_content = html_path.read_text(encoding="utf-8")
            html_path.write_text(add_margins(html_content), encoding="utf-8")
            print(f"📏 Margins added: {html_path.name}")
        except Exception as exc:
            print(f"❌ Error adding margins to {html_path}: {exc}")


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    markdown_files = collect_markdown_files(args.paths)

    if not markdown_files:
        print("📝 No Markdown files found to convert")
        return 0

    processed: List[Path] = []
    newly_generated: List[Path] = []
    for md_file in markdown_files:
        html_path, created = convert_markdown_file(md_file, args.output_dir, force=args.force)
        if html_path:
            processed.append(html_path)
        if created:
            newly_generated.append(html_path)

    if processed:
        apply_margins_to_paths(processed)

    if newly_generated:
        print(f"📄 Conversion completed ({len(newly_generated)} HTML file(s))")
    elif processed:
        print("⏭️  No new HTML generated (used existing files, margins updated)")
    else:
        print("⚠️  No HTML files were generated")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
