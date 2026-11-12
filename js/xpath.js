// Shared helpers for every tracker script. load_js() puts this file first,
// so the trackers after it can call getXPath and getFrameXPaths.

// XPath of an element: id("...") when it has an id, otherwise a path of
// tag[index] steps from the nearest ancestor with an id (or from /html/body).
// Both course versions have the same DOM, so the same XPath finds the
// matching element in the right window.
function getXPath(element) {
    if (!element) return '';
    if (element.id) {
        return 'id("' + element.id + '")';
    }
    // ownerDocument, not document: the element may be inside an iframe
    if (element === element.ownerDocument.body) {
        return '/html/body';
    }
    var ix = 0;
    var siblings = element.parentNode ? element.parentNode.childNodes : [];
    for (var i = 0; i < siblings.length; i++) {
        var sibling = siblings[i];
        if (sibling === element) {
            var tagName = element.tagName.toLowerCase();
            return getXPath(element.parentNode) + '/' + tagName + '[' + (ix + 1) + ']';
        }
        if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
            ix++;
        }
    }
    return '';
}

// XPaths of the iframes around el, outer to inner. [] on the top page.
// Example: a button in frame2 inside frame1 -> ['id("frame1")', 'id("frame2")']
function getFrameXPaths(el) {
    var path = [];
    var frame = el.ownerDocument.defaultView.frameElement;
    while (frame) {
        path.unshift(getXPath(frame));
        frame = frame.ownerDocument.defaultView.frameElement;
    }
    return path;
}
