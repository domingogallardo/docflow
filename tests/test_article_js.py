def test_browse_assets_include_article_js(tmp_path):
    from pathlib import Path

    from utils import build_browse_index

    base = tmp_path / "base"
    base.mkdir()

    build_browse_index.ensure_assets(base)

    article_js = base / "_site" / "assets" / "article.js"
    assert article_js.exists()
    assert "articlejs-reading-type-style" in article_js.read_text(encoding="utf-8")


def test_article_js_includes_highlights():
    import pathlib
    content = pathlib.Path('utils/static/article.js').read_text(encoding='utf-8')
    assert 'articlejs-highlight-btn' in content
    assert '/api/highlights?path=' in content
    assert '/api/reading-position?path=' in content
    assert 'nextHighlight: nextHighlight' in content
    assert 'previousHighlight: previousHighlight' in content
    assert 'getHighlightProgress: getHighlightProgress' in content
    assert 'focusHighlightById: focusHighlightById' in content
    assert 'restoreReadingPosition' in content
    assert 'installReadingPositionTracking' in content
    assert "window.addEventListener('pagehide'" in content
    assert "hash.indexOf('hl=') === 0" in content
    assert 'articlejs:highlight-progress' in content
    assert '.articlejs-highlight.articlejs-highlight-active {' not in content
    assert 'box-shadow: 0 0 0 2px rgba(190, 126, 0, 0.35);' not in content
    assert 'padding: 0;' in content
    assert 'padding: 0 2px;' not in content
    assert '/data/highlights/' not in content
    assert 'articlejs-reading-type-style' in content
    assert "closest('a.image-zoom')" in content
    assert "querySelectorAll('img')" in content
    assert 'img.currentSrc' in content
    assert 'getTimezoneOffset' in content
    assert "toISOString().slice(0, -1)" in content
