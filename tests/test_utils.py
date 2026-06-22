import sys
from pathlib import Path
import pytest

sys.path.append(str(Path(__file__).parent.parent))  # To import utils.py.
import utils
from podcast_processor import PodcastProcessor

def test_extract_episode_title():
    fixture_path = Path(__file__).parent / "fixtures" / "snipd_example.md"
    title = utils.extract_episode_title(fixture_path)
    assert title == "AI Podcast - The Future of AI"

def test_is_podcast_file_true():
    fixture_path = Path(__file__).parent / "fixtures" / "snipd_example.md"
    assert utils.is_podcast_file(fixture_path) is True

def test_is_podcast_file_false():
    # Create a temporary file that is not from Snipd.
    non_podcast_path = Path(__file__).parent / "fixtures" / "not_a_podcast.md"
    non_podcast_path.write_text("# Not a podcast\nSome random markdown content\n", encoding="utf-8")
    try:
        assert utils.is_podcast_file(non_podcast_path) is False
    finally:
        non_podcast_path.unlink()  # Clean up the temporary file.


# Tests for centralized CSS.
def test_get_base_css():
    """Test that verifies get_base_css() returns the correct CSS."""
    css = utils.get_base_css()
    
    # Verify it contains the expected elements.
    assert "-apple-system" in css, "CSS no contiene la tipografía del sistema"
    assert "margin: 6%" in css, "CSS no contiene los márgenes"
    assert "font-weight: bold" in css, "CSS no contiene títulos en negrita"
    assert "border-bottom: 1px solid #eee" in css, "CSS no contiene la línea inferior"
    assert "blockquote" in css, "CSS no contiene estilos de blockquote"
    assert "hr" in css, "CSS no contiene estilos de separadores"


def test_podcast_processor_uses_centralized_css():
    """Test that verifies PodcastProcessor uses centralized CSS."""
    processor = PodcastProcessor(Path("/tmp"), Path("/tmp"))
    html = processor._wrap_html("Test Podcast", "<p>Contenido de prueba</p>")
    
    # Verify it uses the base CSS.
    assert "-apple-system" in html, "PodcastProcessor no usa tipografía del sistema"
    assert "margin: 6%" in html, "PodcastProcessor no usa márgenes centralizados"
    assert "#667eea" in html, "PodcastProcessor no usa color de podcast"
    assert "border-left: 4px solid #667eea" in html, "PodcastProcessor no usa borde azul podcast"


def test_clean_duplicate_markdown_links():
    """Test to verify cleaning duplicated Markdown links."""
    from utils import clean_duplicate_markdown_links
    
    # Test with a duplicated link.
    text_with_duplicate = """See more details: [https://people.idsia.ch/~juergen/who-invented-backpropagation.html](https://people.idsia.ch/~juergen/who-invented-backpropagation.html)"""
    
    result = clean_duplicate_markdown_links(text_with_duplicate)
    
    # Verify the URL was truncated and cleaned.
    assert "people.idsia.ch/~juergen/who-invented-back..." in result
    assert result.count("https://people.idsia.ch/~juergen/who-invented-backpropagation.html") == 1  # Only in the link.
    
    # Test with a normal (non-duplicated) link - should not change.
    text_normal = """See [this article](https://example.com) for more info."""
    result_normal = clean_duplicate_markdown_links(text_normal)
    assert result_normal == text_normal
    
    # Test with a short URL - should not be truncated.
    text_short = """Visit [https://x.com/test](https://x.com/test)"""
    result_short = clean_duplicate_markdown_links(text_short)
    assert "x.com/test" in result_short
    assert "..." not in result_short


def test_add_margins_wraps_images(tmp_path):
    from bs4 import BeautifulSoup

    html = tmp_path / "sample.html"
    html.write_text("<html><head></head><body><p>hola</p><img src=\"https://img.test/x.jpg\"></body></html>", encoding="utf-8")

    utils.add_margins_to_html_files(tmp_path)

    out = html.read_text(encoding="utf-8")
    soup = BeautifulSoup(out, "html.parser")
    wrapped = soup.find("a", href="https://img.test/x.jpg")
    assert wrapped is not None
    assert wrapped.get("target") == "_blank"
    rel = wrapped.get("rel") or []
    assert "noopener" in rel
    img = wrapped.find("img")
    assert img is not None
    assert img.get("src") == "https://img.test/x.jpg"
    assert "cursor: zoom-in" in out
    assert "body { margin-left: 6%; margin-right: 6%; background: #fff; color: #111; }" in out


