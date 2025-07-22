#!/usr/bin/env python3
"""clean_snip.py
Limpia ficheros Markdown exportados desde Snipd:
1. Elimina reglas horizontales (---, *** o ___).
2. Elimina bloques <details>/<summary>; conserva el texto de <summary> como párrafo.
3. Sustituye enlaces "🎧 Play snip" por botones atractivos que abren en nueva pestaña

Uso:
    python clean_snip.py [--dir Misc]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable

# --------------------- patrones ---------------------
HR_PATTERN   = re.compile(r"^\s*([\-*_]\s*){3,}$")    # ---  ***  ___
SUMMARY_TAG  = re.compile(r"<summary>(.*?)</summary>", re.IGNORECASE | re.DOTALL)
SNIP_LINK    = re.compile(r"\[🎧[^\]]*\]\((https://share\.snipd\.com/[^)]+)\)")

# ----------------------------------------------------

def replace_snip(match: re.Match[str]) -> str:  # type: ignore[type-var]
    """Devuelve HTML embebido para el enlace del snip."""
    url = match.group(1)
    snip_id = url.rstrip("/").split("/")[-1]
    # Crear botón atractivo que abre en nueva pestaña
    return (
        f'<div style="text-align: center; margin: 10px 0;">\n'
        f'  <a href="{url}" target="_blank" rel="noopener" '
        f'style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); '
        f'color: white; padding: 12px 20px; text-decoration: none; border-radius: 25px; '
        f'font-size: 14px; font-weight: 500; box-shadow: 0 4px 15px rgba(0,0,0,0.2); '
        f'transition: all 0.3s ease;">\n'
        f'    🎧 Reproducir fragmento de audio\n'
        f'  </a>\n'
        f'</div>'
    )


def clean_lines(lines: Iterable[str]) -> list[str]:
    """Aplica reglas de limpieza línea a línea."""
    cleaned: list[str] = []
    for line in lines:
        lower = line.lower()
        # Eliminar etiquetas <details> y </details> pero mantener su contenido
        if '<details' in lower:
            continue
        if '</details>' in lower:
            continue
        # Convertir <summary> a texto plano
        if '<summary' in lower:
            cleaned_text = SUMMARY_TAG.sub(r"\1", line)
            cleaned.append(cleaned_text.strip() + "\n")
            continue

        # Eliminar líneas que contienen solo "Click to expand"
        if line.strip().lower() == "click to expand":
            continue

        # Eliminar reglas horizontales
        if HR_PATTERN.match(line):
            continue

        cleaned.append(line)
    return cleaned


def process_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")

    # Reemplazar saltos de línea HTML <br/> y <br/>> para quoted text
    text = re.sub(r"<br\s*/?>\s*>\s*", "\n> ", text)  # <br/>>  → nueva línea con "> "
    text = re.sub(r"<br\s*/?>", "\n", text)              # <br/>   → nueva línea simple

    # Reemplazar enlaces de audio
    text = SNIP_LINK.sub(replace_snip, text)

    original_lines = text.splitlines(keepends=True)
    new_lines = clean_lines(original_lines)

    if new_lines != original_lines:
        path.write_text("".join(new_lines), encoding="utf-8")
        print(f"🧹 Limpiado: {path}")


def parse_args():
    p = argparse.ArgumentParser(description="Limpia markdown Snipd.")
    p.add_argument("--dir", type=str, default="Misc", help="Directorio raíz (default: Misc)")
    return p.parse_args()


def main():
    args = parse_args()
    root = Path(args.dir)
    if not root.exists():
        raise SystemExit(f"❌ El directorio no existe: {root}")

    md_files = list(root.rglob("*.md"))
    if not md_files:
        print("No se encontraron archivos Markdown.")
        return

    for md in md_files:
        process_file(md)

    print(f"✨ Limpieza completa: {len(md_files)} archivos procesados.")


if __name__ == "__main__":
    main() 