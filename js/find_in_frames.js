// Start of every right-window action (run_on_right in el_tester.py).
// arguments[0]: iframe XPaths, outer to inner; arguments[1]: element XPath.
// Defines `el`; the action JS and 'return true;' are appended after it.
function byXPath(doc, x) { return doc.evaluate(x, doc, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; }
var doc = document;
for (var i = 0; i < arguments[0].length; i++) {  // walk the iframes, outer to inner
    var frame = byXPath(doc, arguments[0][i]);
    doc = frame && frame.contentDocument;
    if (!doc) return false;
}
var el = byXPath(doc, arguments[1]);
if (!el) return false;
