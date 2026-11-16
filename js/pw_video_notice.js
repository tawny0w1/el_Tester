(el, a) => {
    // REPLAY_JS["video_hover"] in pw_tester.py, RIGHT window: shows
    // (a.show true) or hides the same popup as video_notice.js (Selenium).
    // el: the right video, only used to find its page. OK hides the popup
    // for the rest of the session (sessionStorage), as in Selenium.
    let popup = document.getElementById('videoNoticePopup');
    if (!popup) {
        popup = document.createElement('div');
        popup.id = 'videoNoticePopup';
        popup.style.cssText = 'position: fixed; top: 450px; right: 250px; background: #ff6b6b; color: white; padding: 20px; border-radius: 5px; font-size: 14px; font-weight: bold; z-index: 99999; box-shadow: 0 4px 6px rgba(0,0,0,0.3); display: none; max-width: 350px;';

        const message = document.createElement('div');
        message.style.marginBottom = '15px';
        message.textContent = '⚠ Video playback is NOT synchronized. Please, test separately.';
        popup.appendChild(message);

        const button = document.createElement('button');
        button.textContent = 'OK';
        button.style.cssText = 'background: white; color: #ff6b6b; border: none; padding: 8px 16px; border-radius: 3px; font-weight: bold; cursor: pointer; font-size: 13px;';
        button.onclick = () => {
            popup.style.display = 'none';
            sessionStorage.setItem('videoNoticeDismissed', 'true');
        };
        popup.appendChild(button);
        el.ownerDocument.body.appendChild(popup);
    }
    const dismissed = sessionStorage.getItem('videoNoticeDismissed') === 'true';
    popup.style.display = a.show && !dismissed ? 'block' : 'none';
}