def test_add_margins_replaces_minimal_body_style(tmp_path):
    html = tmp_path / "sample.html"
    html.write_text(
        (
            "<html><head><style>body { margin-left: 6%; margin-right: 6%; }</style></head>"
            "<body><p>hola</p></body></html>"
        ),
        encoding="utf-8",
    )

    utils.add_margins_to_html_files(tmp_path)

    out = html.read_text(encoding="utf-8")
    assert "body { margin-left: 6%; margin-right: 6%; background: #fff; color: #111; }" in out
    assert "font-family" not in out


def test_add_margins_reuses_existing_anchor_and_fixes_nested_image_links(tmp_path):
    from bs4 import BeautifulSoup

    html = tmp_path / "sample.html"
    html.write_text(
        (
            "<html><head></head><body><figure>"
            '<a href="https://img.test/full.jpg"><div><picture>'
            '<a class="image-zoom" href="https://img.test/thumb.jpg">'
            '<img src="https://img.test/thumb.jpg"></a>'
            "</picture></div></a>"
            '<figcaption><a href="https://example.com/caption">Caption</a></figcaption>'
            "</figure></body></html>"
        ),
        encoding="utf-8",
    )

    utils.add_margins_to_html_files(tmp_path)

    out = html.read_text(encoding="utf-8")
    soup = BeautifulSoup(out, "html.parser")
    figure = soup.find("figure")
    assert figure is not None
    wrapped = figure.find("a", class_="image-zoom")
    assert wrapped is not None
    assert wrapped.get("href") == "https://img.test/full.jpg"
    assert "image-zoom" in (wrapped.get("class") or [])
    assert wrapped.find("div") is None
    assert wrapped.find("picture") is not None
    img = wrapped.find("img")
    assert img is not None
    assert img.get("src") == "https://img.test/thumb.jpg"


def test_add_margins_uses_card_image_src_for_zoom(tmp_path):
    from bs4 import BeautifulSoup

    html = tmp_path / "sample.html"
    html.write_text(
        (
            "<html><head></head><body>"
            '<div class="docflow-link-card">'
            '<a class="docflow-link-card__image-link" href="https://t.co/card">'
            '<img class="docflow-link-card__image" src="https://img.test/card.jpg">'
            "</a>"
            '<a class="docflow-link-card__title" href="https://t.co/card">Card</a>'
            "</div>"
            "</body></html>"
        ),
        encoding="utf-8",
    )

    utils.add_margins_to_html_files(tmp_path)

    out = html.read_text(encoding="utf-8")
    soup = BeautifulSoup(out, "html.parser")
    link = soup.find("a", class_="docflow-link-card__image-link")
    assert link is not None
    assert link.get("href") == "https://t.co/card"
    assert link.get("data-image-zoom-src") == "https://img.test/card.jpg"
    assert "image-zoom" in (link.get("class") or [])
    assert 'data-image-zoom-src") || link.getAttribute("href")' in out


def test_add_margins_adds_wrapped_pre_styles(tmp_path):
    html = tmp_path / "sample.html"
    html.write_text("<html><head></head><body><pre><code>Long prose line</code></pre></body></html>", encoding="utf-8")

    utils.add_margins_to_html_files(tmp_path)

    out = html.read_text(encoding="utf-8")
    assert "pre { white-space: pre-wrap;" in out
    assert "pre code { white-space: inherit; }" in out


def test_add_margins_makes_fixed_width_videos_responsive(tmp_path):
    html = tmp_path / "sample.html"
    html.write_text(
        '<html><head></head><body><video width="1188"></video></body></html>',
        encoding="utf-8",
    )

    utils.add_margins_to_html_files(tmp_path)

    out = html.read_text(encoding="utf-8")
    assert "video { max-width: 100%; height: auto; }" in out


def test_convert_urls_integration():
    """End-to-end test for URL processing (dedupe + conversion)."""
    from utils import convert_urls_to_links
    
    test_text = """Enlaces duplicados: [https://people.idsia.ch/~juergen/very-long-path-that-should-be-truncated.html](https://people.idsia.ch/~juergen/very-long-path-that-should-be-truncated.html)
    
URL aislada: https://x.com/SchmidhuberAI/status/1950194864940835159"""
    
    result = convert_urls_to_links(test_text)
    
    # Verify the duplicated link was cleaned.
    assert "people.idsia.ch/~juergen/very-long-path-th..." in result
    
    # Verify the standalone URL was converted to a link.
    assert "[https://x.com/SchmidhuberAI/status/1950194864940835159](https://x.com/SchmidhuberAI/status/1950194864940835159)" in result 


