#!/usr/bin/env python3
"""Helpers to generate descriptive image filenames using OpenAI."""
from __future__ import annotations

import base64
import re
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps


class ImageAIDescriber:
    """Generate short descriptive filenames for images."""

    MIME_TYPES = {
        ".bmp": "image/bmp",
        ".gif": "image/gif",
        ".jpeg": "image/jpeg",
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".tiff": "image/tiff",
        ".webp": "image/webp",
    }

    def __init__(
        self,
        ai_client,
        *,
        model: str = "gpt-5-mini",
        max_name_len: int = 120,
        detail: str = "low",
        preview_max_side: int = 1024,
    ) -> None:
        self.client = ai_client
        self.model = model
        self.max_name_len = max_name_len
        self.detail = detail
        self.preview_max_side = preview_max_side
        self._missing_client_logged = False

    def describe_filename(self, image_path: Path) -> str | None:
        """Return a short descriptive filename stem, without extension."""
        if self.client is None:
            if not self._missing_client_logged:
                print("🤖 AI client not configured; keeping original image filenames")
                self._missing_client_logged = True
            return None

        try:
            data_url = self._image_data_url(image_path)
            client = (
                self.client.with_options(timeout=60)
                if hasattr(self.client, "with_options")
                else self.client
            )
            response = client.responses.create(
                model=self.model,
                instructions=(
                    "Return ONLY a concise filename stem and nothing else. "
                    "Do not include an extension. "
                    "Use 3 to 8 words when possible. "
                    "Describe the main visible subject or scene. "
                    "For screenshots, mention the app, page, or task shown. "
                    "Avoid generic fillers like image, photo, or picture unless they are necessary."
                ),
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "Create a short, search-friendly filename for this image. "
                                    "Keep it concrete and easy to scan."
                                ),
                            },
                            {
                                "type": "input_image",
                                "image_url": data_url,
                                "detail": self.detail,
                            },
                        ],
                    }
                ],
                max_output_tokens=48,
                reasoning={"effort": "minimal"},
                text={"verbosity": "low"},
            )
        except Exception as exc:
            print(f"❌ Error describing image {image_path.name}: {exc}")
            return None

        raw_name = self._response_text(response)
        cleaned = self._sanitize_filename(raw_name)
        return cleaned or None

    def _image_data_url(self, image_path: Path) -> str:
        payload, mime_type = self._image_payload(image_path)
        encoded = base64.b64encode(payload).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def _image_payload(self, image_path: Path) -> tuple[bytes, str]:
        try:
            with Image.open(image_path) as img:
                img = ImageOps.exif_transpose(img)
                img.thumbnail((self.preview_max_side, self.preview_max_side))
                has_alpha = "A" in img.getbands() or (
                    img.mode == "P" and "transparency" in img.info
                )
                buffer = BytesIO()
                if has_alpha:
                    if img.mode not in {"RGBA", "LA"}:
                        img = img.convert("RGBA")
                    img.save(buffer, format="PNG", optimize=True)
                    return buffer.getvalue(), "image/png"

                if img.mode not in {"RGB", "L"}:
                    img = img.convert("RGB")
                img.save(buffer, format="JPEG", quality=85, optimize=True)
                return buffer.getvalue(), "image/jpeg"
        except Exception:
            mime_type = self.MIME_TYPES.get(image_path.suffix.lower(), "image/jpeg")
            return image_path.read_bytes(), mime_type

    def _response_text(self, response) -> str:
        text = (getattr(response, "output_text", "") or "").strip()
        if text:
            return text

        def _collect(value: object) -> str:
            if value is None:
                return ""
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                return "".join(_collect(item) for item in value)
            if isinstance(value, dict):
                return "".join(
                    [
                        str(value.get("text", "")),
                        _collect(value.get("content")),
                        str(value.get("output_text", "")),
                    ]
                )
            if hasattr(value, "text"):
                return str(getattr(value, "text", ""))
            if hasattr(value, "content"):
                return _collect(getattr(value, "content"))
            if hasattr(value, "output_text"):
                return str(getattr(value, "output_text", ""))
            return str(value)

        outputs = getattr(response, "output", None) or getattr(response, "content", None)
        if outputs:
            return _collect(outputs).strip()

        messages = getattr(response, "messages", None)
        if messages:
            return _collect(messages).strip()

        return ""

    def _sanitize_filename(self, value: str) -> str:
        cleaned = value.replace("```", " ").replace("\n", " ").strip()
        cleaned = re.sub(r"^(filename|title)\s*[:\-]\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip("\"'“”‘’` ")
        cleaned = cleaned.replace("_", " ")
        cleaned = re.sub(
            r"\.(?:bmp|gif|jpe?g|png|tiff|webp)$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r'[<>:"/\\|?*#]', "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = cleaned.strip(" .-_")
        return cleaned[: self.max_name_len].strip() or ""
