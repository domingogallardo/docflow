#!/usr/bin/env python3
"""ImageProcessor - Gestiona imágenes en el pipeline anual."""
from __future__ import annotations

from pathlib import Path
from typing import List
import html
from urllib.parse import quote

import utils as U
from path_utils import unique_path


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
        return unique_path(base)

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
                aria_label = html.escape(f"Ampliar {img.name}")
                figures.append(
                    "            <figure>\n"
                    "                <a class=\"gallery-thumb\" "
                    f"href=\"{href}\" data-full=\"{href}\" data-caption=\"{caption}\" "
                    f"aria-label=\"{aria_label}\" title=\"Haz clic para ampliar\">\n"
                    f"                    <img src=\"{href}\" alt=\"{alt_text}\">\n"
                    "                </a>\n"
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
            "        .gallery figure { margin: 0; display: flex; flex-direction: column; gap: 8px; }\n"
            "        .gallery-thumb { display: block; border: none; padding: 0; background: transparent; cursor: zoom-in; border-radius: 12px; text-decoration: none; }\n"
            "        .gallery-thumb:focus-visible { outline: 3px solid #0070f3; outline-offset: 4px; }\n"
            "        .gallery-thumb img { display: block; width: 100%; height:auto; border-radius: 12px; box-shadow: 0 6px 18px rgba(0, 0, 0, 0.1); background: #fff; }\n"
            "        figcaption { font-size: 14px; color: #555; word-break: break-word; }\n"
            "        .lightbox { position: fixed; inset: 0; display: flex; align-items: center; justify-content: center; background: rgba(0, 0, 0, 0.85); padding: 32px; opacity: 0; visibility: hidden; transition: opacity 0.2s ease; z-index: 1000; }\n"
            "        .lightbox[data-active=\"true\"] { opacity: 1; visibility: visible; }\n"
            "        .lightbox__inner { max-width: min(90vw, 1200px); max-height: 90vh; display: flex; flex-direction: column; align-items: center; gap: 16px; }\n"
            "        .lightbox__image { max-width: 100%; max-height: 70vh; border-radius: 16px; box-shadow: 0 20px 40px rgba(0, 0, 0, 0.35); background: #111; }\n"
            "        .lightbox__caption { color: #f5f5f5; text-align: center; font-size: 15px; word-break: break-word; }\n"
            "        .lightbox__close { align-self: flex-end; background: rgba(34, 34, 34, 0.9); color: #fff; border: none; padding: 8px 14px; border-radius: 999px; cursor: pointer; font-size: 14px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3); }\n"
            "        .lightbox__close:hover { background: rgba(34, 34, 34, 1); }\n"
            "        .lightbox__close:focus-visible { outline: 3px solid #fff; outline-offset: 3px; }\n"
            "        body.lightbox-open { overflow: hidden; }\n"
            "    </style>\n"
            "</head>\n"
            "<body>\n"
            f"    <h1>{title}</h1>\n"
            "    <div class=\"gallery\">\n"
            f"{gallery_body}\n"
            "    </div>\n"
            "    <div class=\"lightbox\" role=\"dialog\" aria-modal=\"true\" aria-hidden=\"true\" data-active=\"false\">\n"
            "        <div class=\"lightbox__inner\">\n"
            "            <button type=\"button\" class=\"lightbox__close\" aria-label=\"Cerrar vista ampliada\">Cerrar ✕</button>\n"
            "            <img src=\"\" alt=\"Imagen ampliada\" class=\"lightbox__image\">\n"
            "            <p class=\"lightbox__caption\"></p>\n"
            "        </div>\n"
            "    </div>\n"
            "    <script>\n"
            "        (function () {\n"
            "            const lightbox = document.querySelector('.lightbox');\n"
            "            const lightboxImage = lightbox ? lightbox.querySelector('.lightbox__image') : null;\n"
            "            const lightboxCaption = lightbox ? lightbox.querySelector('.lightbox__caption') : null;\n"
            "            const closeButton = lightbox ? lightbox.querySelector('.lightbox__close') : null;\n"
            "            if (!lightbox || !lightboxImage || !lightboxCaption || !closeButton) {\n"
            "                return;\n"
            "            }\n"
            "            let lastFocus = null;\n"
            "            function openLightbox(src, caption) {\n"
            "                if (!src) {\n"
            "                    return;\n"
            "                }\n"
            "                lightboxImage.src = src;\n"
            "                lightboxImage.alt = caption ? 'Vista ampliada de ' + caption : 'Imagen ampliada';\n"
            "                lightboxCaption.textContent = caption || '';\n"
            "                lightbox.setAttribute('data-active', 'true');\n"
            "                lightbox.setAttribute('aria-hidden', 'false');\n"
            "                document.body.classList.add('lightbox-open');\n"
            "                try {\n"
            "                    closeButton.focus({ preventScroll: true });\n"
            "                } catch (error) {\n"
            "                    closeButton.focus();\n"
            "                }\n"
            "            }\n"
            "            function closeLightbox() {\n"
            "                lightbox.setAttribute('data-active', 'false');\n"
            "                lightbox.setAttribute('aria-hidden', 'true');\n"
            "                document.body.classList.remove('lightbox-open');\n"
            "                lightboxImage.removeAttribute('src');\n"
            "                if (lastFocus) {\n"
            "                    try {\n"
            "                        lastFocus.focus({ preventScroll: true });\n"
            "                    } catch (error) {\n"
            "                        lastFocus.focus();\n"
            "                    }\n"
            "                }\n"
            "            }\n"
            "            document.querySelectorAll('.gallery-thumb').forEach(function (thumb) {\n"
            "                thumb.addEventListener('click', function (event) {\n"
            "                    event.preventDefault();\n"
            "                    const src = thumb.getAttribute('data-full');\n"
            "                    const caption = thumb.getAttribute('data-caption');\n"
            "                    lastFocus = thumb;\n"
            "                    openLightbox(src, caption);\n"
            "                });\n"
            "            });\n"
            "            closeButton.addEventListener('click', function () {\n"
            "                closeLightbox();\n"
            "            });\n"
            "            lightbox.addEventListener('click', function (event) {\n"
            "                if (event.target === lightbox) {\n"
            "                    closeLightbox();\n"
            "                }\n"
            "            });\n"
            "            document.addEventListener('keydown', function (event) {\n"
            "                if (event.key === 'Escape' && lightbox.getAttribute('data-active') === 'true') {\n"
            "                    closeLightbox();\n"
            "                }\n"
            "            });\n"
            "        })();\n"
            "    </script>\n"
            "</body>\n"
            "</html>\n"
        )

        gallery_path = self.destination_dir / self.gallery_name
        gallery_path.write_text(html_doc, encoding="utf-8")
        print(f"🖼️ Galería actualizada: {gallery_path}")
