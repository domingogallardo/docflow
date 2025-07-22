from __future__ import annotations
from pathlib import Path
import argparse
import markdown  # pip install markdown


def md_to_html(md_text: str) -> str:
    """Convierte texto Markdown en HTML usando la librería *markdown*.

    Se añaden extensiones comunes como tablas y código con sangría.
    """
    return markdown.markdown(
        md_text,
        extensions=[
            "fenced_code",
            "tables",
            "toc",
        ],
        output_format="html5",
    )


def wrap_html(title: str, body: str) -> str:
    """Devuelve un documento HTML con cabecera mínima y UTF-8."""
    return (
        "<!DOCTYPE html>\n"
        "<html>\n<head>\n<meta charset=\"UTF-8\">\n"
        f"<title>{title}</title>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )


def process_file(md_path: Path) -> Path:
    """Convierte un fichero .md a .html junto a él y devuelve la ruta generada."""
    html_path = md_path.with_suffix(".html")
    # No sobrescribir si ya existe
    if html_path.exists():
        return html_path

    md_text = md_path.read_text(encoding="utf-8")
    html_body = md_to_html(md_text)
    full_html = wrap_html(md_path.stem, html_body)
    html_path.write_text(full_html, encoding="utf-8")
    # Mostrar ruta relativa si es posible sin lanzar excepción
    try:
        display_path = html_path.relative_to(Path.cwd()) if html_path.is_absolute() else html_path
    except ValueError:
        display_path = html_path
    print(f"✅ HTML generado: {display_path}")
    return html_path


def parse_args():
    p = argparse.ArgumentParser(description="Convierte todos los .md de un directorio a .html.")
    p.add_argument("--dir", type=str, default="Misc",
                   help="Directorio raíz donde buscar .md (por defecto: Misc)")
    return p.parse_args()


def main():
    args = parse_args()
    root = Path(args.dir)
    if not root.exists():
        raise SystemExit(f"❌ El directorio no existe: {root}")

    md_files = [p for p in root.rglob("*.md") if not p.with_suffix(".html").exists()]
    if not md_files:
        print("No hay ficheros .md pendientes de convertir.")
        return

    for md in md_files:
        process_file(md)

    print(f"🎉 Conversión completada: {len(md_files)} archivos procesados.")


if __name__ == "__main__":
    main() 