def test_convert_urls_does_not_linkify_inside_raw_iframe_blocks():
    from utils import convert_urls_to_links

    md = """Intro https://example.com/plain

<iframe srcdoc="<!doctype html>
<blockquote
  class=&quot;instagram-media&quot;
  data-instgrm-permalink=&quot;https://instagram.com/p/DX_WjYuspNk/?utm_source=ig_embed&utm_campaign=loading&quot;
></blockquote>
<script async src=&quot;https://www.instagram.com/embed.js&quot;></script>
</iframe>
"""

    result = convert_urls_to_links(md)

    assert "[https://example.com/plain](https://example.com/plain)" in result
    assert "[https://instagram.com" not in result
    assert "data-instgrm-permalink=&quot;https://instagram.com/p/DX_WjYuspNk/" in result
    assert "src=&quot;https://www.instagram.com/embed.js&quot;" in result


def test_convert_urls_does_not_linkify_urls_inside_markdown_link_text():
    from utils import convert_urls_to_links

    md = "[*https://x.com/ProfAviLoeb*](https://x.com/ProfAviLoeb)"

    result = convert_urls_to_links(md)

    assert result == md


def test_convert_urls_does_not_linkify_inside_markdown_image_links():
    from utils import convert_urls_to_links

    md = "[![](https://img.example/post.png)](https://x.com/handle/status/123)"

    result = convert_urls_to_links(md)

    assert result == md


def test_convert_urls_does_not_linkify_inside_fenced_code_blocks():
    from utils import convert_urls_to_links

    md = """Intro https://example.com/plain

```
https://x.com/someone/status/123
```
"""

    result = convert_urls_to_links(md)

    assert "[https://example.com/plain](https://example.com/plain)" in result
    assert "[https://x.com/someone/status/123]" not in result
    assert "```\nhttps://x.com/someone/status/123\n```" in result


def test_convert_newlines_to_br_does_not_inject_breaks_in_list_items():
    from utils import convert_newlines_to_br

    html = "<ul><li>\n<p>Item A</p>\n</li><li>Item B</li></ul>"
    converted = convert_newlines_to_br(html)

    assert "<li><br>" not in converted
    assert "<br></li>" not in converted
    assert "<p>Item A</p>" in converted


def test_convert_newlines_to_br_does_not_treat_pre_as_paragraph():
    from utils import convert_newlines_to_br

    html = "<pre><code>Intro line\n</code></pre>\n<blockquote>\n<p>Quote</p>\n</blockquote>"
    converted = convert_newlines_to_br(html)

    assert "</code></pre><br>" not in converted
    assert "<blockquote><br>" not in converted
    assert "<pre><code>Intro line\n</code></pre>" in converted


def test_convert_newlines_to_br_keeps_x_handle_metadata_inline():
    from utils import convert_newlines_to_br

    html = "<p>Elon Musk\n@elonmusk\n·\n5h\nOn my way</p>"
    converted = convert_newlines_to_br(html)

    assert "@elonmusk<br>" not in converted
    assert "Elon Musk<br>\n@elonmusk · 5h<br>\nOn my way" in converted


def test_convert_newlines_to_br_joins_x_handle_punctuation_lists():
    from utils import convert_newlines_to_br

    html = "<p>Gracias:\n@pablogguz_\n,\n@SantiCalvo_Eco\n,\n@jgjorrin\n. Si me dejo a alguien.</p>"
    converted = convert_newlines_to_br(html)

    assert "@pablogguz_<br>" not in converted
    assert "@SantiCalvo_Eco<br>" not in converted
    assert "@jgjorrin<br>" not in converted
    assert "@pablogguz_, @SantiCalvo_Eco, @jgjorrin. Si me dejo a alguien." in converted


def test_convert_newlines_to_br_joins_inline_x_handle_continuations():
    from utils import convert_newlines_to_br

    html = "<p>Replying to @StuartHameroff\nand @davidchalmers42\nBody text.</p>"
    converted = convert_newlines_to_br(html)

    assert "@StuartHameroff<br>" not in converted
    assert "Replying to @StuartHameroff and @davidchalmers42<br>\nBody text." in converted


def test_convert_newlines_to_br_joins_inline_x_handle_metadata_lines():
    from utils import convert_newlines_to_br

    html = "<p>Quotevitrupo @vitrupo\n·Jan 1\nQuoted text.</p>"
    converted = convert_newlines_to_br(html)

    assert "@vitrupo<br>" not in converted
    assert "Quotevitrupo @vitrupo ·Jan 1<br>\nQuoted text." in converted


def test_markdown_to_html_avoids_list_item_br_artifacts():
    from bs4 import BeautifulSoup
    from utils import markdown_to_html

    md = """# Demo

- Parent item

  - Child item
- Sibling item
"""
    html = markdown_to_html(md, title="Demo")

    assert "<li><br>" not in html
    assert "<br></li>" not in html

    soup = BeautifulSoup(html, "html.parser")
    assert len(soup.find_all("li")) == 3


