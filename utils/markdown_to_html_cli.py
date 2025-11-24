#!/usr/bin/env python3
"""Comando standalone para convertir Markdown a HTML sin depender de otros módulos del repo."""
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
            "Convierte archivos Markdown a HTML usando las mismas transformaciones "
            "de los pipelines del repositorio."
        )
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Rutas de archivos o directorios con Markdown a convertir",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        help="Directorio donde guardar los HTML generados (por defecto junto al Markdown)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Sobrescribe los archivos HTML si ya existen",
    )
    return parser.parse_args(argv)


def convert_urls_to_links(md_text: str) -> str:
    """Convierte URLs en texto plano a enlaces Markdown simples."""
    url_re = re.compile(r"(?P<url>https?://[^\s<]+)")

    def repl(match: re.Match[str]) -> str:
        url = match.group("url")
        return f"[{url}]({url})"

    return url_re.sub(repl, md_text)


def convert_newlines_to_br(html_text: str) -> str:
    """Inserta <br> dentro de párrafos para respetar saltos de línea."""
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
        "<html>\n<head>\n<meta charset=\"utf-8\"/>\n"
        f"<title>{title}</title>\n"
        "</head>\n<body>\n"
        f"{html_body}\n"
        "</body>\n</html>\n"
    )
    return full_html


def add_margins(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    margin_style = "body { margin-left: 6%; margin-right: 6%; }"
    head = soup.head
    if head is None:
        head = soup.new_tag("head")
        soup.html.insert(0, head) if soup.html else None
    style_tag = head.find("style")
    if style_tag:
        existing = style_tag.string or ""
        if margin_style not in existing:
            style_tag.string = (existing + ("\n" if existing else "") + margin_style)
    else:
        style_tag = soup.new_tag("style")
        style_tag.string = margin_style
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
            print(f"⚠️  Ignorando ruta no Markdown: {path}")
    return markdown_files


def convert_markdown_file(
    md_file: Path, output_dir: Path | None, *, force: bool
) -> Tuple[Path | None, bool]:
    if not md_file.exists():
        print(f"⚠️  Archivo no encontrado: {md_file}")
        return None, False

    target_dir = output_dir or md_file.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    html_path = target_dir / f"{md_file.stem}.html"

    if html_path.exists() and not force:
        print(f"⏭️  Saltando {md_file.name} (HTML ya existe)")
        return html_path, False

    try:
        md_text = md_file.read_text(encoding="utf-8", errors="replace")
        md_text = re.sub(r"\n{2,}", "\n", md_text)
        full_html = markdown_to_html(md_text, title=md_file.stem)
        html_with_margins = add_margins(full_html)
        html_path.write_text(html_with_margins, encoding="utf-8")
        print(f"✅ HTML generado: {html_path}")
        return html_path, True
    except Exception as exc:
        print(f"❌ Error convirtiendo {md_file.name}: {exc}")
    return None, False


def apply_margins_to_paths(html_paths: Iterable[Path]) -> None:
    for html_path in html_paths:
        try:
            html_content = html_path.read_text(encoding="utf-8")
            html_path.write_text(add_margins(html_content), encoding="utf-8")
            print(f"📏 Márgenes añadidos: {html_path.name}")
        except Exception as exc:
            print(f"❌ Error añadiendo márgenes a {html_path}: {exc}")


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    markdown_files = collect_markdown_files(args.paths)

    if not markdown_files:
        print("📝 No se encontraron archivos Markdown para convertir")
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
        print(f"📄 Conversión completada ({len(newly_generated)} archivo(s) HTML)")
    elif processed:
        print("⏭️  No se generaron nuevos HTML (se usaron existentes, márgenes actualizados)")
    else:
        print("⚠️  No se generaron archivos HTML")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
