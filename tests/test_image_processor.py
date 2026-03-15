#!/usr/bin/env python3
"""Tests for ImageProcessor."""
from pathlib import Path

from image_processor import ImageProcessor


def write_dummy_image(path: Path, signature: bytes) -> None:
    path.write_bytes(signature + b"dummy")


class StubImageNamer:
    def __init__(self, mapping: dict[str, str | None] | None = None) -> None:
        self.mapping = mapping or {}

    def describe_filename(self, image_path: Path) -> str | None:
        return self.mapping.get(image_path.name)


def test_process_images_renames_files_with_descriptions_and_updates_gallery(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    dest = tmp_path / "Images" / "Images 2025"

    write_dummy_image(incoming / "photo1.jpg", b"\xff\xd8\xff\xdb")
    write_dummy_image(incoming / "photo2.png", b"\x89PNG\r\n\x1a\n")
    write_dummy_image(incoming / "photo3.webp", b"RIFF....WEBP")

    processor = ImageProcessor(
        incoming,
        dest,
        image_namer=StubImageNamer(
            {
                "photo1.jpg": "Mountain_lake_at_sunrise",
                "photo2.png": "Notes_app_weekly_plan",
                "photo3.webp": "Orange_cat_on_sofa",
            }
        ),
    )
    moved = processor.process_images()

    assert len(moved) == 3
    assert (dest / "Mountain lake at sunrise.jpg").exists()
    assert (dest / "Notes app weekly plan.png").exists()
    assert (dest / "Orange cat on sofa.webp").exists()

    gallery = (dest / "gallery.html").read_text(encoding="utf-8")
    assert "Mountain lake at sunrise.jpg" in gallery
    assert "Notes app weekly plan.png" in gallery
    assert "Orange cat on sofa.webp" in gallery
    assert "Gallery Images 2025" in gallery
    assert 'class="lightbox"' in gallery
    assert 'data-full="Mountain%20lake%20at%20sunrise.jpg"' in gallery
    assert 'class="gallery-thumb"' in gallery


def test_process_images_renames_conflicts(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    dest = tmp_path / "Images" / "Images 2025"
    dest.mkdir(parents=True, exist_ok=True)

    # Existing file that will force a rename.
    write_dummy_image(dest / "Blue ocean wave.png", b"\x89PNG\r\n\x1a\n")
    write_dummy_image(incoming / "duplicate.png", b"\x89PNG\r\n\x1a\n")

    processor = ImageProcessor(
        incoming,
        dest,
        image_namer=StubImageNamer({"duplicate.png": "Blue ocean wave"}),
    )
    moved = processor.process_images()

    assert len(moved) == 1
    assert any(p.name.startswith("Blue ocean wave") for p in moved)
    assert (dest / "Blue ocean wave.png").exists()
    assert any(path.name == "Blue ocean wave (1).png" for path in dest.iterdir() if path.suffix.lower() == ".png")

    gallery = (dest / "gallery.html").read_text(encoding="utf-8")
    assert "Blue ocean wave.png" in gallery
    assert "Blue ocean wave (1).png" in gallery


def test_process_images_keeps_original_name_when_description_is_missing(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    dest = tmp_path / "Images" / "Images 2025"

    write_dummy_image(incoming / "original.gif", b"GIF89a")

    processor = ImageProcessor(incoming, dest, image_namer=StubImageNamer())
    moved = processor.process_images()

    assert len(moved) == 1
    assert (dest / "original.gif").exists()
