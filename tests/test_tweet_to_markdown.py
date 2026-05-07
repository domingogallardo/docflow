#!/usr/bin/env python3
"""Tests para utilidades de tweet_to_markdown."""
from utils.tweet_to_markdown import (
    rebuild_urls_from_lines,
    normalize_inline_mention_breaks,
    normalize_glued_author_body_breaks,
    strip_platform_inline_prompts,
    strip_article_metric_preamble,
    strip_tweet_stats,
    _media_markdown_lines,
    _emoji_from_twimg_url,
    _insert_quote_separator,
    _pick_quoted_tweet_url,
    _has_quote_marker,
    _insert_media_before_quote,
    _status_id_from_url,
    _find_quoted_status_id,
    _quoted_url_from_graphql_id,
    _wait_for_tweet_detail,
    _detect_access_issue,
    PlaywrightTimeoutError,
    _expand_show_more,
    _read_article_text,
    _resolve_thread_context,
    _select_thread_indices,
    _extract_thread_ids_from_payload,
    _build_single_tweet_markdown,
    _build_thread_markdown,
    _build_filename,
    TweetParts,
    ReplyParentContext,
    _reply_parent_url_from_payload,
)


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


def test_rebuild_urls_stops_on_ellipsis_with_trailing_text():
    raw = "\n".join(
        [
            "Texto introductorio",
            "https://example.com/path/",
            "segmento",
            "… y sigue el texto.",
            "Cierre",
        ]
    )
    result = rebuild_urls_from_lines(raw)
    lines = result.splitlines()
    assert "https://example.com/path/segmento" in result
    assert "… y sigue el texto." not in result
    assert any("y sigue el texto." in line for line in lines)


def test_normalize_inline_mention_breaks_rejoins_split_mentions():
    raw = "\n".join(
        [
            "Intro paragraph.",
            "",
            "@Alibaba_Qwen",
            "'s Qwen3.5 and",
            "@GoogleDeepMind",
            "’s Gemma 4 are leading the pack.",
        ]
    )
    result = normalize_inline_mention_breaks(raw)
    assert result == (
        "Intro paragraph.\n\n"
        "@Alibaba_Qwen's Qwen3.5 and @GoogleDeepMind’s Gemma 4 are leading the pack."
    )


def test_normalize_inline_mention_breaks_keeps_new_mention_line_after_sentence_end():
    raw = "\n".join(
        [
            "Sentence complete.",
            "@alice",
            "shared a useful reference.",
        ]
    )
    result = normalize_inline_mention_breaks(raw)
    assert result == raw


def test_normalize_inline_mention_breaks_keeps_author_name_and_handle_separate():
    raw = "\n".join(
        [
            "Artificial Analysis",
            "@ArtificialAnlys",
            "Sub-32B models now offer GPT-5 level intelligence.",
        ]
    )
    result = normalize_inline_mention_breaks(raw)
    assert result == raw


def test_normalize_glued_author_body_breaks_splits_body_with_spaced_handle():
    raw = "Henry Shevlin@dioscuriI am confident that Turing would agree."
    result = normalize_glued_author_body_breaks(
        raw,
        author_name="Henry Shevlin",
        author_handle="@dioscuri",
    )
    assert result == "Henry Shevlin @dioscuri\nI am confident that Turing would agree."


def test_normalize_glued_author_body_breaks_keeps_time_with_author_line():
    raw = "Ethan Mollick@emollick·10hA thing I see missing from AI job debates."
    result = normalize_glued_author_body_breaks(
        raw,
        author_name="Ethan Mollick",
        author_handle="@emollick",
    )
    assert result == "Ethan Mollick @emollick·10h\nA thing I see missing from AI job debates."


def test_normalize_glued_author_body_breaks_allows_display_name_emoji():
    raw = "Peter Steinberger \U0001f99e@steipeteWanted a truly local storage."
    result = normalize_glued_author_body_breaks(
        raw,
        author_name="Peter Steinberger",
        author_handle="@steipete",
    )
    assert result == "Peter Steinberger \U0001f99e @steipete\nWanted a truly local storage."


def test_strip_platform_inline_prompts_separates_glued_link_card():
    raw = (
        "Wanted a truly local storage since they are not fully accessible via the api)."
        "Releases · steipete/birdclawFrom github.com"
    )
    result = strip_platform_inline_prompts(raw)
    assert result == "\n".join(
        [
            "Wanted a truly local storage since they are not fully accessible via the api).",
            "Releases · steipete/birdclaw",
            "From github.com",
        ]
    )


def test_strip_platform_inline_prompts_removes_show_translation_line():
    raw = "\n".join(
        [
            "Autor",
            "@handle",
            "Show translation",
            "Contenido válido.",
        ]
    )
    result = strip_platform_inline_prompts(raw)
    assert result == "Autor\n@handle\nContenido válido."


def test_strip_platform_inline_prompts_removes_translation_variants():
    raw = "\n".join(
        [
            "Autor",
            "Mostrar traducción",
            "Contenido válido.",
            "See translation",
        ]
    )
    result = strip_platform_inline_prompts(raw)
    assert result == "Autor\nContenido válido."


