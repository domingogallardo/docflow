"""Summary propagation and browser interactions for the shared list preview."""
import json
from pathlib import Path

import pytest

from utils import build_browse_index as browse, build_reading_index as reading, build_done_index as done
from utils.article_preview import summary_for_path
from utils.site_state import save_reading_state, save_done_state


def test_summary_reaches_all_lists_and_search_without_content_writes(tmp_path):
    posts = tmp_path / 'Posts' / 'Posts 2026'
    posts.mkdir(parents=True)
    path = posts / 'Article.html'
    path.write_text('<p>Article</p>')
    md = path.with_suffix('.md')
    summary = 'Names <tools> & "details".'
    md.write_text('---\ndocflow_summary: ' + summary + '\n---\nBody')
    original = md.read_bytes(), md.stat().st_mtime_ns
    browse.build_browse_site(tmp_path)
    from bs4 import BeautifulSoup
    page = tmp_path / '_site/browse/posts/Posts 2026/index.html'
    link = BeautifulSoup(page.read_text(), 'html.parser').select_one('a[data-dg-summary]')
    assert link['data-dg-summary'] == summary
    payload = json.loads((tmp_path / '_site/search-index.json').read_text())
    assert payload['entries'][0]['summary'] == summary
    rel = path.relative_to(tmp_path).as_posix()
    save_reading_state(tmp_path, {'items': {rel: {}}})
    save_done_state(tmp_path, {'items': {rel: {}}})
    for writer in (reading.write_site_reading_index, done.write_site_done_index):
        output = writer(tmp_path)
        soup = BeautifulSoup(output.read_text(), 'html.parser')
        assert soup.select_one('a[data-dg-summary]')['data-dg-summary'] == summary
        assert soup.select_one('script[src*="article-preview.js"]')
    history = browse._history_entry_from_position(tmp_path, {'path': rel, 'updated_at': '2026-11-03T10:00:00Z'})
    assert history[1]['summary'] == summary
    assert (md.read_bytes(), md.stat().st_mtime_ns) == original
    assert summary_for_path(posts / 'missing.html') == ''


@pytest.fixture(params=['chromium', 'webkit'])
def page(request):
    playwright = pytest.importorskip('playwright.sync_api')
    with playwright.sync_playwright() as p:
        browser_type = getattr(p, request.param)
        if not Path(browser_type.executable_path).exists():
            pytest.skip(f'{request.param} is not installed')
        browser = browser_type.launch()
        context = browser.new_context(viewport={'width': 390, 'height': 700}, has_touch=True, is_mobile=True)
        page = context.new_page()
        page.set_content('<meta name="viewport" content="width=device-width, initial-scale=1"><a id="article" href="#opened" data-dg-summary="Saved &lt;summary&gt;">Article</a><a id="empty" href="#empty">No summary</a><div style="height:1800px"></div>')
        page.add_style_tag(path='utils/static/article-preview.css')
        page.add_script_tag(path='utils/static/article-preview.js')
        # Let the mobile visual viewport settle before beginning a gesture.
        page.wait_for_timeout(150)
        yield page
        browser.close()


def pointer(page, event, **kwargs):
    page.locator('#article').dispatch_event(event, {'pointerType': 'touch', 'pointerId': 1, 'isPrimary': True, 'clientX': 20, 'clientY': 20, **kwargs})


def test_hover_delay_escape_and_safe_text(page):
    page.locator('#article').hover()
    page.wait_for_timeout(250)
    assert page.locator('[data-dg-article-preview]').is_hidden()
    page.wait_for_timeout(220)
    assert page.locator('[data-dg-article-preview] strong').inner_text() == 'Article'
    assert page.locator('[data-dg-article-preview] p').inner_text() == 'Saved <summary>'
    assert page.locator('[data-dg-article-preview] summary').count() == 0
    box = page.locator('[data-dg-article-preview]').bounding_box()
    assert box['x'] >= 0 and box['x'] + box['width'] <= 390
    page.keyboard.press('Escape')
    assert page.locator('[data-dg-article-preview]').is_hidden()


def test_touch_tap_hold_and_next_tap(page):
    page.locator('#article').tap()
    assert page.url.endswith('#opened')
    page.evaluate("history.replaceState(null, '', '#start')")
    pointer(page, 'pointerdown')
    page.wait_for_timeout(450)
    assert page.locator('[data-dg-article-preview]').is_visible()
    pointer(page, 'pointerup')
    page.locator('#article').dispatch_event('click', {'detail': 1})
    assert page.url.endswith('#start')
    page.locator('#article').tap()
    assert page.url.endswith('#opened')


