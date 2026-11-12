// Drag tracker for the LEFT window: pointer events on a Rise matching
// piece go to sessionStorage.lastDrag. Needs xpath.js before it.
(function(){
  if (window.__dragTracker) return;
  window.__dragTracker = true;

  var current = null;
  document.addEventListener('pointerdown', function(e){
    try{
      var el = e.target.closest('.matching-interaction-piece');
      if(!el) return;
      current = {
        id: Date.now(),
        xpath: getXPath(el),
        startX: e.clientX,
        startY: e.clientY,
        lastX: e.clientX,
        lastY: e.clientY,
        active: true
      };
      window.sessionStorage.setItem('lastDrag', JSON.stringify(current));
    }catch(err){ console.error('drag down', err); }
  }, true);

  document.addEventListener('pointermove', function(e){
    try{
      if(!current || !current.active) return;
      current.lastX = e.clientX;
      current.lastY = e.clientY;
      window.sessionStorage.setItem('lastDrag', JSON.stringify(current));
    }catch(err){ console.error('drag move', err); }
  }, true);

  document.addEventListener('pointerup', function(e){
    try{
      if(!current) return;
      current.lastX = e.clientX;
      current.lastY = e.clientY;
      current.active = false;
      current.ended = true;
      window.sessionStorage.setItem('lastDrag', JSON.stringify(current));
      setTimeout(function(){ try{ window.sessionStorage.removeItem('lastDrag'); }catch(e){} }, 1000);
      current = null;
    }catch(err){ console.error('drag up', err); }
  }, true);
})();