def test_strip_platform_inline_prompts_removes_glued_translation_prompt():
    raw = "Antonio Ortiz@antonelloShow translationPues ya es oficial."
    result = strip_platform_inline_prompts(
        raw,
        author_name="Antonio Ortiz",
        author_handle="@antonello",
    )
    assert result == "Antonio Ortiz @antonello\nPues ya es oficial."


def test_strip_platform_inline_prompts_removes_glued_subscribe_prompt():
    raw = (
        "Aella@Aella_GirlSubscribeClick to Subscribe to Aella_Girl"
        "Imagine a circle."
    )
    result = strip_platform_inline_prompts(
        raw,
        author_name="Aella",
        author_handle="@Aella_Girl",
    )
    assert result == "Aella @Aella_Girl\nImagine a circle."


def test_strip_platform_inline_prompts_removes_standalone_subscribe_line():
    raw = "\n".join(
        [
            "Nathan Lambert",
            "@natolambert",
            "Subscribe",
            "So much rests on which trend line is more representative.",
        ]
    )

    result = strip_platform_inline_prompts(
        raw,
        author_name="Nathan Lambert",
        author_handle="@natolambert",
    )

    assert result == "\n".join(
        [
            "Nathan Lambert",
            "@natolambert",
            "So much rests on which trend line is more representative.",
        ]
    )


def test_strip_platform_inline_prompts_separates_glued_edit_prompt_from_url():
    raw = "https://arxiv.org/abs/2501.09223Last edited"

    result = strip_platform_inline_prompts(raw)

    assert result == "https://arxiv.org/abs/2501.09223"


def test_strip_platform_inline_prompts_removes_view_activity_line():
    raw = "\n".join(
        [
            "Contenido válido.",
            "View activity",
        ]
    )

    result = strip_platform_inline_prompts(raw)

    assert result == "Contenido válido."


def test_strip_platform_inline_prompts_separates_glued_view_activity():
    raw = "Contenido válido.View activity"

    result = strip_platform_inline_prompts(raw)

    assert result == "Contenido válido."


def test_tweet_cleanup_keeps_url_when_edit_prompt_glues_metrics():
    raw = "\n".join(
        [
            "It's freely available on arXiv:",
            "",
            "https://arxiv.org/abs/2501.09223",
            "Last edited",
            "7:12 PM · Feb 17, 2026 · 2.4M Views",
            "340 1.2K 10K 11K Relevant View quotes",
        ]
    )

    rebuilt = rebuild_urls_from_lines(raw)
    cleaned = strip_tweet_stats(strip_platform_inline_prompts(rebuilt))

    assert cleaned == "\n".join(
        [
            "It's freely available on arXiv:",
            "",
            "https://arxiv.org/abs/2501.09223",
        ]
    )


def test_strip_platform_inline_prompts_preserves_meaningful_blank_lines():
    raw = "\n".join(
        [
            "First paragraph.",
            "",
            "",
            "Second paragraph.",
        ]
    )

    assert strip_platform_inline_prompts(raw) == "First paragraph.\n\nSecond paragraph."


def test_strip_platform_inline_prompts_removes_x_article_premium_prompt():
    raw = "\n".join(
        [
            "Actual article ending.",
            "Want to publish your own Article?",
            "Upgrade to Premium+",
        ]
    )

    assert strip_platform_inline_prompts(raw) == "Actual article ending."


def test_strip_platform_inline_prompts_removes_glued_x_article_prompt_tail():
    raw = (
        "If you build something impressive, share it below."
        "Want to publish your own Article?Upgrade to Premium+"
    )

    assert strip_platform_inline_prompts(raw) == (
        "If you build something impressive, share it below."
    )


def test_strip_article_metric_preamble_removes_x_article_counters():
    raw = "\n".join(
        [
            "Lisan al Gaib",
            "@scaling01",
            "The AI model gap is bigger than you think",
            "14",
            "28",
            "257",
            "60K",
            "Like all good articles, this one is a reaction.",
            "",
            "The main issue is benchmark shape.",
        ]
    )

    result = strip_article_metric_preamble(raw, author_handle="@scaling01")

    assert result == "\n".join(
        [
            "Lisan al Gaib",
            "@scaling01",
            "The AI model gap is bigger than you think",
            "Like all good articles, this one is a reaction.",
            "",
            "The main issue is benchmark shape.",
        ]
    )


def test_strip_article_metric_preamble_removes_compact_x_article_counters():
    raw = "\n".join(
        [
            "Lisan al Gaib",
            "@scaling01",
            "The AI model gap is bigger than you think142019430KLike all good articles, this one is a reaction.",
            "",
            "The main issue is benchmark shape.",
        ]
    )

    result = strip_article_metric_preamble(raw, author_handle="@scaling01")

    assert result == "\n".join(
        [
            "Lisan al Gaib",
            "@scaling01",
            "The AI model gap is bigger than you think",
            "Like all good articles, this one is a reaction.",
            "",
            "The main issue is benchmark shape.",
        ]
    )


def test_strip_article_metric_preamble_leaves_regular_numeric_body():
    raw = "\n".join(
        [
            "Author",
            "@author",
            "42",
            "is still the answer.",
            "More text.",
        ]
    )

    assert strip_article_metric_preamble(raw, author_handle="@author") == raw