def test_markdown_to_html_does_not_inject_breaks_around_pre_blocks():
    from utils import markdown_to_html

    md = """```
Intro paragraph in code block
```

> Quote one
>
> Quote two
"""
    html = markdown_to_html(md, title="Demo")

    assert "</code></pre><br>" not in html
    assert "<blockquote><br>" not in html


def test_markdown_to_html_handles_definition_list_quotes():
    from bs4 import BeautifulSoup
    from utils import markdown_to_html

    md = """[Daring Fireball](https://daringfireball.net)
·
by John Gruber

:   Chance Miller:

    > Epic Games [announced](https://x.com/fortnite/status/123) the return.
"""
    html = markdown_to_html(md, title="Demo")

    assert "[announced](https://x.com/fortnite/status/123)" not in html
    assert "<pre><code>" not in html

    soup = BeautifulSoup(html, "html.parser")
    assert soup.find("dl") is not None
    assert soup.find("a", string="announced")["href"] == "https://x.com/fortnite/status/123"


def test_markdown_to_html_normalizes_substack_block_embeds():
    from bs4 import BeautifulSoup
    from utils import markdown_to_html

    md = """# Demo

[

![X avatar](https://img.example/avatar.jpg)

Author @handle

Embedded tweet text.

](https://x.com/handle/status/123)
"""
    html = markdown_to_html(md, title="Demo")

    assert "<p>[</p>" not in html
    assert "](https://x.com/handle/status/123)" not in html

    soup = BeautifulSoup(html, "html.parser")
    embed = soup.find("div", class_="docflow-embed")
    assert embed is not None
    assert embed.find("a", string="View on X")["href"] == "https://x.com/handle/status/123"
    assert "Embedded tweet text." in embed.get_text()


def test_markdown_to_html_normalizes_substack_block_embeds_with_trailing_text():
    from bs4 import BeautifulSoup
    from utils import markdown_to_html

    md = """# Demo

[

![X avatar](https://img.example/avatar.jpg)

Author @handle

](https://x.com/handle/status/123)[example.com](https://example.com) trailing text.
"""
    html = markdown_to_html(md, title="Demo")

    assert "](https://x.com/handle/status/123)" not in html
    assert "[example.com]" not in html

    soup = BeautifulSoup(html, "html.parser")
    embed = soup.find("div", class_="docflow-embed")
    assert embed is not None
    assert embed.find("a", string="View on X")["href"] == "https://x.com/handle/status/123"
    assert soup.find("a", string="example.com")["href"] == "https://example.com"


def test_markdown_to_html_normalizes_multiline_x_embeds():
    from bs4 import BeautifulSoup
    from utils import markdown_to_html

    md = """# Demo

[![](https://img.example/avatar.jpg)

Author @handle

Embedded tweet text.

![](https://img.example/media.jpg)

9:14 PM · Mar 31, 2026 · 247K Views

25 Replies · 164 Reposts · 768 Likes](https://x.com/handle/status/123?s=20)
"""
    html = markdown_to_html(md, title="Demo")

    assert "](https://x.com/handle/status/123" not in html

    soup = BeautifulSoup(html, "html.parser")
    embed = soup.find("div", class_="docflow-embed")
    assert embed is not None
    assert embed.find("a", string="View on X")["href"] == "https://x.com/handle/status/123?s=20"
    assert "Embedded tweet text." in embed.get_text()
    assert "25 Replies" in embed.get_text()


def test_markdown_to_html_does_not_capture_later_inline_x_links_after_image_links():
    from bs4 import BeautifulSoup
    from utils import markdown_to_html

    md = """# Demo

[![Author](https://img.example/author.png)](/author/casey/)

Question with [**posted**](https://x.com/handle/status/123) inline.
"""
    html = markdown_to_html(md, title="Demo")

    assert "docflow-embed-source" not in html
    assert "</div>" not in html

    soup = BeautifulSoup(html, "html.parser")
    assert soup.find("a", href="/author/casey/").find("img") is not None
    assert soup.find("a", string="posted")["href"] == "https://x.com/handle/status/123"


def test_markdown_to_html_normalizes_single_line_x_image_links():
    from bs4 import BeautifulSoup
    from utils import markdown_to_html

    md = """# Demo

[![](https://img.example/post.png)](https://x.com/handle/status/123)
"""
    html = markdown_to_html(md, title="Demo")

    assert "](https://x.com/handle/status/123)" not in html

    soup = BeautifulSoup(html, "html.parser")
    embed = soup.find("div", class_="docflow-embed")
    assert embed is not None
    assert embed.find("img")["src"] == "https://img.example/post.png"
    assert embed.find("a", string="View on X")["href"] == "https://x.com/handle/status/123"


