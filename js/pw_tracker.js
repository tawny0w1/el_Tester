// Playwright tracker for the LEFT window. Needs xpath.js before it.
// Installed with context.add_init_script, so it runs in every page load and
// in every frame (cross-origin ones too): no re-injection, no listenInFrames.
// Each action is pushed to Python through the reportAction binding
// (page.expose_binding), instead of sessionStorage + polling.
// Python adds the iframe path itself, from the frame that called it.

// Clicks. Links are not blocked: the right window clicks its own link at the
// same XPath, so it opens its own href.
document.addEventListener('click', function (event) {
    var target = event.target.closest('a, button, input[type="checkbox"], input[type="radio"], .flashcard, .quiz-multiple-choice-option__input');
    if (target) {
        // name: for the bug report if the right has no such element
        window.reportAction({type: 'click', xpath: getXPath(target), name: getElementName(target)});
    }
}, true);

// Typing and dropdown changes. Checkboxes and radios are synced as clicks.
document.addEventListener('input', function (event) {
    var t = event.target;
    if (t.type === 'checkbox' || t.type === 'radio') return;
    window.reportAction({type: 'input', xpath: getXPath(t), value: t.value});
}, true);

// Scrolls of the page and of any element, in this frame. "scroll" doesn't
// bubble, but a capture listener on the document gets it from any element.
// It fires on every frame of a scroll, so positions are collected per
// element and sent at most every 50 ms; the last position is always sent.
var pendingScrolls = {};
var scrollFlushTimer = null;

function flushScrolls() {
    scrollFlushTimer = null;
    for (var xpath in pendingScrolls) {
        window.reportAction({type: 'scroll', xpath: xpath, top: pendingScrolls[xpath]});
    }
    pendingScrolls = {};
}

document.addEventListener('scroll', function (event) {
    var t = event.target;
    var el = t.nodeType === Node.DOCUMENT_NODE ? t.scrollingElement : t;  // the page itself scrolled
    // getXPath can't handle <html> (its parent is the document), so name it directly
    var xpath = el === el.ownerDocument.documentElement ? '/html' : getXPath(el);
    pendingScrolls[xpath] = el.scrollTop;
    if (scrollFlushTimer === null) {
        scrollFlushTimer = setTimeout(flushScrolls, 50);
    }
}, true);
