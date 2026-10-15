/* Spare Sale Order > Printing: open the printable order for the order number entered. */
(function () {
  "use strict";

  var root = document.querySelector("[data-spare-printing]");
  if (!root) return;

  var input = root.querySelector("[data-order-no]");
  var err = root.querySelector("[data-error]");

  function go() {
    var no = input.value.trim();
    if (!no) { err.textContent = "Enter the order no."; err.hidden = false; return; }
    err.hidden = true;
    window.open(root.dataset.printUrlTemplate.replace("__NO__", encodeURIComponent(no)), "_blank");
  }

  root.querySelector("[data-print]").addEventListener("click", go);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); go(); }
  });
  root.querySelector("[data-exit]").addEventListener("click", function () {
    window.location.href = root.dataset.exitUrl;
  });
})();
