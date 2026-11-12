// Video hover tracker for the LEFT window: entering and leaving a <video>
// goes to sessionStorage (videoHoverEnter/Leave). Needs xpath.js before it.
(function(){
  if (window.__videoHoverTracker) return;
  window.__videoHoverTracker = true;

  function findVideoFromPoint(x,y){
    if (document.elementsFromPoint) {
      var els = document.elementsFromPoint(x,y);
      for (var i=0;i<els.length;i++){
        var v = els[i].closest ? els[i].closest('video') : null;
        if (v) return v;
      }
    }
    var vids = document.querySelectorAll('video');
    for (var j=0;j<vids.length;j++){
      try {
        var r = vids[j].getBoundingClientRect();
        if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return vids[j];
      } catch(e){}
    }
    return null;
  }

  var lastVideo = null;
  document.addEventListener('mousemove', function(e){
    try{
      var v = findVideoFromPoint(e.clientX, e.clientY);
      if (v && lastVideo !== v) {
        lastVideo = v;
        window.sessionStorage.setItem('videoHoverEnter', JSON.stringify({xpath: getXPath(v), timestamp: Date.now()}));
      } else if (!v && lastVideo) {
        window.sessionStorage.setItem('videoHoverLeave', JSON.stringify({timestamp: Date.now()}));
        lastVideo = null;
      }
    }catch(e){ console.error('video hover track', e); }
  }, true);
})();