def test_strip_article_metric_preamble_keeps_compact_year_in_title():
    raw = "\n".join(
        [
            "Author",
            "@author",
            "Model release 2026Introduces lower latency.",
            "More text.",
        ]
    )

    assert strip_article_metric_preamble(raw, author_handle="@author") == raw


def test_strip_article_metric_preamble_removes_embedded_tweet_metric_block():
    raw = "\n".join(
        [
            "Chris Hayduk",
            "@ChrisHayduk",
            "On the Looped Transformers Controversy",
            "Chris Hayduk",
            "@ChrisHayduk",
            "·",
            "Apr 10",
            "I strongly suspect that Claude Mythos is a looped language model.",
            "111",
            "422",
            "4K",
            "595K",
            "This was not meant to be taken as fact.",
        ]
    )

    result = strip_article_metric_preamble(raw, author_handle="@ChrisHayduk")

    assert result == "\n".join(
        [
            "Chris Hayduk",
            "@ChrisHayduk",
            "On the Looped Transformers Controversy",
            "Chris Hayduk",
            "@ChrisHayduk",
            "·",
            "Apr 10",
            "I strongly suspect that Claude Mythos is a looped language model.",
            "This was not meant to be taken as fact.",
        ]
    )


def test_strip_article_metric_preamble_keeps_numeric_body_without_embedded_tweet_chrome():
    raw = "\n".join(
        [
            "Author",
            "@author",
            "Useful thresholds:",
            "111",
            "422",
            "4K",
            "595K",
            "Those thresholds are intentionally strange.",
        ]
    )

    assert strip_article_metric_preamble(raw, author_handle="@author") == raw


def test_strip_tweet_stats_removes_metrics_lines():
    raw = "\n".join(
        [
            "Autor",
            "@handle",
            "Texto del tweet que debe quedarse.",
            "",
            "Contenido adicional.",
            "10:25 PM · Jul 13, 2025 · 1.2M Views",
            "12.3K Retweets   900 Quotes   8.1K Likes   300 Bookmarks",
        ]
    )
    result = strip_tweet_stats(raw)
    lines = result.splitlines()
    assert "Texto del tweet que debe quedarse." in lines
    assert "Contenido adicional." in lines
    for metric in ("Views", "Retweets", "Quotes", "Likes", "Bookmarks"):
        assert all(metric not in line for line in lines)


def test_strip_tweet_stats_removes_timestamp_and_counts_block():
    raw = "\n".join(
        [
            "Contenido válido.",
            "",
            "6:47 AM · Nov 10, 2025",
            "·",
            "18.3K",
            "Views",
            "2",
            "24",
            "175",
            "136",
        ]
    )
    result = strip_tweet_stats(raw)
    assert "Contenido válido." in result
    for snippet in ("Nov 10", "18.3K", "Views", "175"):
        assert snippet not in result


def test_strip_tweet_stats_keeps_compact_line_with_real_content():
    raw = (
        "monos estocásticos@monospodcastOpenClaw se va a OpenAiQuote"
        "Sam Altman@sama·Feb 15Peter Steinberger joins OpenAI"
        "Show more11:04 PM · Feb 15, 2026·965 Views116"
    )
    result = strip_tweet_stats(raw)
    assert "OpenClaw se va a OpenAi" in result
    assert result.strip() != ""


def test_strip_tweet_stats_removes_trailing_show_more_after_metrics():
    raw = "\n".join(
        [
            "Contenido válido.",
            "Show more",
            "11:04 PM · Feb 15, 2026",
            "·",
            "965",
            "Views",
            "1",
            "16",
        ]
    )
    result = strip_tweet_stats(raw)
    assert result == "Contenido válido."


def test_strip_tweet_stats_removes_metrics_block_ending_in_relevant():
    raw = "\n".join(
        [
            "Contenido válido.",
            "8:59 PM · Mar 10, 2026",
            "·",
            "53.2K",
            "Views",
            "43",
            "55",
            "551",
            "104",
            "Relevant",
        ]
    )
    result = strip_tweet_stats(raw)
    assert result == "Contenido válido."


def test_strip_tweet_stats_removes_reply_controls_after_metrics():
    raw = "\n".join(
        [
            "Contenido válido.",
            "6:44 PM · Apr 17, 2026",
            "·",
            "1.1M",
            "Views",
            "206",
            "2.6K",
            "15K",
            "4.7K",
            "Relevant",
            "View quotes",
            "You can reply to this post.",
        ]
    )
    result = strip_tweet_stats(raw)
    assert result == "Contenido válido."


def test_strip_tweet_stats_removes_multiline_reply_controls_after_metrics():
    raw = "\n".join(
        [
            "Contenido válido.",
            "8:10 PM · Mar 9, 2026",
            "·",
            "22.7K",
            "Views",
            "130",
            "632",
            "297",
            "Who can reply?",
            "Accounts",
            "@GoogleResearch",
            "mentioned can reply",
        ]
    )
    result = strip_tweet_stats(raw)
    assert result == "Contenido válido."


