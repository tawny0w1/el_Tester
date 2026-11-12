// Shows (arguments[0] true) or hides the 'video is not synced' popup
// on the RIGHT window. Creates the popup the first time.
try {
    if (!document.getElementById('videoNoticePopup')) {
        var popup = document.createElement('div');
        popup.id = 'videoNoticePopup';
        popup.style.cssText = 'position: fixed; top: 450px; right: 250px; background: #ff6b6b; color: white; padding: 20px; border-radius: 5px; font-size: 14px; font-weight: bold; z-index: 99999; box-shadow: 0 4px 6px rgba(0,0,0,0.3); display: none; max-width: 350px;';

        var messageDiv = document.createElement('div');
        messageDiv.style.marginBottom = '15px';
        messageDiv.textContent = '⚠ Video playback is NOT synchronized. Please, test separately.';
        popup.appendChild(messageDiv);

        var button = document.createElement('button');
        button.textContent = 'OK';
        button.style.cssText = 'background: white; color: #ff6b6b; border: none; padding: 8px 16px; border-radius: 3px; font-weight: bold; cursor: pointer; font-size: 13px;';
        button.onclick = function(){
            popup.style.display = 'none';
            window.sessionStorage.setItem('videoNoticeDismissed', 'true');
        };
        popup.appendChild(button);

        document.body.appendChild(popup);
    }
    var popup = document.getElementById('videoNoticePopup');
    // only show if not dismissed
    var dismissed = window.sessionStorage.getItem('videoNoticeDismissed') === 'true';
    popup.style.display = (arguments[0] && !dismissed) ? 'block' : 'none';
    return {ok: true};
} catch(e) { return {ok:false, msg: e.toString()}; }
