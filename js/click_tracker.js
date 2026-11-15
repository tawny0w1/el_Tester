// Click, input and in-iframe scroll tracker for the LEFT window.
// Needs xpath.js before it. Writes the actions to sessionStorage;
// the Python sync loops read them and replay them on the right.
console.log("Reinjecting click interception script");

function handleClick(event) {
    var target = event.target.closest('a, button, input[type="checkbox"], input[type="radio"], .flashcard, .quiz-multiple-choice-option__input');
    if (target) {
        // Read by Python only if the target has no such element (bug report)
        window.sessionStorage.setItem('lastClickedName', getElementName(target));
        var frameXPaths = getFrameXPaths(target);
        var url = target.href || null;
        if (url && frameXPaths.length === 0) {
            event.preventDefault();
            console.log("Click intercepted (URL):", url);
            // XPath key first: Python reads it after it sees the URL key.
            // The right window opens its own link at this XPath.
            window.sessionStorage.setItem('lastClickedLinkXPath', getXPath(target));
            window.sessionStorage.setItem('lastClickedUrl', url);
        } else {
            var xpath = getXPath(target);
            console.log("Click intercepted (non-URL, xpath):", xpath);
            // Frame key first: Python reads it after it sees the element key
            window.sessionStorage.setItem('lastClickedFrameXPaths', JSON.stringify(frameXPaths));
            window.sessionStorage.setItem('lastClickedElementXPath', xpath);
        }
    }
}

document.addEventListener('click', handleClick, true);

// Typing and dropdown changes. Checkboxes and radios are synced as clicks.
function handleInput(event) {
    var t = event.target;
    if (t.type === 'checkbox' || t.type === 'radio') return;
    // One entry per field, so a quick change in another field (e.g. autofill)
    // doesn't overwrite this one before Python reads it
    var change = {frameXPaths: getFrameXPaths(t), xpath: getXPath(t), value: t.value};
    var key = JSON.stringify([change.frameXPaths, change.xpath]);  // unique per field
    var pending = JSON.parse(window.sessionStorage.getItem('pendingInputs') || '{}');
    pending[key] = change;
    window.sessionStorage.setItem('pendingInputs', JSON.stringify(pending));
}

document.addEventListener('input', handleInput, true);

// Scrolls inside iframes. Only listenInFrames adds this listener: the top
// page is synced by the synchronize_scroll poll. "scroll" doesn't bubble,
// but a capture listener on a document gets it from any element in it.
function handleScroll(event) {
    var t = event.target;
    var el = t.nodeType === Node.DOCUMENT_NODE ? t.scrollingElement : t;  // the frame's page itself scrolled
    // getXPath can't handle <html> (its parent is the document), so name it directly
    var xpath = el === el.ownerDocument.documentElement ? '/html' : getXPath(el);
    var frameXPaths = getFrameXPaths(el);
    var key = JSON.stringify([frameXPaths, xpath]);  // unique per scrolled element
    var pending = JSON.parse(window.sessionStorage.getItem('pendingScrolls') || '{}');
    pending[key] = {frameXPaths: frameXPaths, xpath: xpath, top: el.scrollTop};
    window.sessionStorage.setItem('pendingScrolls', JSON.stringify(pending));
}

// Events inside an iframe don't reach this document. Listen inside every
// same-origin iframe too, and inside the iframes in those (recursion).
// Re-checked every 500 ms because iframes appear (and get rewritten)
// after load. Re-adding the same listener is a no-op.
function listenInFrames(doc) {
    var frames = doc.querySelectorAll('iframe');
    for (var i = 0; i < frames.length; i++) {
        try {
            var inner = frames[i].contentDocument;  // null for cross-origin
            if (inner) {
                inner.addEventListener('click', handleClick, true);
                inner.addEventListener('input', handleInput, true);
                inner.addEventListener('scroll', handleScroll, true);
                listenInFrames(inner);
            }
        } catch (e) {}
    }
}

setInterval(function () { listenInFrames(document); }, 500);