def test_strip_tweet_stats_removes_view_post_engagements_after_metrics():
    raw = "\n".join(
        [
            "Contenido válido.",
            "10:28 AM · Jan 20, 2026",
            "·",
            "32",
            "Views",
            "View post engagements",
        ]
    )
    result = strip_tweet_stats(raw)
    assert result == "Contenido válido."


def test_strip_tweet_stats_removes_new_version_prompts_after_metrics():
    raw = "\n".join(
        [
            "Contenido válido.",
            "12:12 PM · Nov 27, 2025",
            "·",
            "1,628",
            "Views",
            "There's a new version of this post.",
            "See the latest post",
        ]
    )
    result = strip_tweet_stats(raw)
    assert result == "Contenido válido."


def test_strip_tweet_stats_keeps_non_metric_relevant_line():
    raw = "\n".join(
        [
            "Contenido válido.",
            "Relevant",
        ]
    )
    result = strip_tweet_stats(raw)
    assert result == raw


def test_strip_tweet_stats_removes_platform_boilerplate_lines():
    raw = "\n".join(
        [
            "Contenido válido.",
            "",
            "Access your post analytics",
            "Unlock advanced analytics with X Premium",
            "Learn more",
        ]
    )
    result = strip_tweet_stats(raw)
    assert result == "Contenido válido."


def test_strip_tweet_stats_removes_inline_platform_boilerplate_tail():
    raw = (
        "Contenido válido. "
        "Access your post analytics "
        "Unlock advanced anlytics with X Premium "
        "Learn more"
    )
    result = strip_tweet_stats(raw)
    assert result == "Contenido válido."


def test_strip_tweet_stats_removes_compact_metric_tail():
    raw = (
        "Contenido válido7:46 AM · Apr 24, 2026·75 Views"
        "Access your post analytics Unlock advanced analytics with X PremiumLearn more111"
    )
    result = strip_tweet_stats(raw)
    assert result == "Contenido válido"


def test_strip_tweet_stats_formats_compact_poll_results():
    raw = (
        "Aella@Aella_Girl\n"
        "Imagine a circle. Where did it land?"
        "On the red 80.2%On the yellow19.8%"
        "7,864 votes·6 days left"
        "12:49 AM · Apr 26, 2026·397.2K Views3765014.2K875RelevantView quotes"
    )
    result = strip_tweet_stats(raw)
    assert result == "\n".join(
        [
            "Aella@Aella_Girl",
            "Imagine a circle. Where did it land?",
            "",
            "- On the red: 80.2%",
            "- On the yellow: 19.8%",
            "",
            "7,864 votes · 6 days left",
        ]
    )


def test_insert_quote_separator_adds_hr_before_quote():
    raw = "\n".join(
        [
            "Texto del tweet.",
            "Quote",
            "@autor",
            "Texto citado.",
        ]
    )
    result = _insert_quote_separator(raw)
    expected = "\n".join(
        [
            "Texto del tweet.",
            "",
            "---",
            "",
            "#### Tweet citado",
            "@autor",
            "Texto citado.",
        ]
    )
    assert result == expected


def test_insert_quote_separator_adds_quoted_link_after_hr():
    raw = "\n".join(
        [
            "Texto del tweet.",
            "Quote",
            "@autor",
            "Texto citado.",
        ]
    )
    result = _insert_quote_separator(raw, "https://x.com/i/web/status/999")
    expected = "\n".join(
        [
            "Texto del tweet.",
            "",
            "---",
            "[View quoted tweet](https://x.com/i/web/status/999)",
            "",
            "#### Tweet citado",
            "@autor",
            "Texto citado.",
        ]
    )
    assert result == expected


def test_insert_quote_separator_splits_inline_quote_card():
    raw = "\n".join(
        [
            "Texto del tweet.QuoteAutor Citado@autor·1hTexto citado.",
            "> línea citada",
            "",
            "[![image 1](https://example.com/img.jpg)](https://example.com/img.jpg)",
        ]
    )
    result = _insert_quote_separator(raw, "https://x.com/i/web/status/999")
    expected = "\n".join(
        [
            "Texto del tweet.",
            "",
            "---",
            "[View quoted tweet](https://x.com/i/web/status/999)",
            "",
            "#### Tweet citado",
            "",
            "Autor Citado@autor·1hTexto citado.",
            "línea citada",
            "",
            "[![image 1](https://example.com/img.jpg)](https://example.com/img.jpg)",
        ]
    )
    assert result == expected


def test_insert_quote_separator_ignores_inline_quote_word():
    raw = "Linea con quote en medio."
    assert _insert_quote_separator(raw) == raw


def test_insert_media_before_quote_places_block_before_hr():
    raw = "\n".join(
        [
            "Texto del tweet.",
            "",
            "---",
            "[View quoted tweet](https://x.com/i/web/status/999)",
            "",
            "#### Tweet citado",
            "Texto citado.",
        ]
    )
    media = ["[![image 1](https://example.com/img.jpg)](https://example.com/img.jpg)"]
    result = _insert_media_before_quote(raw, media)
    expected = "\n".join(
        [
            "Texto del tweet.",
            "",
            "[![image 1](https://example.com/img.jpg)](https://example.com/img.jpg)",
            "",
            "---",
            "[View quoted tweet](https://x.com/i/web/status/999)",
            "",
            "#### Tweet citado",
            "Texto citado.",
        ]
    )
    assert result == expected