def test_markdown_to_html_normalizes_youtube_image_links():
    from bs4 import BeautifulSoup
    from utils import markdown_to_html

    md = """# Demo

![](https://www.youtube.com/watch?v=abc123)
"""
    html = markdown_to_html(md, title="Demo")

    assert '<img alt="" src="https://www.youtube.com/watch?v=abc123"' not in html

    soup = BeautifulSoup(html, "html.parser")
    embed = soup.find("div", class_="docflow-embed")
    assert embed is not None
    assert embed.find("a", string="View on YouTube")["href"] == "https://www.youtube.com/watch?v=abc123"


def test_markdown_to_html_drops_substack_profile_avatar_cards():
    from bs4 import BeautifulSoup
    from utils import markdown_to_html

    md = """# Demo

[

![Author avatar](https://img.example/avatar.png)

](https://substack.com/@author)

[Author](https://substack.com/@author)
"""
    html = markdown_to_html(md, title="Demo")

    assert "docflow-embed" not in html
    assert "Read full story" not in html

    soup = BeautifulSoup(html, "html.parser")
    assert soup.find("a", string="Author")["href"] == "https://substack.com/@author"


def test_markdown_to_html_drops_adjacent_substack_profile_avatar_cards():
    from bs4 import BeautifulSoup
    from utils import markdown_to_html

    md = """# Demo

[

![Author one avatar](https://img.example/one.png)

](https://substack.com/@one)[

![Author two avatar](https://img.example/two.png)

](https://substack.com/@two)

[Author One](https://substack.com/@one) and [Author Two](https://substack.com/@two)
"""
    html = markdown_to_html(md, title="Demo")

    assert "](https://substack.com/@two)" not in html
    assert "<p>[</p>" not in html
    assert "Author one avatar" not in html
    assert "Author two avatar" not in html

    soup = BeautifulSoup(html, "html.parser")
    assert soup.find("a", string="Author One")["href"] == "https://substack.com/@one"
    assert soup.find("a", string="Author Two")["href"] == "https://substack.com/@two"


def test_markdown_to_html_handles_nested_substack_read_more_blocks():
    from bs4 import BeautifulSoup
    from utils import markdown_to_html

    md = """# Demo

[

![The Darkness](https://img.example/card.png)

#### The Darkness

[Noah Smith](https://substack.com/profile/8243895-noah-smith)

May 13, 2021

[

Read full story

](https://www.noahpinion.blog/p/the-darkness)

](https://www.noahpinion.blog/p/the-darkness)
"""
    html = markdown_to_html(md, title="Demo")

    assert "<p>[</p>" not in html
    assert "](https://www.noahpinion.blog/p/the-darkness)" not in html

    soup = BeautifulSoup(html, "html.parser")
    embed = soup.find("div", class_="docflow-embed")
    assert embed is not None
    assert embed.find("a", string="View embedded item")["href"] == "https://www.noahpinion.blog/p/the-darkness"
    assert embed.get_text().count("Read full story") == 0


def test_markdown_to_html_strips_unstable_tiktok_artifacts():
    from bs4 import BeautifulSoup
    from utils import markdown_to_html

    md = """# Demo

<iframe class="tiktok-iframe" src="https://cdn.iframe.ly/api/iframe?url=https%3A%2F%2Fwww.tiktok.com%2F%40u%2Fvideo%2F1"></iframe><iframe class="third-party-cookie-check-iframe" src="https://example.com/cookie.html"></iframe>

[![](https://img.example/poster.jpg)](https://www.tiktok.com/@u/video/1)

[@u](https://www.tiktok.com/@u)[A very long TikTok caption that should not become a huge visible link.](https://www.tiktok.com/@u/video/1)

![](https://substackcdn.com//img/alert-circle.svg)Tiktok failed to load.  

Enable 3rd party cookies or use another browser
"""
    html = markdown_to_html(md, title="Demo")

    assert "tiktok-iframe" not in html
    assert "third-party-cookie-check-iframe" not in html
    assert "Tiktok failed to load" not in html
    assert "3rd party cookies" not in html
    assert "A very long TikTok caption" not in html

    soup = BeautifulSoup(html, "html.parser")
    embed = soup.find("div", class_="docflow-embed-tiktok")
    assert embed is not None
    poster = soup.find("a", href="https://www.tiktok.com/@u/video/1")
    assert poster is not None
    assert poster.find("img")["src"] == "https://img.example/poster.jpg"
    assert embed.find("a", string="@u")["href"] == "https://www.tiktok.com/@u"
    assert embed.find("a", string="View on TikTok")["href"] == "https://www.tiktok.com/@u/video/1"


