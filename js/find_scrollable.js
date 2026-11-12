// Returns the element whose scrollTop the top-page scroll sync copies.
// Runs through execute_script, so the top-level return is allowed.
// Look for elements with scrollable overflow
var elements = document.querySelectorAll('#page-wrap, .page__content, .cover');  // Add all possible selectors here
for (var i = 0; i < elements.length; i++) {
    var element = elements[i];
    if (element.scrollHeight > element.clientHeight) {
        return element;
    }
}
// Not a Rise page (or nothing scrollable inside it): sync the page scroll
return document.scrollingElement || document.documentElement;