def test_pick_quoted_tweet_url_skips_self_and_picks_next():
    hrefs = [
        "/user/status/12345",
        "https://x.com/other/status/999",
    ]
    assert (
        _pick_quoted_tweet_url(hrefs, "https://x.com/user/status/12345")
        == "https://x.com/other/status/999"
    )


def test_pick_quoted_tweet_url_accepts_i_web_status():
    hrefs = [
        "/user/status/12345",
        "/i/web/status/9876543210",
    ]
    assert (
        _pick_quoted_tweet_url(hrefs, "https://x.com/user/status/12345")
        == "https://x.com/i/web/status/9876543210"
    )


def test_has_quote_marker_detects_standalone_quote_line():
    raw = "\n".join(["Texto", "Quote", "Mas texto"])
    assert _has_quote_marker(raw) is True


def test_has_quote_marker_detects_inline_quote_card():
    raw = "Texto del tweet.QuoteAutor Citado@autor·1hTexto citado."
    assert _has_quote_marker(raw) is True


def test_status_id_from_url_handles_status_variants():
    assert _status_id_from_url("https://x.com/user/status/12345") == "12345"
    assert _status_id_from_url("https://x.com/i/web/status/987654") == "987654"
    assert _status_id_from_url("https://x.com/user") is None


def test_find_quoted_status_id_from_graphql():
    payload = {
        "data": {"tweetResult": {"quoted_status_id_str": "999"}},
    }
    assert _find_quoted_status_id(payload) == "999"


def test_find_quoted_status_id_from_quoted_result():
    payload = {
        "quoted_status_result": {
            "result": {"rest_id": "888"},
        }
    }
    assert _find_quoted_status_id(payload) == "888"


def test_quoted_url_from_graphql_id_skips_self():
    tweet_url = "https://x.com/user/status/123"
    assert _quoted_url_from_graphql_id("123", tweet_url) is None
    assert (
        _quoted_url_from_graphql_id("456", tweet_url)
        == "https://x.com/i/web/status/456"
    )


def test_emoji_from_twimg_url_decodes_composite_sequences():
    assert _emoji_from_twimg_url("https://abs-0.twimg.com/emoji/v2/svg/1f447.svg") == "👇"
    assert _emoji_from_twimg_url("https://abs.twimg.com/emoji/v2/svg/1f64f.svg") == "🙏"
    assert _emoji_from_twimg_url("https://abs-0.twimg.com/emoji/v2/svg/1f1ea-1f1fa.svg") == "🇪🇺"
    assert _emoji_from_twimg_url("https://abs-0.twimg.com/emoji/v2/svg/1f468-1f3fb-200d-1f4bb.svg") == "👨🏻‍💻"


def test_media_markdown_lines_include_direct_links():
    lines = _media_markdown_lines(
        [
            "https://pbs.twimg.com/media/img1?format=jpg",
            "https://abs-0.twimg.com/emoji/v2/svg/1f447.svg",
            "https://pbs.twimg.com/media/img2?format=jpg",
        ]
    )
    assert lines[0] == "[![image 1](https://pbs.twimg.com/media/img1?format=jpg)](https://pbs.twimg.com/media/img1?format=jpg)"
    assert lines[1] == "👇"
    assert lines[2] == "[![image 3](https://pbs.twimg.com/media/img2?format=jpg)](https://pbs.twimg.com/media/img2?format=jpg)"


def test_build_single_tweet_markdown_includes_external_link_without_media():
    parts = TweetParts(
        author_name="Autor",
        author_handle="@autor",
        body_text="Texto del tweet.",
        avatar_url=None,
        trailing_media_lines=[],
        media_present=False,
        external_link="https://example.com/post",
    )
    md = _build_single_tweet_markdown(parts, "https://x.com/autor/status/123")
    assert "Original link: https://example.com/post" in md


def test_build_single_tweet_markdown_skips_duplicate_external_link():
    parts = TweetParts(
        author_name="Autor",
        author_handle="@autor",
        body_text="Texto https://example.com/post/ con enlace.",
        avatar_url=None,
        trailing_media_lines=[],
        media_present=False,
        external_link="https://example.com/post",
    )
    md = _build_single_tweet_markdown(parts, "https://x.com/autor/status/123")
    assert "Original link: https://example.com/post" not in md


def test_build_thread_markdown_strips_repeated_author_headers():
    first = TweetParts(
        author_name="Jack Cole",
        author_handle="@MindsAI_Jack",
        body_text="Jack Cole\n@MindsAI_Jack\n1/ Humpty Dumpty sat on a wall.",
        avatar_url="https://pbs.twimg.com/profile_images/avatar_normal.jpg",
        trailing_media_lines=[],
        media_present=False,
        external_link=None,
    )
    second = TweetParts(
        author_name="Jack Cole",
        author_handle="@MindsAI_Jack",
        body_text="Jack Cole\n@MindsAI_Jack\n2/ The agent spun up 400 subagents.",
        avatar_url=None,
        trailing_media_lines=[],
        media_present=False,
        external_link=None,
    )

    md = _build_thread_markdown(
        [
            ("https://x.com/MindsAI_Jack/status/1", first),
            ("https://x.com/MindsAI_Jack/status/2", second),
        ],
        "https://x.com/MindsAI_Jack/status/2",
        first,
        author_handle="@MindsAI_Jack",
    )

    assert "# Thread by Jack Cole (@MindsAI_Jack)" in md
    assert md.count("Jack Cole\n@MindsAI_Jack") == 0
    assert "1/ Humpty Dumpty sat on a wall." in md
    assert "2/ The agent spun up 400 subagents." in md