def test_enrich_markdown_metadata_adds_canonical_fields():
    from utils import enrich_markdown_metadata, split_front_matter

    md = "# Demo title\n\nBody with words."
    enriched = enrich_markdown_metadata(
        md,
        source_url="https://example.com/article",
        extra={"docflow_extractor": "test"},
        now="2026-01-02T03:04:05Z",
    )

    meta, body = split_front_matter(enriched)
    assert meta["title"] == "Demo title"
    assert meta["source_url"] == "https://example.com/article"
    assert meta["docflow_source_type"] == "web"
    assert meta["docflow_post_url"] == "https://example.com/article"
    assert meta["docflow_ingested_at"] == "2026-01-02T03:04:05Z"
    assert meta["docflow_extractor"] == "test"
    assert meta["docflow_word_count"] == "5"
    assert body.lstrip().startswith("# Demo title")


def test_enrich_markdown_metadata_does_not_backfill_missing_ingested_at():
    from utils import enrich_markdown_metadata, split_front_matter

    md = """---
docflow_id: existing-id
docflow_markdown_path: Posts/Posts 2020/Old post.md
docflow_render_status: paired_html
---

# Old post

Body with words.
"""

    enriched = enrich_markdown_metadata(md, now="2026-01-02T03:04:05Z")

    meta, _ = split_front_matter(enriched)
    assert meta["docflow_id"] == "existing-id"
    assert "docflow_ingested_at" not in meta
    assert meta["docflow_word_count"] == "5"


def test_enrich_markdown_metadata_removes_imported_description_and_tags():
    from utils import enrich_markdown_metadata, split_front_matter

    md = """---
title: Demo title
description: "Imported summary"
tags:
  - "clippings"
source: "https://example.com/article"
---

# Demo title

Body with words.
"""
    enriched = enrich_markdown_metadata(md, now="2026-01-02T03:04:05Z")

    meta, body = split_front_matter(enriched)
    assert "description" not in meta
    assert "tags" not in meta
    assert "clippings" not in enriched
    assert meta["source_url"] == "https://example.com/article"
    assert meta["docflow_post_url"] == "https://example.com/article"
    assert meta["docflow_ingested_at"] == "2026-01-02T03:04:05Z"
    assert body.lstrip().startswith("# Demo title")


def test_enrich_markdown_metadata_uses_first_body_link_as_post_url():
    from utils import enrich_markdown_metadata, split_front_matter

    md = """# Demo title

[original](https://example.com/original)

[second](https://example.com/second)
"""
    enriched = enrich_markdown_metadata(
        md,
        source_url="https://example.com/final",
        now="2026-01-02T03:04:05Z",
    )

    meta, _ = split_front_matter(enriched)
    assert meta["source_url"] == "https://example.com/final"
    assert meta["docflow_post_url"] == "https://example.com/original"


def test_enrich_markdown_metadata_does_not_add_post_url_to_tweets():
    from utils import enrich_markdown_metadata, split_front_matter

    md = """---
source: tweet
---

# Tweet

https://example.com/article
"""
    enriched = enrich_markdown_metadata(
        md,
        source_url="https://x.com/autor/status/123",
        now="2026-01-02T03:04:05Z",
    )

    meta, _ = split_front_matter(enriched)
    assert meta["docflow_source_type"] == "tweet"
    assert "docflow_post_url" not in meta


def test_markdown_to_html_renders_source_x_post_for_tweet_discovered_article():
    from utils import markdown_to_html

    md = """---
source_url: https://example.com/article
docflow_source_type: web
tweet_url: https://x.com/user/status/123
---

# Article

Body.
"""

    html = markdown_to_html(md, title="Article")

    assert "Original link:" in html
    assert "Source X post:" in html
    assert 'href="https://x.com/user/status/123"' in html


def test_markdown_to_html_wraps_long_original_source_urls():
    from utils import markdown_to_html

    md = """---
source_url: https://example.com/a-very-long-source-url-without-natural-breaking-points
docflow_source_type: web
---

Body.
"""

    html = markdown_to_html(md, title="Article")

    assert ".docflow-original-link { overflow-wrap: anywhere; word-break: break-word; }" in html


def test_markdown_to_html_does_not_render_source_x_post_for_tweets():
    from utils import markdown_to_html

    md = """---
source: tweet
docflow_source_type: tweet
tweet_url: https://x.com/user/status/123
---

# Tweet

Body.
"""

    html = markdown_to_html(md, title="Tweet")

    assert "Source X post:" not in html


def test_markdown_to_html_renders_front_matter_author():
    from bs4 import BeautifulSoup
    from utils import markdown_to_html

    md = """---
author:
  - "[[Casey Newton]]"
---

# Article

Body.
"""

    html = markdown_to_html(md, title="Article")

    soup = BeautifulSoup(html, "html.parser")
    author = soup.find("p", class_="docflow-author")
    assert author is not None
    assert author.get_text() == "By Casey Newton"
    assert soup.body.find() == author


