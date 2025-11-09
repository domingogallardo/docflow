#!/usr/bin/env python3
"""Tests para utilidades de tweet_to_markdown."""
from utils.tweet_to_markdown import rebuild_urls_from_lines


def test_rebuild_urls_from_lines_merges_wrapped_urls():
    raw = "\n".join(
        [
            "Texto introductorio",
            "https://example.com/path/",
            "segmento",
            "final",
            "Título:",
            "Más texto",
        ]
    )
    result = rebuild_urls_from_lines(raw)
    assert "https://example.com/path/segmentofinal" in result
    assert "segmento" not in result.splitlines()[2]


def test_rebuild_urls_stops_on_ellipsis_or_blank():
    raw = "\n".join(
        [
            "https://example.com/uno/",
            "dos",
            "…",
            "https://example.com/tres/",
            "cuatro",
            "",
            "Fin",
        ]
    )
    result = rebuild_urls_from_lines(raw)
    assert "https://example.com/uno/dos" in result
    assert "https://example.com/tres/cuatro" in result
    assert "Fin" in result.splitlines()[-1]
