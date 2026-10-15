(function () {
  "use strict";

  function askConfirm(message, onYes) {
    var host = document.querySelector("dialog[open]") || document.body;
    var overlay = document.createElement("div");
    overlay.className = "modal-discard";
    if (host === document.body) overlay.style.position = "fixed";
    overlay.innerHTML =
      '<div class="modal-discard__box" role="alertdialog">' +
      '<p class="modal-discard__title"></p>' +
      '<div class="modal-discard__actions">' +
      '<button class="btn btn--primary" type="button" data-yes>Yes</button>' +
      '<button class="btn btn--secondary" type="button" data-no>No</button>' +
      "</div></div>";
    overlay.querySelector(".modal-discard__title").textContent = message;
    function close() { overlay.remove(); }
    overlay.querySelector("[data-yes]").addEventListener("click", function () { close(); onYes(); });
    overlay.querySelector("[data-no]").addEventListener("click", close);
    host.appendChild(overlay);
    overlay.querySelector("[data-yes]").focus();
  }

  window.askConfirm = askConfirm;
})();
