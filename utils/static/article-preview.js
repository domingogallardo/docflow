/* One delegated preview for static lists, search results and History.
 * Touch holds on summary titles belong to this preview; scrolling and zoom stay native.
 */
(() => {
  'use strict';
  const selector = 'a[data-dg-summary]';
  const card = document.createElement('div');
  card.className = 'dg-article-preview';
  card.id = 'dg-article-preview';
  card.setAttribute('role', 'region');
  card.setAttribute('aria-label', 'Article preview');
  card.setAttribute('data-dg-article-preview', '');
  card.hidden = true;
  const title = document.createElement('strong');
  const titleLink = document.createElement('a');
  title.append(titleLink);
  const body = document.createElement('p');
  // A direct listener also makes this text tappable in Mobile Safari.
  body.addEventListener('click', cancel);
  card.append(title, body);
  document.body.append(card);
  let timer, anchor = null, touch = null, blockedClick = null, blockTimer, pressingCard = false;

  function linkAt(target) {
    const link = target instanceof Element ? target.closest(selector) : null;
    return link && link.dataset.dgSummary.trim() ? link : null;
  }
  function hide() {
    clearTimeout(timer);
    if (anchor) {
      const ids = (anchor.getAttribute('aria-describedby') || '').split(/\s+/).filter(id => id && id !== card.id);
      if (ids.length) anchor.setAttribute('aria-describedby', ids.join(' '));
      else anchor.removeAttribute('aria-describedby');
    }
    anchor = null;
    card.hidden = true;
  }
  function cancel() { touch = null; pressingCard = false; hide(); }
  function position() {
    if (!anchor || !anchor.isConnected) { hide(); return; }
    const rect = anchor.getBoundingClientRect();
    const viewport = window.visualViewport;
    const left = viewport ? viewport.offsetLeft : 0;
    const top = viewport ? viewport.offsetTop : 0;
    const width = viewport ? viewport.width : innerWidth;
    const height = viewport ? viewport.height : innerHeight;
    card.style.maxWidth = `${Math.max(0, width - 24)}px`;
    card.style.maxHeight = `${Math.max(0, height - 24)}px`;
    const size = card.getBoundingClientRect();
    card.style.left = `${Math.max(left + 12, Math.min(rect.left, left + width - size.width - 12))}px`;
    const below = rect.bottom + 8;
    card.style.top = `${Math.max(top + 12, below + size.height <= top + height - 12 ? below : rect.top - size.height - 8)}px`;
  }
  function show(link) {
    if (!link.isConnected || !link.dataset.dgSummary.trim()) return;
    anchor = link;
    titleLink.textContent = link.textContent;
    titleLink.setAttribute('href', link.getAttribute('href'));
    body.textContent = link.dataset.dgSummary;
    const ids = (link.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
    if (!ids.includes(card.id)) ids.push(card.id);
    link.setAttribute('aria-describedby', ids.join(' '));
    card.hidden = false;
    card.scrollTop = 0;
    position();
  }
  function schedule(link) { hide(); timer = setTimeout(() => show(link), 400); }

  document.addEventListener('pointerover', event => {
    const link = linkAt(event.target);
    if (event.pointerType === 'mouse' && link && !link.contains(event.relatedTarget)) schedule(link);
  });
  document.addEventListener('pointerout', event => {
    if (event.pointerType !== 'mouse') return;
    const link = linkAt(event.target);
    if (link && !link.contains(event.relatedTarget) && !card.contains(event.relatedTarget)) {
      clearTimeout(timer);
      timer = setTimeout(hide, 150);
    }
  });
  card.addEventListener('pointerenter', () => clearTimeout(timer));
  card.addEventListener('pointerleave', event => {
    if (event.pointerType !== 'mouse') return;
    if (!anchor || !anchor.contains(event.relatedTarget)) hide();
  });
  document.addEventListener('focusin', event => { const link = linkAt(event.target); if (link && link.matches(':focus-visible')) schedule(link); });
  document.addEventListener('focusout', event => {
    if (pressingCard) return;
    if (card.contains(event.relatedTarget) || (anchor && anchor.contains(event.relatedTarget))) return;
    hide();
  });
  document.addEventListener('pointerdown', event => {
    clearTimeout(blockTimer);
    blockedClick = null;
    pressingCard = card.contains(event.target);
    if (pressingCard) return;
    cancel();
    const link = linkAt(event.target);
    if (!link || event.pointerType === 'mouse' || !event.isPrimary) return;
    touch = {id: event.pointerId, x: event.clientX, y: event.clientY, link, shown: false};
    timer = setTimeout(() => {
      if (!touch) return;
      touch.shown = true;
      show(link);
    }, 400);
  }, {passive: true});
  document.addEventListener('pointermove', event => {
    if (touch && event.pointerId === touch.id && Math.hypot(event.clientX - touch.x, event.clientY - touch.y) > 10) cancel();
  }, {passive: true});
  document.addEventListener('pointerup', event => {
    if (!touch || event.pointerId !== touch.id) return;
    clearTimeout(timer);
    if (touch.shown) {
      blockedClick = touch.link;
      blockTimer = setTimeout(() => { blockedClick = null; }, 800);
    }
    touch = null;
  }, {passive: true});
  // Cancel only the compatibility click belonging to a completed custom hold.
  document.addEventListener('click', event => {
    if (blockedClick && (linkAt(event.target) === blockedClick || card.contains(event.target)) && event.detail !== 0) {
      event.preventDefault();
      event.stopPropagation();
      blockedClick = null;
      pressingCard = false;
      return;
    }
    if (card.contains(event.target) && !event.target.closest('a')) cancel();
    pressingCard = false;
  }, true);
  document.addEventListener('pointercancel', cancel, {passive: true});
  // Only touch holds on summary titles replace the browser's link menu.
  // Keep desktop right-clicks and all other links native.
  document.addEventListener('contextmenu', event => {
    const link = linkAt(event.target);
    if (link && ((touch && touch.link === link) ||
        (event.pointerType === 'touch' && anchor === link))) {
      event.preventDefault();
      return;
    }
    cancel();
  });
  document.addEventListener('dragstart', event => {
    if (touch && linkAt(event.target) === touch.link) event.preventDefault();
    else cancel();
  });
  function selectionSurface(target) {
    if (!target) return false;
    if (!(target instanceof Element)) target = target.parentElement;
    if (!target) return false;
    if (card.contains(target)) return true;
    const row = target.closest('.dg-search-results li');
    return !!(row && Array.from(row.querySelectorAll(selector)).some(link => linkAt(link)));
  }
  // A hold can select the result's folder label or the card that appears under
  // the finger. Suppress selection there, without cancelling touchmove/zoom.
  document.addEventListener('selectstart', event => {
    if (window.matchMedia('(any-pointer: coarse)').matches && selectionSurface(event.target)) {
      event.preventDefault();
    }
  });
  document.addEventListener('selectionchange', () => {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) return;
    if (touch && touch.shown && anchor) {
      const row = anchor.closest('.dg-search-results li') || anchor;
      if (selection.containsNode(row, true) || selection.containsNode(card, true) ||
          selectionSurface(selection.anchorNode) || selectionSurface(selection.focusNode)) {
        selection.removeAllRanges();
        return;
      }
    }
    cancel();
  });
  document.addEventListener('touchstart', event => { if (event.touches.length > 1) cancel(); }, {passive: true});
  document.addEventListener('keydown', event => {
    pressingCard = false;
    if (event.key === 'Escape') cancel();
    if (event.key === 'Tab' && !card.hidden) {
      if (!event.shiftKey && event.target === anchor) {
        event.preventDefault();
        titleLink.focus();
      } else if (event.shiftKey && event.target === titleLink && anchor) {
        event.preventDefault();
        anchor.focus();
      }
    }
  });
  document.addEventListener('scroll', event => {
    if (!card.contains(event.target)) cancel();
  }, {capture: true, passive: true});
  window.addEventListener('resize', cancel);
  window.addEventListener('blur', cancel);
  window.addEventListener('pagehide', cancel);
  document.addEventListener('visibilitychange', cancel);
  document.documentElement.classList.add('dg-summary-previews');
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', cancel);
    window.visualViewport.addEventListener('scroll', cancel);
  }
})();
