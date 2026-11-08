"""Browser regressions for optional summary matching in Home search."""
import json
from pathlib import Path

import pytest

from utils import build_browse_index as browse


@pytest.fixture(params=['chromium', 'webkit'])
def search_page(request):
    playwright = pytest.importorskip('playwright.sync_api')
    entries = [
        {'name': 'Gardens.html', 'stem': 'Gardens', 'summary': 'Ética and robotics in Madrid.', 'category': 'posts', 'href': '#gardens'},
        {'name': 'Robotics.html', 'stem': 'Robotics', 'category': 'posts', 'href': '#robotics'},
        {'name': 'Tweet.html', 'stem': 'Tweet', 'summary': 'Robotics in Madrid.', 'category': 'tweets', 'href': '#tweet'},
        {'name': 'House.html', 'stem': 'House', 'summary': '', 'category': 'posts', 'href': '#house'},
    ]
    with playwright.sync_playwright() as p:
        engine = getattr(p, request.param)
        if not Path(engine.executable_path).exists():
            pytest.skip(f'{request.param} is not installed')
        browser = engine.launch()
        page = browser.new_page(viewport={'width': 390, 'height': 700}, is_mobile=True, has_touch=True)
        html = browse._base_head('Search') + '<body>' + browse._search_controls_html() + browse._search_result_html() + browse._search_script_html() + '</body></html>'
        page.route('http://docflow.test/**', lambda route: route.fulfill(
            content_type='application/json' if route.request.url.endswith('.json') else 'text/html',
            body=json.dumps({'entries': entries}) if route.request.url.endswith('.json') else html,
        ))
        # Assets are unnecessary here; exercise the real generated styles and search script.
        page.route('**/assets/**', lambda route: route.fulfill(body=''))
        page.goto('http://docflow.test/')
        yield page, playwright.expect
        browser.close()


def search(page, query):
    page.locator('[data-dg-search-input]').fill(query)
    page.locator('[data-dg-search-form]').evaluate('form => form.requestSubmit()')


def test_summary_opt_in_and_immediate_results(search_page):
    page, expect = search_page
    toggle = page.locator('[data-dg-search-summaries]')
    expect(toggle).not_to_be_checked()
    search(page, 'Madrid')
    expect(page.locator('[data-dg-search-hit]')).to_have_text('No matching documents found.')
    toggle.check()
    expect(page.locator('.dg-search-results a')).to_have_text(['Gardens.html', 'Tweet.html'])
    expect(page.locator('[data-dg-search-input]')).to_have_attribute('placeholder', 'Search titles and summaries or term + term')
    toggle.uncheck()
    expect(page.locator('.dg-search-results a')).to_have_count(0)
    search(page, 'Robotics')
    expect(page.locator('.dg-search-results a')).to_have_text(['Robotics.html'])


def test_combined_terms_tweets_and_missing_summaries(search_page):
    page, expect = search_page
    page.locator('[data-dg-search-summaries]').check()
    search(page, 'Gardens + Madrid')
    expect(page.locator('.dg-search-results a')).to_have_text(['Gardens.html'])
    search(page, 'Robotics')
    expect(page.locator('.dg-search-results a')).to_have_count(3)
    page.locator('[data-dg-search-tweets]').uncheck()
    expect(page.locator('.dg-search-results a')).to_have_text(['Gardens.html', 'Robotics.html'])
    search(page, 'House')
    expect(page.locator('.dg-search-results a')).to_have_text(['House.html'])
    search(page, 'Robotics + absent')
    expect(page.locator('.dg-search-results a')).to_have_count(0)


def test_checkbox_state_survives_reload_independently(search_page):
    page, expect = search_page
    page.locator('[data-dg-search-summaries]').check()
    page.locator('[data-dg-search-tweets]').uncheck()
    search(page, 'Madrid')
    expect(page.locator('.dg-search-results a')).to_have_text(['Gardens.html'])
    page.reload()
    expect(page.locator('[data-dg-search-summaries]')).to_be_checked()
    expect(page.locator('[data-dg-search-tweets]')).not_to_be_checked()
    expect(page.locator('.dg-search-results a')).to_have_text(['Gardens.html'])


def test_unicode_boundaries_and_mobile_controls(search_page):
    page, expect = search_page
    page.locator('[data-dg-search-summaries]').check()
    search(page, 'ÉTICA')
    expect(page.locator('.dg-search-results a')).to_have_text(['Gardens.html'])
    search(page, 'robot')
    expect(page.locator('.dg-search-results a')).to_have_count(0)
    # The added checkbox must remain inside the narrow viewport.
    for selector in ['[data-dg-search-input]', '[data-dg-search-summaries]', '[data-dg-search-button]']:
        box = page.locator(selector).bounding_box()
        assert box['x'] >= 0 and box['x'] + box['width'] <= 390