def test_wait_for_tweet_detail_returns_payload():
    class FakeResponse:
        url = "https://x.com/i/api/graphql/xyz/TweetDetail"

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class FakeContext:
        def __init__(self, response):
            self.value = response

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _tb):
            return False

    class FakePage:
        def expect_response(self, predicate, timeout):
            resp = FakeResponse({"ok": True})
            assert predicate(resp)
            assert timeout == 123
            return FakeContext(resp)

    assert _wait_for_tweet_detail(FakePage(), 123) == {"ok": True}


def test_wait_for_tweet_detail_returns_none_on_timeout():
    class FakePage:
        def expect_response(self, predicate, timeout):
            raise PlaywrightTimeoutError("timeout")

    assert _wait_for_tweet_detail(FakePage(), 50) is None


def test_wait_for_tweet_detail_returns_none_on_bad_json():
    class FakeResponse:
        url = "https://x.com/i/api/graphql/xyz/TweetDetail"

        def json(self):
            raise ValueError("bad")

    class FakeContext:
        def __init__(self, response):
            self.value = response

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _tb):
            return False

    class FakePage:
        def expect_response(self, predicate, timeout):
            resp = FakeResponse()
            assert predicate(resp)
            return FakeContext(resp)

    assert _wait_for_tweet_detail(FakePage(), 100) is None


def test_expand_show_more_clicks_buttons_and_waits():
    clicked: list[int | None] = []
    waits: list[int] = []

    class FakeButton:
        def __init__(self, bucket):
            self.bucket = bucket

        def click(self, timeout=None):
            self.bucket.append(timeout)

    class FakeLocator:
        def __init__(self, count, bucket):
            self._count = count
            self._bucket = bucket

        def count(self):
            return self._count

        def nth(self, idx):
            return FakeButton(self._bucket)

    class FakeArticle:
        def get_by_role(self, role, name, exact):
            if role == "button" and name == "Show more" and exact:
                return FakeLocator(2, clicked)
            return FakeLocator(0, clicked)

        def locator(self, selector):
            raise AssertionError("fallback should not be used")

    class FakePage:
        def wait_for_timeout(self, wait_ms):
            waits.append(wait_ms)

    _expand_show_more(FakeArticle(), FakePage(), wait_ms=123)
    assert len(clicked) == 2
    assert waits == [123, 123]


def test_expand_show_more_ignores_non_button_text_nodes():
    clicked: list[int | None] = []
    waits: list[int] = []

    class FakeButton:
        def __init__(self, bucket):
            self.bucket = bucket

        def click(self, timeout=None):
            self.bucket.append(timeout)

    class FakeLocator:
        def __init__(self, count, bucket):
            self._count = count
            self._bucket = bucket

        def count(self):
            return self._count

        def nth(self, idx):
            return FakeButton(self._bucket)

    class FakeArticle:
        def get_by_role(self, role, name, exact):
            return FakeLocator(0, clicked)

        def locator(self, selector):
            if selector == 'text="Show more"':
                return FakeLocator(1, clicked)
            return FakeLocator(0, clicked)

    class FakePage:
        def wait_for_timeout(self, wait_ms):
            waits.append(wait_ms)

    _expand_show_more(FakeArticle(), FakePage(), wait_ms=50)
    assert len(clicked) == 0
    assert waits == []


def test_resolve_thread_context_prefers_context_metadata():
    result = _resolve_thread_context(
        context_author_handle="@like",
        context_time_text="2h",
        context_time_datetime="2026-01-10T12:00:00.000Z",
        target_author_handle="@target",
        target_time_text="1h",
        target_time_datetime="2026-01-10T13:00:00.000Z",
    )
    assert result == ("@like", "2h", "2026-01-10T12:00:00.000Z")


def test_resolve_thread_context_falls_back_to_target():
    result = _resolve_thread_context(
        context_author_handle=None,
        context_time_text=None,
        context_time_datetime=None,
        target_author_handle="@target",
        target_time_text="1h",
        target_time_datetime="2026-01-10T13:00:00.000Z",
    )
    assert result == ("@target", "1h", "2026-01-10T13:00:00.000Z")


def test_build_single_tweet_markdown_marks_capture_source():
    parts = TweetParts(
        author_name="Author",
        author_handle="@author",
        body_text="Tweet body.",
        avatar_url=None,
        trailing_media_lines=[],
        media_present=False,
        external_link=None,
    )

    md = _build_single_tweet_markdown(
        parts,
        "https://x.com/author/status/123",
        capture_source="posted",
    )

    assert "tweet_capture_source: posted" in md


