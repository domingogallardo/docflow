#!/usr/bin/env python3
"""ImageProcessor - Gestiona imágenes en el pipeline anual."""
from __future__ import annotations

from pathlib import Path
from typing import List
import html
from urllib.parse import quote

import utils as U


class ImageProcessor:
    """Procesador para mover imágenes y generar una galería anual."""

    SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"}

    def __init__(self, incoming_dir: Path, destination_dir: Path):
        self.incoming_dir = incoming_dir
        self.destination_dir = destination_dir
        self.gallery_name = "gallery.html"

    def process_images(self) -> List[Path]:
        """Mueve imágenes desde Incoming y actualiza la galería anual."""
        print("🖼️ Procesando imágenes...")

        images = self._list_incoming_images()
        if not images:
            print("🖼️ No se encontraron imágenes para procesar")
            return []

        self.destination_dir.mkdir(parents=True, exist_ok=True)

        moved: List[Path] = []
        for image_path in images:
            dest_path = self._unique_destination(image_path.name)
            image_path.rename(dest_path)
            moved.append(dest_path)

        self._build_gallery()

        print(f"🖼️ {len(moved)} imagen(es) movidas a {self.destination_dir}")
        return moved

    # --------- helpers ---------
    def _list_incoming_images(self) -> List[Path]:
        return [p for p in U.list_files(self.SUPPORTED_EXTS, root=self.incoming_dir)]

    def _unique_destination(self, filename: str) -> Path:
        base = self.destination_dir / filename
        if not base.exists():
            return base
        stem = base.stem
        suffix = base.suffix
        counter = 1
        while True:
            candidate = self.destination_dir / f"{stem} ({counter}){suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def _build_gallery(self) -> None:
        images = [
            p for p in self.destination_dir.iterdir()
            if p.is_file() and p.suffix.lower() in self.SUPPORTED_EXTS
        ]
        images.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        title = f"Galería {self.destination_dir.name}"

        if images:
            figures = []
            for img in images:
                href = quote(img.name)
                alt_text = html.escape(img.stem.replace("_", " ").replace("-", " "))
                caption = html.escape(img.name)
                figures.append(
                    "            <figure>\n"
                    f"                <img src=\"{href}\" alt=\"{alt_text}\">\n"
                    f"                <figcaption>{caption}</figcaption>\n"
                    "            </figure>"
                )
            gallery_body = "\n".join(figures)
        else:
            gallery_body = "            <p>No hay imágenes procesadas para este año.</p>"

        html_doc = (
            "<!DOCTYPE html>\n"
            "<html>\n"
            "<head>\n"
            "    <meta charset=\"UTF-8\">\n"
            "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f"    <title>{title}</title>\n"
            "    <style>\n"
            "        body { margin: 4%; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #fafafa; color: #222; }\n"
            "        h1 { font-size: 28px; margin-bottom: 24px; }\n"
            "        .gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 24px; }\n"
            "        figure { margin: 0; display: flex; flex-direction: column; gap: 8px; }\n"
            "        img { width: 100%; height:auto; border-radius: 12px; box-shadow: 0 6px 18px rgba(0, 0, 0, 0.1); background: #fff; }\n"
            "        figcaption { font-size: 14px; color: #555; word-break: break-word; }\n"
            "    </style>\n"
            "</head>\n"
            "<body>\n"
            f"    <h1>{title}</h1>\n"
            "    <div class=\"gallery\">\n"
            f"{gallery_body}\n"
            "    </div>\n"
            "</body>\n"
            "</html>\n"
        )

        gallery_path = self.destination_dir / self.gallery_name
        gallery_path.write_text(html_doc, encoding="utf-8")
        print(f"🖼️ Galería actualizada: {gallery_path}")