@pytest.mark.parametrize('cancel_event', ['move', 'pointercancel', 'scroll', 'multitouch'])
def test_native_gestures_cancel_preview_without_preventing_default(page, cancel_event):
    pointer(page, 'pointerdown')
    if cancel_event == 'move':
        pointer(page, 'pointermove', clientY=45)
    elif cancel_event == 'multitouch':
        page.evaluate("(() => { const event = new Event('touchstart', {bubbles:true, cancelable:true}); Object.defineProperty(event, 'touches', {value:[{},{}]}); return document.dispatchEvent(event); })()")
    elif cancel_event == 'scroll':
        page.evaluate('window.scrollTo(0, 100)')
    else:
        pointer(page, cancel_event)
    page.wait_for_timeout(450)
    assert page.locator('[data-dg-article-preview]').is_hidden()
    pointer(page, 'pointerup')
    page.locator('#article').dispatch_event('click', {'detail': 1})
    assert page.url.endswith('#opened')


def test_delegated_search_results_and_keyboard(page):
    page.evaluate("document.body.insertAdjacentHTML('afterbegin', '<a id=dynamic href=#result data-dg-summary=Result>Search result</a>')")
    page.locator('#dynamic').focus()
    page.wait_for_timeout(450)
    assert page.locator('[data-dg-article-preview] strong').inner_text() == 'Search result'
    assert page.locator('[data-dg-article-preview] p').inner_text() == 'Result'
    page.keyboard.press('Enter')
    assert page.url.endswith('#result')


def test_no_preview_for_missing_summary_and_native_styles(page):
    page.locator('#empty').hover()
    page.wait_for_timeout(450)
    assert page.locator('[data-dg-article-preview]').is_hidden()
    styles = page.locator('#article').evaluate("el => { const s = getComputedStyle(el); return {touch: s.touchAction, select: (s.userSelect || s.webkitUserSelect), callout: s.webkitTouchCallout}; }")
    assert styles['touch'] == 'auto'
    assert styles['select'] == 'none'
    empty_styles = page.locator('#empty').evaluate("el => { const s = getComputedStyle(el); return {select:(s.userSelect || s.webkitUserSelect), callout:s.webkitTouchCallout}; }")
    assert empty_styles['select'] != 'none'
    assert empty_styles.get('callout') != 'none'
    if page.evaluate("CSS.supports('-webkit-touch-callout', 'none')"):
        assert styles['callout'] == 'none'


def test_real_search_renderer_supplies_summary(page):
    # Exercise the actual Home renderer, including async index loading and escaping.
    page.route('http://docflow.test/**', lambda route: route.fulfill(
        content_type='application/json' if route.request.url.endswith('.json') else 'text/html',
        body=json.dumps({'entries': [{'name':'Article.html','stem':'Article','href':'#article','folder':'Posts','summary':'Saved <summary>'}]}) if route.request.url.endswith('.json') else '<meta name="viewport" content="width=device-width">' + browse._search_controls_html() + browse._search_result_html() + browse._search_script_html(),
    ))
    page.goto('http://docflow.test/')
    page.add_style_tag(path='utils/static/article-preview.css')
    page.add_script_tag(path='utils/static/article-preview.js')
    page.locator('[data-dg-search-input]').fill('Article')
    page.locator('[data-dg-search-form]').evaluate('el => el.requestSubmit()')
    result = page.locator('.dg-search-results a')
    result.wait_for()
    assert result.get_attribute('data-dg-summary') == 'Saved <summary>'
    result.hover()
    page.wait_for_timeout(450)
    assert page.locator('[data-dg-article-preview] p').inner_text() == 'Saved <summary>'


def test_touch_context_menu_keeps_custom_preview_and_desktop_menu_native(page):
    pointer(page, 'pointerdown')
    page.wait_for_timeout(450)
    assert page.locator('[data-dg-article-preview]').is_visible()
    # Safari callout suppression is CSS; this handles touch contextmenu events
    # on browsers that also emit them, without changing desktop right-click.
    assert not page.locator('#article').evaluate("el => el.dispatchEvent(new PointerEvent('contextmenu', {bubbles:true, cancelable:true, pointerType:'touch'}))")
    assert page.locator('[data-dg-article-preview]').is_visible()
    pointer(page, 'pointerup')
    assert page.locator('#article').evaluate("el => el.dispatchEvent(new PointerEvent('contextmenu', {bubbles:true, cancelable:true, pointerType:'mouse'}))")
    assert page.locator('[data-dg-article-preview]').is_hidden()
    assert page.locator('#empty').evaluate("el => el.dispatchEvent(new PointerEvent('contextmenu', {bubbles:true, cancelable:true, pointerType:'touch'}))")


