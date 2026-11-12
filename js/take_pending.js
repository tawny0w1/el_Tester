// Reads and removes a sessionStorage key in one script, so page JS can't
// write to it in between and lose a change. arguments[0]: the key.
var value = window.sessionStorage.getItem(arguments[0]);
window.sessionStorage.removeItem(arguments[0]);
return value;