def test_markdown_to_html_renders_legacy_link_card_as_card():
    from utils import markdown_to_html

    md = "\n".join(
        [
            "# Tweet",
            "",
            "Texto real.",
            "",
            "\\#### Link card",
            "[Example title](https://example.com/post)",
            "Domain: example.com",
            "Description: Example description.",
            "Image: https://example.com/card.jpg",
        ]
    )

    html = markdown_to_html(md, title="Tweet")

    assert '<div class="docflow-link-card">' in html
    assert 'class="docflow-link-card__title"' in html
    assert 'src="https://example.com/card.jpg"' in html
    assert "Image: https://example.com/card.jpg" not in html


def test_markdown_to_html_renders_markdown_link_card_as_card():
    from utils import markdown_to_html

    md = "\n".join(
        [
            "# Tweet",
            "",
            "Texto real.",
            "",
            "> [!link-card]",
            "> [![Link preview](https://example.com/card.jpg)](https://example.com/post)",
            "> **[Example title](https://example.com/post)**",
            "> example.com",
            "> Example description.",
        ]
    )

    html = markdown_to_html(md, title="Tweet")

    assert '<div class="docflow-link-card">' in html
    assert 'class="docflow-link-card__title"' in html
    assert 'src="https://example.com/card.jpg"' in html
    assert "[!link-card]" not in html


def test_markdown_to_html_renders_bare_url_link_card_without_bracket_artifact():
    from utils import markdown_to_html

    md = "\n".join(
        [
            "# Tweet",
            "",
            "> [!link-card]",
            "> https://t.co/osNHgNwBu7",
            "> t.co",
        ]
    )

    html = markdown_to_html(md, title="Tweet")

    assert '<a class="docflow-link-card__title" href="https://t.co/osNHgNwBu7"' in html
    assert ">https://t.co/osNHgNwBu7</a>" in html
    assert "[https://t.co/osNHgNwBu7" not in html


def test_markdown_to_html_renders_inline_front_matter_author():
    from utils import markdown_to_html

    md = """---
author: "[[John Gruber]]"
---

# Article

Body.
"""

    html = markdown_to_html(md, title="Article")

    assert '<p class="docflow-author">By John Gruber</p>' in html


def test_upsert_front_matter_preserves_unrelated_lines():
    from utils import upsert_front_matter

    md = "---\n# keep this comment\nsource: manual\n---\n\n# Demo\n"
    updated = upsert_front_matter(md, {"title": "Demo"})

    assert "# keep this comment" in updated
    assert "source: manual" in updated
    assert "title: Demo" in updated


def test_front_matter_meta_tags_exports_tweet_reply_fields():
    from utils import front_matter_meta_tags

    html = front_matter_meta_tags(
        {
            "tweet_reply_to_url": "https://x.com/parent/status/99",
            "tweet_reply_context_included": "true",
            "tweet_conversation_count": "3",
        }
    )

    assert (
        '<meta name="docflow-tweet-reply-to-url" '
        'content="https://x.com/parent/status/99">'
    ) in html
    assert (
        '<meta name="docflow-tweet-reply-context-included" content="true">'
    ) in html
    assert '<meta name="docflow-tweet-conversation-count" content="3">' in html


def test_front_matter_meta_tags_exports_docflow_summary():
    from utils import front_matter_meta_tags

    html = front_matter_meta_tags({"docflow_summary": "Resumen breve."})

    assert '<meta name="docflow-summary" content="Resumen breve.">' in html


def test_front_matter_block_escapes_yaml_sensitive_values():
    from utils import front_matter_block

    block = front_matter_block(
        {
            "name": 'Piotr "Woz"\nWozniak',
            "title": "A title: with colon",
        }
    )

    assert 'name: "Piotr \\"Woz\\"\\nWozniak"' in block
    assert 'title: "A title: with colon"' in block
    assert block.endswith("---\n\n")


