// Every <button class="count"> shows how often it was clicked, so the two
// windows can be compared at a glance. Also fills .box elements with lines
// so they can scroll.
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('button.count').forEach(function (b) {
    var label = b.textContent;
    b.dataset.count = '0';
    b.addEventListener('click', function () {
      b.dataset.count = String(Number(b.dataset.count) + 1);
      b.textContent = label + ' (' + b.dataset.count + ')';
    });
  });
  document.querySelectorAll('.box').forEach(function (box) {
    for (var i = 1; i <= 30; i++) {
      var p = document.createElement('p');
      p.textContent = box.id + ' line ' + i;
      box.appendChild(p);
    }
  });
});