def test_touch_styles_do_not_affect_desktop_or_no_javascript(page):
    desktop = page.context.browser.new_page(has_touch=False, is_mobile=False)
    desktop.set_content('<a href=# data-dg-summary=Summary>Article</a>')
    desktop.add_style_tag(path='utils/static/article-preview.css')
    desktop.add_script_tag(path='utils/static/article-preview.js')
    assert desktop.locator('a[data-dg-summary]').evaluate('el => getComputedStyle(el).userSelect') != 'none'
    desktop.close()
    page.evaluate("document.documentElement.classList.remove('dg-summary-previews')")
    assert page.locator('#article').evaluate('el => getComputedStyle(el).userSelect') != 'none'


def test_search_hold_does_not_turn_into_text_selection(page):
    page.evaluate("""document.body.insertAdjacentHTML('afterbegin',
      '<ul class="dg-search-results"><li><a id="result" href="#result" data-dg-summary="Saved summary">Result</a> <span class="dg-search-folder">Posts 2026</span></li></ul>')""")
    link = page.locator('#result')
    link.dispatch_event('pointerdown', {'pointerType':'touch', 'pointerId':1, 'isPrimary':True})
    page.wait_for_timeout(500)
    assert page.locator('[data-dg-article-preview]').is_visible()
    for selector in ['.dg-search-folder', '[data-dg-article-preview] p']:
        element = page.locator(selector)
        styles = element.evaluate("el => { const s=getComputedStyle(el); return {select:s.userSelect || s.webkitUserSelect,touch:s.touchAction}; }")
        assert styles['select'] == 'none'
        assert styles['touch'] == 'auto'
        assert not element.evaluate("el => el.dispatchEvent(new Event('selectstart', {bubbles:true,cancelable:true}))")
        # Model Safari selecting a text node despite CSS during an active hold.
        element.evaluate("""el => { const range=document.createRange(); range.selectNodeContents(el);
          const selection=getSelection(); selection.removeAllRanges(); selection.addRange(range);
          document.dispatchEvent(new Event('selectionchange')); }""")
        assert page.evaluate('getSelection().isCollapsed')
        assert page.locator('[data-dg-article-preview]').is_visible()
    link.dispatch_event('pointerup', {'pointerType':'touch', 'pointerId':1, 'isPrimary':True})
    link.dispatch_event('click', {'detail':1})
    assert not page.url.endswith('#result')
    link.tap()
    assert page.url.endswith('#result')
    assert page.locator('#empty').evaluate("el => el.dispatchEvent(new Event('selectstart', {bubbles:true,cancelable:true}))")


@pytest.mark.parametrize('mode', ['mouse', 'touch', 'keyboard'])
def test_preview_title_opens_article(page, mode):
    if mode == 'mouse':
        page.locator('#article').hover()
    elif mode == 'keyboard':
        page.locator('#article').focus()
    else:
        # iOS blurs the search input with relatedTarget=null when tapping a link.
        page.evaluate("const input=document.createElement('input'); document.body.prepend(input); input.focus();")
        page.wait_for_timeout(150)
        pointer(page, 'pointerdown')
    page.wait_for_timeout(500)
    title = page.locator('[data-dg-article-preview] strong a')
    assert title.get_attribute('href').endswith('#opened')
    if mode == 'touch':
        pointer(page, 'pointerup')
        title.tap()
    elif mode == 'keyboard':
        page.keyboard.press('Tab')
        assert title.evaluate('el => el === document.activeElement')
        assert title.is_visible()
        page.keyboard.press('Enter')
    else:
        title.click()
    assert page.url.endswith('#opened')


def test_tapping_summary_text_dismisses_card_without_navigation(page):
    pointer(page, 'pointerdown')
    page.wait_for_timeout(500)
    pointer(page, 'pointerup')
    # Releasing the hold over the newly shown text must not dismiss it.
    body = page.locator('[data-dg-article-preview] p')
    body.dispatch_event('click', {'detail':1})
    assert body.is_visible()
    body.tap()
    assert page.locator('[data-dg-article-preview]').is_hidden()
    assert not page.url.endswith('#opened')


def test_scroll_within_long_preview_keeps_card_and_reopens_at_title(page):
    page.locator('#article').evaluate("el => el.dataset.dgSummary = 'Long summary. '.repeat(500)")
    pointer(page, 'pointerdown')
    page.wait_for_timeout(500)
    pointer(page, 'pointerup')
    card = page.locator('[data-dg-article-preview]')
    card.evaluate('el => el.scrollTop = 100')
    page.wait_for_timeout(150)
    assert card.is_visible()
    page.keyboard.press('Escape')
    pointer(page, 'pointerdown')
    page.wait_for_timeout(500)
    pointer(page, 'pointerup')
    assert card.evaluate('el => el.scrollTop') == 0
    page.locator('[data-dg-article-preview] strong a').tap()
    assert page.url.endswith('#opened')
