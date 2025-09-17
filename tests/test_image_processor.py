#!/usr/bin/env python3
"""Tests for ImageProcessor."""
from pathlib import Path

from image_processor import ImageProcessor


def write_dummy_image(path: Path, signature: bytes) -> None:
    path.write_bytes(signature + b"dummy")


def test_process_images_moves_files_and_updates_gallery(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    dest = tmp_path / "Images" / "Images 2025"

    write_dummy_image(incoming / "photo1.jpg", b"\xff\xd8\xff\xdb")
    write_dummy_image(incoming / "photo2.png", b"\x89PNG\r\n\x1a\n")
    write_dummy_image(incoming / "photo3.webp", b"RIFF....WEBP")

    processor = ImageProcessor(incoming, dest)
    moved = processor.process_images()

    assert len(moved) == 3
    assert (dest / "photo1.jpg").exists()
    assert (dest / "photo2.png").exists()
    assert (dest / "photo3.webp").exists()

    gallery = (dest / "gallery.html").read_text(encoding="utf-8")
    assert "photo1.jpg" in gallery
    assert "photo2.png" in gallery
    assert "photo3.webp" in gallery
    assert "Galería Images 2025" in gallery


def test_process_images_renames_conflicts(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()
    dest = tmp_path / "Images" / "Images 2025"
    dest.mkdir(parents=True, exist_ok=True)

    # Archivo existente que forzará renombrado
    write_dummy_image(dest / "duplicate.png", b"\x89PNG\r\n\x1a\n")
    write_dummy_image(incoming / "duplicate.png", b"\x89PNG\r\n\x1a\n")

    processor = ImageProcessor(incoming, dest)
    moved = processor.process_images()

    assert len(moved) == 1
    assert any(p.name.startswith("duplicate") for p in moved)
    assert (dest / "duplicate.png").exists()
    assert any(path.name != "duplicate.png" for path in dest.iterdir() if path.suffix.lower() == ".png")

    gallery = (dest / "gallery.html").read_text(encoding="utf-8")
    assert "duplicate.png" in gallery
    assert "duplicate (1).png" in gallery
