from pathlib import Path

from web_clipper_wrapper import (
    _html_bridge_redirect_url,
    attempts_for_url,
    author_metadata,
    build_template,
    clean_html_for_markdown,
    default_output_path,
    fetch_html,
    markdown_quality,
    original_published_metadata,
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


def test_clean_html_resolves_relative_images_against_document_base():
    html = """
    <html>
      <head><base href="/"></head>
      <body>
        <img src="images/article/photo.avif" alt="relative">
        <img src="https://cdn.example/photo.jpg" alt="absolute">
      </body>
    </html>
    """

    cleaned, removed = clean_html_for_markdown(
        html,
        base_url="https://example.com/posts/article/",
    )

    assert removed == 0
    assert 'src="https://example.com/images/article/photo.avif"' in cleaned
    assert 'src="https://cdn.example/photo.jpg"' in cleaned


def test_clean_html_resolves_document_relative_links_and_media():
    html = """
    <html>
      <head><base href="/"></head>
      <body>
        <a href="/pdf/main.pdf">Preprint</a>
        <a href="supplement.html">Supplement</a>
        <a href="#methods">Methods</a>
        <a href="mailto:team@example.com">Contact</a>
        <video poster="img/poster.webp"><source src="media/demo.webm"></video>
      </body>
    </html>
    """

    cleaned, removed = clean_html_for_markdown(
        html,
        base_url="https://example.com/posts/article/",
    )

    assert removed == 0
    assert 'href="https://example.com/pdf/main.pdf"' in cleaned
    assert 'href="https://example.com/supplement.html"' in cleaned
    assert 'href="#methods"' in cleaned
    assert 'href="mailto:team@example.com"' in cleaned
    assert 'poster="https://example.com/img/poster.webp"' in cleaned
    assert 'src="https://example.com/media/demo.webm"' in cleaned


def test_clean_html_keeps_data_images_when_removal_is_disabled():
    html = '<img src="data:image/png;base64,AAAA" alt="inline">'

    cleaned, removed = clean_html_for_markdown(
        html,
        base_url="https://example.com/article/",
        remove_data_images=False,
    )

    assert removed == 0
    assert "data:image/png;base64,AAAA" in cleaned


def test_clean_html_removes_script_and_template_payloads_but_keeps_article_content():
    html = """
    <article><p>Visible article text.</p></article>
    <script>self.__next_f.push('large serialized application state')</script>
    <template><p>Transport payload</p></template>
    """

    cleaned, removed = clean_html_for_markdown(html)

    assert removed == 0
    assert "Visible article text." in cleaned
    assert "serialized application state" not in cleaned
    assert "Transport payload" not in cleaned


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


def test_fetch_html_uses_detected_encoding_when_header_has_no_charset(monkeypatch):
    class FakeResponse:
        content = "<p>\u00a0\u2744</p>".encode("utf-8")
        headers = {"content-type": "text/html"}
        apparent_encoding = "utf-8"
        url = "https://example.com/article"

        def raise_for_status(self):
            pass

    def fake_get(url, headers, timeout):
        return FakeResponse()

    monkeypatch.setattr("web_clipper_wrapper.requests.get", fake_get)

    html, final_url = fetch_html("https://example.com/article")

    assert html == "<p>\u00a0\u2744</p>"
    assert "Â" not in html
    assert final_url == "https://example.com/article"


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


def test_markdown_quality_rejects_json_wrapped_escaped_markdown_destinations():
    noisy_body = (
        '\\["Intro [first](\\"https://example.com/one\\") and '
        '[second](\\"/two\\")", "more text"\\]'
    )

    quality = markdown_quality(noisy_body, min_chars=20, min_words=2)

    assert not quality.usable
    assert quality.reason == (
        "contains escaped Markdown destinations in a JSON-like wrapper"
    )


def test_strip_frontmatter_returns_body_only():
    assert strip_frontmatter("---\na: b\n---\nBody\n") == "Body"


def test_original_published_metadata_prefers_html_structured_date():
    html = """
    <html><head>
      <script type="application/ld+json">
        {"@type": "Article", "datePublished": "2026-05-02"}
      </script>
    </head></html>
    """
    markdown = "Published May 1, 2026\n\nBody"

    metadata = original_published_metadata(
        html,
        markdown,
        url="https://example.com/2026/05/03/article",
    )

    assert metadata == {
        "docflow_original_published_at": "2026-05-02",
        "docflow_original_published_source": "json_ld:datePublished",
    }


def test_original_published_metadata_uses_markdown_before_url_path():
    metadata = original_published_metadata(
        "<html></html>",
        "Published May 2, 2026\n\nBody",
        url="https://example.com/2026/05/03/article",
    )

    assert metadata == {
        "docflow_original_published_at": "2026-05-02",
        "docflow_original_published_source": "markdown_text:first_lines",
    }


def test_author_metadata_reads_json_ld_article_author():
    html = """
    <html><head>
      <script type="application/ld+json">
        {
          "@type": "BlogPosting",
          "author": {"@type": "Person", "name": "M.G. Siegler"}
        }
      </script>
    </head></html>
    """

    assert author_metadata(html) == {"author": "M.G. Siegler"}


def test_author_metadata_reads_json_ld_graph_article_author():
    html = """
    <html><head>
      <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@graph": [
            {"@type": "WebSite", "name": "Example"},
            {
              "@type": ["Article", "BlogPosting"],
              "author": [
                {"@type": "Person", "name": "Ada Lovelace"},
                {"@type": "Person", "name": "Grace Hopper"}
              ]
            }
          ]
        }
      </script>
    </head></html>
    """

    assert author_metadata(html) == {"author": "Ada Lovelace, Grace Hopper"}


def test_author_metadata_uses_meta_author_fallback():
    html = '<html><head><meta name="author" content="Tyler Cowen"></head></html>'

    assert author_metadata(html) == {"author": "Tyler Cowen"}


def test_author_metadata_ignores_url_only_article_author():
    html = (
        '<html><head><meta property="article:author" '
        'content="https://example.com/authors/alice"></head></html>'
    )

    assert author_metadata(html) == {}


def test_build_template_requests_author_from_clipper():
    attempt = attempts_for_url("https://example.com/article")[0]

    template = build_template(attempt)

    assert {"name": "author", "value": "{{author}}", "type": "multitext"} in template["properties"]


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
