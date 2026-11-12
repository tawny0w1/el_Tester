// Replays a drag on the RIGHT window as synthetic pointer events.
// arguments: xpath, startX, startY, lastX, lastY (from lastDrag).
try{
  function byXPath(x){ return document.evaluate(x, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; }
  var xpath = arguments[0], sx = arguments[1], sy = arguments[2], lx = arguments[3], ly = arguments[4];
  var el = byXPath(xpath);
  if(!el) return {ok:false,msg:'element not found'};
  var rect = el.getBoundingClientRect();
  var cx = rect.left + rect.width/2, cy = rect.top + rect.height/2;
  var dx = lx - sx, dy = ly - sy;
  var ex = cx + dx, ey = cy + dy;

  function send(type,x,y){
    var ev = new PointerEvent(type, {bubbles:true, cancelable:true, clientX:x, clientY:y, pointerType:'mouse'});
    var under = document.elementFromPoint(x,y); if(under) try{ under.dispatchEvent(ev); }catch(e){}
    try{ el.dispatchEvent(ev); }catch(e){}
  }

  send('pointerdown', cx, cy);
  // single midpoint move instead of two
  send('pointermove', cx + dx*0.5, cy + dy*0.5);
  // final move with exact coordinates
  send('pointermove', ex, ey);
  send('pointerup', ex, ey);
  return {ok:true};
}catch(e){ return {ok:false,msg: e.toString()}; }
