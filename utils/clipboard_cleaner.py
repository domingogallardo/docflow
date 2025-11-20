#!/usr/bin/env python3
"""Herramienta para limpiar HTML del portapapeles y generar Markdown compacto."""
from __future__ import annotations

import argparse
import base64
import plistlib
import re
import subprocess
import sys
from typing import Iterable, Optional

from bs4 import BeautifulSoup, NavigableString
from markdownify import markdownify

_TABLE_LIKE_TAGS = ("table", "thead", "tbody", "tfoot", "tr", "td", "th")
_LIST_ITEM_PATTERN = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")
_MACOS_HTML_SNIFF = re.compile(r"<[a-zA-Z!/][^>]*>")


def _normalize_structure(soup: BeautifulSoup) -> None:
    """Elimina ruido de emails (tablas) y caracteres especiales de macOS."""
    for head in soup.find_all("head"):
        head.decompose()

    for tag in soup.find_all(_TABLE_LIKE_TAGS):
        tag.unwrap()

    for span in soup.find_all("span", class_="Apple-converted-space"):
        span.replace_with(" ")


def html_to_compact_markdown(html: str) -> str:
    """Convierte HTML a Markdown compacto, pensado para pegar en Obsidian.

    Elimina párrafos innecesarios dentro de los elementos de lista y colapsa
    líneas en blanco intermedias para evitar que Obsidian inserte espacios
    adicionales entre elementos.
    """
    if not html or not html.strip():
        return ""

    soup = BeautifulSoup(html, "html.parser")
    _normalize_structure(soup)

    # Desenvuelve <p> cuando es el único elemento significativo del <li>.
    for li in soup.find_all("li"):
        direct_children = [
            child
            for child in li.children
            if not (isinstance(child, NavigableString) and not child.strip())
        ]
        if len(direct_children) == 1 and getattr(direct_children[0], "name", None) == "p":
            direct_children[0].unwrap()

    cleaned_html = soup.decode()
    markdown = markdownify(cleaned_html, bullets='-')
    markdown = _collapse_blank_lines_between_list_items(markdown)
    return markdown.strip()


def _collapse_blank_lines_between_list_items(markdown: str) -> str:
    lines = markdown.splitlines()
    result: list[str] = []

    for idx, line in enumerate(lines):
        if line.strip():
            if _should_remove_last_blank(result, line):
                result.pop()
            result.append(line.rstrip())
            continue

        # Línea en blanco: evaluar siguiente línea significativa
        next_line = _next_non_empty_line(lines, idx + 1)
        prev_line = result[-1] if result else ""
        if _LIST_ITEM_PATTERN.match(prev_line) and _LIST_ITEM_PATTERN.match(next_line or ""):
            continue  # omitir el blanco entre elementos contiguos

        if result and result[-1] == "":
            continue  # evitar múltiples líneas en blanco seguidas

        result.append("")

    # Eliminar blancos finales
    while result and result[-1] == "":
        result.pop()

    return "\n".join(result)


def _should_remove_last_blank(result: list[str], new_line: str) -> bool:
    if not result:
        return False
    if result[-1] != "":
        return False
    prev_line = result[-2] if len(result) > 1 else ""
    return _LIST_ITEM_PATTERN.match(prev_line) and _LIST_ITEM_PATTERN.match(new_line)


def _next_non_empty_line(lines: Iterable[str], start: int) -> Optional[str]:
    for line in lines[start:]:
        if line.strip():
            return line
    return None


def _looks_like_html(text: str) -> bool:
    if not text:
        return False
    return bool(_MACOS_HTML_SNIFF.search(text))


def _read_from_clipboard() -> str:
    html = _read_macos_html_clipboard()
    if html:
        return html

    return _run_command_capture(["pbpaste"])


def _read_macos_html_clipboard() -> str:
    html = _run_command_capture(["pbpaste", "-Prefer", "html"])
    if _looks_like_html(html):
        return html

    html = _run_osascript(
        """
ObjC.import('AppKit');
ObjC.import('Foundation');
let output = '';
try {
  const pb = $.NSPasteboard.generalPasteboard;
  for (const type of ['public.html', 'text/html']) {
    const data = pb.dataForType(type);
    if (!data) continue;
    const str = $.NSString.alloc.initWithDataEncoding(data, $.NSUTF8StringEncoding);
    if (str) {
      output = ObjC.unwrap(str);
      break;
    }
  }
} catch (err) {}
console.log(output);
        """
    )
    if _looks_like_html(html):
        return html

    html = _run_osascript(
        """
ObjC.import('AppKit');
ObjC.import('Foundation');
let output = '';
try {
  const pb = $.NSPasteboard.generalPasteboard;
  const data = pb.dataForType('com.apple.webarchive');
  if (data) {
    const nsdata = $.NSData.dataWithData(data);
    const b64 = nsdata.base64EncodedStringWithOptions(0);
    if (b64) output = ObjC.unwrap(b64);
  }
} catch (err) {}
console.log(output);
        """
    )
    if _looks_like_html(html):
        return html

    if html:
        try:
            import plistlib

            decoded = base64.b64decode(html, validate=True)
            plist = plistlib.loads(decoded)
            main_res = plist.get("WebMainResource") or {}
            data_field = main_res.get("WebResourceData")
            if isinstance(data_field, bytes):
                text = data_field.decode("utf-8", errors="ignore")
            elif isinstance(data_field, str):
                text = data_field
            else:
                text = ""
            if text and not _looks_like_html(text):
                # WebResourceData puede venir como base64 en texto
                try:
                    text_bytes = base64.b64decode(text, validate=True)
                    text = text_bytes.decode("utf-8", errors="ignore")
                except Exception:
                    text = ""
            if _looks_like_html(text):
                return text
        except Exception:
            pass

    return ""


def _run_command_capture(cmd: list[str]) -> str:
    try:
        completed = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except Exception:
        return ""
    return completed.stdout


def _run_osascript(script: str) -> str:
    try:
        completed = subprocess.run(
            ["osascript", "-l", "JavaScript"],
            input=script,
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return ""
    if completed.stdout:
        return completed.stdout
    return completed.stderr


def _write_to_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text, check=True, text=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convierte HTML del portapapeles a Markdown sin líneas en blanco entre elementos de lista.",
    )
    parser.add_argument(
        "--from-stdin",
        action="store_true",
        help="Leer el HTML desde stdin en lugar del portapapeles.",
    )
    parser.add_argument(
        "--no-copy",
        action="store_true",
        help="No escribir el resultado en el portapapeles.",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Mostrar el Markdown generado por stdout.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        html = sys.stdin.read() if args.from_stdin else _read_from_clipboard()
    except Exception as exc:
        parser.error(str(exc))
        return 1

    markdown = html_to_compact_markdown(html)

    if not markdown:
        return 0

    if args.print or args.no_copy:
        print(markdown)

    if not args.no_copy:
        try:
            _write_to_clipboard(markdown)
        except Exception as exc:
            parser.error(str(exc))
            return 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
