/* Shared British date format (dd/mm/yyyy) helpers + input auto-mask.
   Backend DateFields already accept "%d/%m/%Y", so this is display-only. */
(function () {
  "use strict";

  function toDisplay(iso) {
    if (!iso) return "";
    var p = String(iso).split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : iso;
  }

  function toIso(dmy) {
    var p = String(dmy || "").split("/");
    return p.length === 3 ? p[2] + "-" + p[1] + "-" + p[0] : dmy;
  }

  function mask(input) {
    input.addEventListener("input", function () {
      var digits = input.value.replace(/\D/g, "").slice(0, 8);
      var out = digits.slice(0, 2);
      if (digits.length > 2) out += "/" + digits.slice(2, 4);
      if (digits.length > 4) out += "/" + digits.slice(4, 8);
      input.value = out;
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-date-mask]").forEach(mask);
  });

  window.DateMask = { toDisplay: toDisplay, toIso: toIso, attach: mask };
})();