def test_build_single_tweet_markdown_includes_reply_parent_context():
    parent = TweetParts(
        author_name="Parent",
        author_handle="@parent",
        body_text="Parent tweet.",
        avatar_url=None,
        trailing_media_lines=[],
        media_present=False,
        external_link=None,
    )
    reply = TweetParts(
        author_name="Author",
        author_handle="@author",
        body_text="Reply body.",
        avatar_url=None,
        trailing_media_lines=[],
        media_present=False,
        external_link=None,
    )

    md = _build_single_tweet_markdown(
        reply,
        "https://x.com/author/status/123",
        capture_source="posted",
        posted_kind="reply",
        reply_parent_context=ReplyParentContext(
            url="https://x.com/parent/status/99",
            parts=parent,
        ),
    )

    assert "tweet_posted_kind: reply" in md
    assert "tweet_reply_to_url: https://x.com/parent/status/99" in md
    assert "tweet_reply_context_included: true" in md
    assert "#### En respuesta a" in md
    assert "**Parent @parent**" in md
    assert "Parent tweet." in md
    assert "#### Mi respuesta" in md
    assert "Reply body." in md


def test_reply_parent_url_from_payload_uses_immediate_parent():
    payload = {
        "data": {
            "threaded_conversation_with_injections_v2": {
                "instructions": [
                    {
                        "entries": [
                            {
                                "content": {
                                    "itemContent": {
                                        "tweet_results": {
                                            "result": {
                                                "__typename": "Tweet",
                                                "rest_id": "123",
                                                "legacy": {
                                                    "in_reply_to_status_id_str": "99",
                                                    "in_reply_to_screen_name": "parent",
                                                },
                                            }
                                        }
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        }
    }

    url = _reply_parent_url_from_payload(payload, "https://x.com/author/status/123")

    assert url == "https://x.com/parent/status/99"


def test_build_filename_uses_posted_prefix_for_posted_source():
    filename = _build_filename(
        "https://x.com/author/status/123",
        "@author",
        capture_source="posted",
    )

    assert filename == "Tweet posted - author-123.md"


def test_read_article_text_retries_on_timeout(monkeypatch):
    calls = {"first": 0, "second": 0}

    class FakeArticle:
        def __init__(self, key):
            self.key = key

        def inner_text(self, timeout=None):
            calls[self.key] += 1
            if self.key == "first":
                raise PlaywrightTimeoutError("timeout")
            return "ok"

        def text_content(self, timeout=None):
            return None

        def evaluate(self, script):
            return "ok-eval"

    class FakePage:
        def wait_for_timeout(self, wait_ms):
            return None

    refreshed = FakeArticle("second")

    def fake_locate(page, tweet_url, timeout_ms=15000):
        assert tweet_url == "https://x.com/user/status/1"
        return refreshed

    monkeypatch.setattr("utils.tweet_to_markdown._locate_tweet_article", fake_locate)
    monkeypatch.setattr("utils.tweet_to_markdown._expand_show_more", lambda *args, **kwargs: None)

    result = _read_article_text(
        FakeArticle("first"),
        "https://x.com/user/status/1",
        page=FakePage(),
        timeout_ms=10,
    )
    assert result == "ok"
    assert calls == {"first": 1, "second": 1}


def test_read_article_text_uses_text_content_fallback():
    class FakeArticle:
        def inner_text(self, timeout=None):
            raise PlaywrightTimeoutError("timeout")

        def text_content(self, timeout=None):
            return "fallback"

        def evaluate(self, script):
            return "ok-eval"

    result = _read_article_text(
        FakeArticle(),
        "https://x.com/user/status/1",
        page=None,
        timeout_ms=10,
    )
    assert result == "fallback"


def test_read_article_text_uses_page_evaluate_fallback():
    class FakeArticle:
        def inner_text(self, timeout=None):
            raise PlaywrightTimeoutError("timeout")

        def text_content(self, timeout=None):
            raise PlaywrightTimeoutError("timeout")

        def evaluate(self, script):
            return "ok-eval"

    class FakePage:
        def locator(self, selector):
            assert selector == "a[href*='/status/1']"
            return FakeLocator()

    class FakeLocator:
        def __init__(self):
            self.first = self

        def evaluate(self, script):
            return "evaluated"

    result = _read_article_text(
        FakeArticle(),
        "https://x.com/user/status/1",
        page=FakePage(),
        timeout_ms=10,
    )
    assert result == "evaluated"


def test_read_article_text_uses_anchor_handle_first():
    class FakeArticle:
        def inner_text(self, timeout=None):
            raise PlaywrightTimeoutError("timeout")

        def text_content(self, timeout=None):
            return None

        def evaluate(self, script):
            return "ok-eval"

    class FakeHandle:
        def evaluate(self, script):
            return "from-handle"

    result = _read_article_text(
        FakeArticle(),
        "https://x.com/user/status/1",
        page=None,
        anchor_handle=FakeHandle(),
        timeout_ms=10,
    )
    assert result == "from-handle"


def test_read_article_text_prefers_richer_inner_text_over_compact_evaluations():
    class FakeArticle:
        def inner_text(self, timeout=None):
            return "line 1\nline 2 from page\nline 3 from inner text"

    class FakeHandle:
        def evaluate(self, script):
            return "compact-from-anchor"

    class FakeLocator:
        def __init__(self):
            self.first = self

        def evaluate(self, script):
            return "line 1\nline 2 from page"

    class FakePage:
        def locator(self, selector):
            assert selector == "a[href*='/status/1']"
            return FakeLocator()

    result = _read_article_text(
        FakeArticle(),
        "https://x.com/user/status/1",
        page=FakePage(),
        anchor_handle=FakeHandle(),
        timeout_ms=10,
    )
    assert result == "line 1\nline 2 from page\nline 3 from inner text"


def test_select_thread_indices_requires_context():
    entries = [("@user", "4h", None), ("@user", "4h", None)]
    assert _select_thread_indices(entries, 1, author_handle=None, time_text="4h", anchor_time_datetime=None) == [1]
    assert _select_thread_indices(entries, 1, author_handle="@user", time_text=None, anchor_time_datetime=None) == [1]


def test_select_thread_indices_collects_contiguous_matches():
    entries = [("@user", "4h", None), ("@user", "4h", None), ("@user", "4h", None)]
    assert _select_thread_indices(entries, 2, author_handle="@user", time_text="4h", anchor_time_datetime=None) == [0, 1, 2]


def test_select_thread_indices_stops_on_first_mismatch():
    entries = [("@user", "4h", None), ("@other", "4h", None), ("@user", "4h", None)]
    assert _select_thread_indices(entries, 2, author_handle="@user", time_text="4h", anchor_time_datetime=None) == [2]


def test_select_thread_indices_uses_datetime_window():
    entries = [
        ("@user", "32m", "2026-01-09T16:54:22.000Z"),
        ("@user", "27m", "2026-01-09T16:59:23.000Z"),
    ]
    selected = _select_thread_indices(
        entries,
        1,
        author_handle="@user",
        time_text="27m",
        anchor_time_datetime="2026-01-09T16:59:23.000Z",
    )
    assert selected == [0, 1]


def test_select_thread_indices_respects_datetime_window_limit():
    entries = [
        ("@user", "2d", "2026-01-07T10:00:00.000Z"),
        ("@user", "1h", "2026-01-09T12:30:00.000Z"),
    ]
    selected = _select_thread_indices(
        entries,
        1,
        author_handle="@user",
        time_text="1h",
        anchor_time_datetime="2026-01-09T12:30:00.000Z",
    )
    assert selected == [1]


def test_extract_thread_ids_from_payload_filters_author_and_time():
    payload = {
        "data": {
            "threaded_conversation_with_injections_v2": {
                "instructions": [
                    {
                        "type": "TimelineAddEntries",
                        "entries": [
                            {
                                "entryId": "tweet-1",
                                "content": {
                                    "itemContent": {
                                        "tweet_results": {
                                            "result": {
                                                "__typename": "Tweet",
                                                "rest_id": "111",
                                                "core": {
                                                    "user_results": {
                                                        "result": {
                                                            "core": {
                                                                "screen_name": "author",
                                                            }
                                                        }
                                                    }
                                                },
                                                "legacy": {
                                                    "created_at": "Thu Jan 08 10:00:00 +0000 2026"
                                                },
                                            }
                                        }
                                    }
                                },
                            },
                            {
                                "entryId": "tweet-2",
                                "content": {
                                    "itemContent": {
                                        "tweet_results": {
                                            "result": {
                                                "__typename": "Tweet",
                                                "rest_id": "222",
                                                "core": {
                                                    "user_results": {
                                                        "result": {
                                                            "core": {
                                                                "screen_name": "other",
                                                            }
                                                        }
                                                    }
                                                },
                                                "legacy": {
                                                    "created_at": "Thu Jan 08 11:00:00 +0000 2026"
                                                },
                                            }
                                        }
                                    }
                                },
                            },
                        ],
                    }
                ]
            }
        }
    }
    ids = _extract_thread_ids_from_payload(
        payload,
        author_handle="@author",
        anchor_time_datetime="2026-01-08T12:00:00.000Z",
    )
    assert ids == ["111"]


def test_detect_access_issue_flags_login_url():
    class FakeLocator:
        def __init__(self, count=0):
            self._count = count

        def count(self):
            return self._count

    class FakePage:
        def __init__(self, url):
            self.url = url

        def locator(self, selector):
            return FakeLocator(0)

    page = FakePage("https://x.com/i/flow/login")
    assert _detect_access_issue(page) == "X requires login (login wall)."


def test_detect_access_issue_flags_unavailable_text():
    class FakeLocator:
        def __init__(self, count=0):
            self._count = count

        def count(self):
            return self._count

    class FakePage:
        def __init__(self, hits):
            self.url = "https://x.com/someone/status/1"
            self._hits = hits

        def locator(self, selector):
            return FakeLocator(self._hits.get(selector, 0))

    page = FakePage({"text=This Post is unavailable": 1})
    assert (
        _detect_access_issue(page)
        == "Tweet unavailable (deleted, protected, or restricted)."
    )
