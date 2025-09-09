/* Minimal base JS for /read/ pages
 * - No visual changes
 * - Allows console verification: ArticleJS.active / ArticleJS.ping()
 */
(function () {
  var version = '0.1.0';
  var api = Object.freeze({
    active: true,
    version: version,
    ping: function () { return 'ok'; }
  });
  try {
    Object.defineProperty(window, 'ArticleJS', {
      value: api,
      enumerable: true,
      configurable: false,
      writable: false
    });
  } catch (e) {
    // Fallback if defineProperty is not allowed
    window.ArticleJS = api;
  }
  // Console-only signal; no UI changes
  if (typeof console !== 'undefined' && console.debug) {
    console.debug('[article-js] active', version);
  }
})();