def test_sync_markdown_html_pair_metadata_links_both_files(tmp_path):
    from bs4 import BeautifulSoup
    from utils import split_front_matter, sync_markdown_html_pair_metadata

    posts = tmp_path / "Posts" / "Posts 2026"
    posts.mkdir(parents=True)
    md = posts / "article.md"
    html = posts / "article.html"
    md.write_text("---\ntitle: Article\n---\n\n# Article\n", encoding="utf-8")
    html.write_text("<html><head><title>Article</title></head><body></body></html>", encoding="utf-8")

    sync_markdown_html_pair_metadata(md, html, base_dir=tmp_path)

    meta, _ = split_front_matter(md.read_text(encoding="utf-8"))
    assert meta["docflow_id"]
    assert meta["docflow_markdown_path"] == "Posts/Posts 2026/article.md"
    assert meta["docflow_html_path"] == "Posts/Posts 2026/article.html"
    assert meta["docflow_render_status"] == "paired_html"

    soup = BeautifulSoup(html.read_text(encoding="utf-8"), "html.parser")
    assert soup.find("meta", attrs={"name": "docflow-id"})["content"] == meta["docflow_id"]
    assert (
        soup.find("meta", attrs={"name": "docflow-markdown-path"})["content"]
        == "Posts/Posts 2026/article.md"
    )
    assert (
        soup.find("meta", attrs={"name": "docflow-html-path"})["content"]
        == "Posts/Posts 2026/article.html"
    )
    assert soup.find("meta", attrs={"name": "docflow-render-status"})["content"] == "paired_html"


def test_sync_markdown_html_pair_metadata_preserves_existing_id(tmp_path):
    from utils import split_front_matter, sync_markdown_html_pair_metadata

    md = tmp_path / "doc.md"
    html = tmp_path / "doc.html"
    md.write_text("---\ndocflow_id: existing-id\n---\n\n# Doc\n", encoding="utf-8")
    html.write_text("<html><head></head><body></body></html>", encoding="utf-8")

    sync_markdown_html_pair_metadata(md, html, base_dir=tmp_path)

    meta, _ = split_front_matter(md.read_text(encoding="utf-8"))
    assert meta["docflow_id"] == "existing-id"


def test_sync_markdown_only_metadata_adds_minimal_front_matter(tmp_path):
    from utils import split_front_matter, sync_markdown_only_metadata

    md = tmp_path / "Tweets" / "daily.md"
    md.parent.mkdir()
    md.write_text("# Daily tweets\n", encoding="utf-8")

    sync_markdown_only_metadata(md, base_dir=tmp_path)

    meta, body = split_front_matter(md.read_text(encoding="utf-8"))
    assert meta["docflow_id"]
    assert meta["docflow_markdown_path"] == "Tweets/daily.md"
    assert meta["docflow_render_status"] == "markdown_only"
    assert "docflow_html_path" not in meta
    assert body.lstrip().startswith("# Daily tweets")


def test_sync_markdown_only_metadata_removes_stale_html_path(tmp_path):
    from utils import split_front_matter, sync_markdown_only_metadata

    md = tmp_path / "Tweets" / "tweet.md"
    md.parent.mkdir()
    md.write_text(
        "---\n"
        "docflow_id: existing-id\n"
        "docflow_markdown_path: Tweets/tweet.md\n"
        "docflow_html_path: Tweets/tweet.html\n"
        "docflow_render_status: paired_html\n"
        "---\n\n"
        "# Tweet\n",
        encoding="utf-8",
    )

    sync_markdown_only_metadata(md, base_dir=tmp_path)

    meta, body = split_front_matter(md.read_text(encoding="utf-8"))
    assert meta["docflow_id"] == "existing-id"
    assert meta["docflow_markdown_path"] == "Tweets/tweet.md"
    assert meta["docflow_render_status"] == "markdown_only"
    assert "docflow_html_path" not in meta
    assert body.lstrip().startswith("# Tweet")


def test_ensure_pdf_sidecar_markdown_sets_docflow_ingested_at(tmp_path):
    from utils import ensure_pdf_sidecar_markdown, split_front_matter

    pdf = tmp_path / "Pdfs" / "paper.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"%PDF-1.4\n")

    md = ensure_pdf_sidecar_markdown(
        pdf,
        base_dir=tmp_path,
        now="2026-01-02T03:04:05Z",
    )

    meta, body = split_front_matter(md.read_text(encoding="utf-8"))
    assert meta["docflow_ingested_at"] == "2026-01-02T03:04:05Z"
    assert meta["docflow_pdf_path"] == "Pdfs/paper.pdf"
    assert body.lstrip().startswith("# paper")


def test_ensure_pdf_sidecar_markdown_does_not_backfill_existing_ingested_at(tmp_path):
    from utils import ensure_pdf_sidecar_markdown, split_front_matter

    pdf = tmp_path / "Pdfs" / "paper.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"%PDF-1.4\n")
    md = pdf.with_suffix(".md")
    md.write_text(
        "---\ndocflow_id: existing-id\ndocflow_render_status: markdown_only\n---\n\n# Paper\n",
        encoding="utf-8",
    )

    ensure_pdf_sidecar_markdown(
        pdf,
        base_dir=tmp_path,
        now="2026-01-02T03:04:05Z",
    )

    meta, _ = split_front_matter(md.read_text(encoding="utf-8"))
    assert meta["docflow_id"] == "existing-id"
    assert "docflow_ingested_at" not in meta
