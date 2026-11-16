// Playwright tracker for drag and drop and video hover, LEFT window.
// Loaded after xpath.js and pw_tracker.js in the same init script, so it
// runs in every page and frame, like pw_tracker.js.
// The Selenium versions (drag_tracker.js, video_hover.js) write to
// sessionStorage for Python to poll; here each action is pushed at once.

// Drag: one action on release, with how far the piece was moved.
// Only Rise's matching exercise pieces are tracked, as in Selenium.
var dragStart = null;  // {xpath, x, y} between pointerdown and pointerup

document.addEventListener('pointerdown', function (event) {
    var piece = event.target.closest('.matching-interaction-piece');
    if (piece) {
        dragStart = {xpath: getXPath(piece), x: event.clientX, y: event.clientY};
    }
}, true);

document.addEventListener('pointerup', function (event) {
    if (dragStart === null) return;
    var dx = event.clientX - dragStart.x, dy = event.clientY - dragStart.y;
    // Barely moved: a click (Rise selects the piece), sent by pw_tracker.js as a click
    if (Math.abs(dx) + Math.abs(dy) > 5) {
        window.reportAction({type: 'drag', xpath: dragStart.xpath, dx: dx, dy: dy});
    }
    dragStart = null;
}, true);

// Video hover: show the "not synced" popup on the right while the mouse is
// over a <video>. elementsFromPoint also finds a video under player controls
// that cover it (Rise), where a plain mouseover would hit the controls.
var hoveredVideo = null;

function videoAt(x, y) {
    var under = document.elementsFromPoint(x, y);
    for (var i = 0; i < under.length; i++) {
        if (under[i].tagName === 'VIDEO') return under[i];
    }
    return null;
}

document.addEventListener('mousemove', function (event) {
    var video = videoAt(event.clientX, event.clientY);
    if (video && video !== hoveredVideo) {
        hoveredVideo = video;
        window.reportAction({type: 'video_hover', xpath: getXPath(video), show: true});
    } else if (!video && hoveredVideo) {
        window.reportAction({type: 'video_hover', xpath: getXPath(hoveredVideo), show: false});
        hoveredVideo = null;
    }
}, true);
