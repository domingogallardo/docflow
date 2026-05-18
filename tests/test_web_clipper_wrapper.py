from pathlib import Path

from web_clipper_wrapper import (
    _html_bridge_redirect_url,
    attempts_for_url,
    clean_html_for_markdown,
    default_output_path,
    markdown_quality,
    read_urls_from_file,
    resolve_node_bin,
    strip_frontmatter,
)


def test_read_urls_from_file_extracts_and_dedupes(tmp_path: Path):
    links = tmp_path / "links.txt"
    links.write_text(
        "\n".join(
            [
                "# ignored",
                "",
                "https://example.com/one",
                "- later: https://example.com/two).",
                "https://example.com/one",
                "not a url",
            ]
        ),
        encoding="utf-8",
    )

    assert read_urls_from_file(links) == [
        "https://example.com/one",
        "https://example.com/two",
    ]


def test_clean_html_removes_data_images_but_keeps_remote_images():
    html = """
    <article>
      <p>Hello</p>
      <img src="data:image/png;base64,AAAA" alt="inline">
      <img src="https://example.com/image.png" alt="remote">
    </article>
    """

    cleaned, removed = clean_html_for_markdown(html)

    assert removed == 1
    assert "data:image" not in cleaned
    assert "https://example.com/image.png" in cleaned


def test_html_bridge_redirect_url_reads_substack_title_bridge():
    html = (
        '<head><noscript><meta http-equiv="refresh" '
        'content="0;URL=https://example.substack.com/p/post?x=1&amp;triedRedirect=true">'
        "</noscript>"
        "<title>https://example.substack.com/p/post?x=1&amp;triedRedirect=true</title>"
        "</head>"
    )

    assert _html_bridge_redirect_url(html) == (
        "https://example.substack.com/p/post?x=1&triedRedirect=true"
    )


def test_markdown_quality_rejects_frontmatter_only():
    quality = markdown_quality(
        '---\nsource: "https://example.com"\n---\n',
        min_chars=20,
        min_words=2,
    )

    assert not quality.usable
    assert quality.reason == "body too short"


def test_markdown_quality_accepts_article_body():
    body = " ".join(["word"] * 130)
    quality = markdown_quality(
        f'---\nsource: "https://example.com"\n---\n{body}',
        min_chars=20,
        min_words=120,
    )

    assert quality.usable
    assert quality.reason == "ok"


def test_markdown_quality_rejects_data_images():
    body = " ".join(["word"] * 130)
    quality = markdown_quality(
        f"{body}\n![](data:image/png;base64,AAAA)",
        min_chars=20,
        min_words=120,
    )

    assert not quality.usable
    assert quality.reason == "contains data:image payloads"


def test_markdown_quality_rejects_escaped_json_payload():
    escaped_comments = "<\\\\/p>\\\\n".join(["Comment"] * 25)
    noisy_body = (
        '\\["\\n\\n# Title\\n\\nBody text",'
        '"childrenIDs":[1,2],'
        '"content":"' + escaped_comments + '"}'
    )
    quality = markdown_quality(noisy_body, min_chars=20, min_words=2)

    assert not quality.usable
    assert quality.reason == "looks like escaped JSON instead of Markdown"


def test_strip_frontmatter_returns_body_only():
    assert strip_frontmatter("---\na: b\n---\nBody\n") == "Body"


def test_attempts_for_esade_include_domain_rule_after_content():
    attempts = [attempt.name for attempt in attempts_for_url("https://www.esade.edu/post")]

    assert attempts[:2] == ["content", "esade-content-text"]
    assert "article" in attempts


def test_attempts_for_substack_include_body_markup_after_content():
    attempts = [attempt.name for attempt in attempts_for_url("https://nanothoughts.substack.com/p/x")]

    assert attempts[:2] == ["content", "substack-body-markup"]


def test_attempts_for_lesswrong_include_post_content_after_content():
    attempts = [
        attempt.name
        for attempt in attempts_for_url(
            "https://www.lesswrong.com/posts/abc/example"
        )
    ]

    assert attempts[:2] == ["content", "lesswrong-post-content"]


def test_attempts_for_marginal_revolution_include_entry_content_after_content():
    attempts = attempts_for_url(
        "https://marginalrevolution.com/marginalrevolution/2026/05/example.html"
    )

    assert [attempt.name for attempt in attempts[:2]] == [
        "content",
        "marginalrevolution-entry-content",
    ]
    assert "{{selectorHtml:.byline|markdown}}" in attempts[1].content_format


def test_attempts_for_thenewthings_include_beehiiv_content_after_content():
    attempts = [
        attempt.name
        for attempt in attempts_for_url(
            "https://thenewthings.com/p/example"
        )
    ]

    assert attempts[:2] == ["content", "beehiiv-content-blocks"]


def test_attempts_include_body_as_last_generic_fallback():
    attempts = attempts_for_url("https://michaelnotebook.com/projects.html")
    names = [attempt.name for attempt in attempts]

    assert names[-1] == "body"
    assert attempts[-1].content_format == "{{selectorHtml:body|markdown}}"


def test_default_output_path_uses_url_slug(tmp_path: Path):
    path = default_output_path(
        tmp_path,
        "https://www.esade.edu/ecpol/es/blog/radiografia-del-alquiler/",
    )

    assert path == tmp_path / "clipper-radiografia-del-alquiler.md"


def test_resolve_node_bin_accepts_explicit_path(tmp_path: Path):
    node = tmp_path / "node"
    node.write_text("#!/bin/sh\n", encoding="utf-8")

    assert resolve_node_bin(str(node)) == str(node)


def test_resolve_node_bin_raises_for_missing_custom_binary():
    try:
        resolve_node_bin("definitely-missing-node-for-docflow-tests")
    except RuntimeError as exc:
        assert "Node.js executable not found" in str(exc)
    else:
        raise AssertionError("missing Node binary should fail")
