(el, a) => {
    // REPLAY_JS["drag"] in pw_tester.py, RIGHT window: the same drag as
    // drag_replay.js (Selenium), as a function for Playwright's evaluate.
    // el: the right piece; a.dx, a.dy: how far the left piece was moved.
    const rect = el.getBoundingClientRect();
    const startX = rect.left + rect.width / 2;
    const startY = rect.top + rect.height / 2;

    // Rise may listen on the piece or on what's under the pointer, so both get each event
    function send(type, x, y) {
        const event = new PointerEvent(type, {bubbles: true, cancelable: true, clientX: x, clientY: y, pointerType: 'mouse'});
        const under = document.elementFromPoint(x, y);
        if (under) under.dispatchEvent(event);
        el.dispatchEvent(event);
    }

    send('pointerdown', startX, startY);
    send('pointermove', startX + a.dx / 2, startY + a.dy / 2);
    send('pointermove', startX + a.dx, startY + a.dy);
    send('pointerup', startX + a.dx, startY + a.dy);
}
