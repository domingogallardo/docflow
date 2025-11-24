#!/usr/bin/env python3
"""Comando standalone para convertir archivos Markdown a HTML con el estilo del repositorio."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List, Tuple

import utils as U


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
        full_html = U.markdown_to_html(md_text, title=md_file.stem)
        html_path.write_text(full_html, encoding="utf-8")
        print(f"✅ HTML generado: {html_path}")
        return html_path, True
    except Exception as exc:
        print(f"❌ Error convirtiendo {md_file.name}: {exc}")
    return None, False


def apply_margins_to_paths(html_paths: Iterable[Path]) -> None:
    paths_by_dir: dict[Path, set[Path]] = {}
    for html_path in html_paths:
        paths_by_dir.setdefault(html_path.parent, set()).add(html_path.resolve())

    for directory, targets in paths_by_dir.items():
        def _filter(path: Path) -> bool:
            return path.resolve() in targets

        U.add_margins_to_html_files(directory, file_filter=_filter)


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
