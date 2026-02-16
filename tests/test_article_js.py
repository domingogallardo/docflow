def test_build_read_index_includes_article_js():
    import importlib.util, pathlib
    path = pathlib.Path('utils/build_read_index.py')
    spec = importlib.util.spec_from_file_location('build_read_index', path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore
    html = mod.build_site_read_html([])
    assert '<script src="/read/article.js" defer></script>' in html


def test_article_js_includes_highlights():
    import pathlib
    content = pathlib.Path('utils/static/article.js').read_text(encoding='utf-8')
    assert 'articlejs-highlight-btn' in content
    assert '/api/highlights?path=' in content
    assert '/data/highlights/' not in content
    assert 'articlejs-reading-type-style' in content
