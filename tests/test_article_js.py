def test_build_working_index_includes_article_js():
    import importlib.util, pathlib
    path = pathlib.Path('utils/build_working_index.py')
    spec = importlib.util.spec_from_file_location('build_working_index', path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore
    html = mod.build_site_working_html([])
    assert '<script src="/working/article.js" defer></script>' in html


def test_article_js_includes_highlights():
    import pathlib
    content = pathlib.Path('utils/static/article.js').read_text(encoding='utf-8')
    assert 'articlejs-highlight-btn' in content
    assert '/api/highlights?path=' in content
    assert 'nextHighlight: nextHighlight' in content
    assert 'previousHighlight: previousHighlight' in content
    assert 'getHighlightProgress: getHighlightProgress' in content
    assert 'articlejs:highlight-progress' in content
    assert 'articlejs-highlight-active' in content
    assert '/data/highlights/' not in content
    assert 'articlejs-reading-type-style' in content
