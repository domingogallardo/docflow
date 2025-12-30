#!/usr/bin/env python3
"""Tests for IncomingRouter classification."""
from pathlib import Path

from incoming_router import IncomingRouter


def test_incoming_router_classifies_types(tmp_path):
    incoming = tmp_path / "Incoming"
    incoming.mkdir()

    instapaper_html = incoming / "instapaper.html"
    instapaper_html.write_text(
        "<html><body><div id='origin'>Example.com</div><p>Body</p></body></html>",
        encoding="utf-8",
    )
    (incoming / "instapaper.md").write_text("# Instapaper Article\n", encoding="utf-8")

    tweet_md = incoming / "tweet.md"
    tweet_md.write_text(
        "# Tweet by Someone (@someone)\n\n[View on X](https://x.com/someone/status/123)\n",
        encoding="utf-8",
    )
    tweet_html = incoming / "tweet.html"
    tweet_html.write_text(
        "<html><body><h1>Tweet by Someone (@someone)</h1><a href=\"https://x.com/someone/status/123\">View on X</a></body></html>",
        encoding="utf-8",
    )

    podcast_md = incoming / "podcast.md"
    podcast_md.write_text(
        "# Test Podcast\n\n## Episode metadata\n- Episode title: Test\n- Show: Demo\n\n## Snips\n- Item\n",
        encoding="utf-8",
    )

    generic_md = incoming / "note.md"
    generic_md.write_text("# Note\n\nGeneric content\n", encoding="utf-8")

    pdf_file = incoming / "doc.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 test")

    image_file = incoming / "image.png"
    image_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    plan = IncomingRouter(incoming).build_plan()

    assert instapaper_html in plan.instapaper_html
    assert (incoming / "instapaper.md") in plan.instapaper_markdown
    assert tweet_md in plan.tweet_markdown
    assert tweet_html in plan.tweet_html
    assert podcast_md in plan.podcast_markdown
    assert generic_md in plan.generic_markdown
    assert pdf_file in plan.pdfs
    assert image_file in plan.images

    # Tweet markdown should not appear in generic markdown.
    assert tweet_md not in plan.generic_markdown
