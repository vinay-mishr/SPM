/* Accounts > Final Accounts > P & L (Cl Stock) -- G.P.%/CLOSING STOCK/RUN
   DATE + VIEW/EXIT, matching the VFP form's own screenshot. VIEW posts to a
   real endpoint; see apps.gl.pl_statement's own module docstring for why it
   currently explains rather than computes a P&L figure (the VFP "trade1"
   procedure's own source was never provided). */
(function () {
  "use strict";

  var root = document.querySelector("[data-pl-statement]");
  if (!root) return;

  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var gpPercent = root.querySelector("[data-gp-percent]");
  var closingStock = root.querySelector("[data-closing-stock]");
  var runDate = root.querySelector("[data-run-date]");
  var alertBox = root.querySelector("[data-alert]");

  function show(msg) {
    alertBox.textContent = msg || "";
    alertBox.hidden = !msg;
  }
  function dmyToIso(d) {
    var p = String(d || "").split(/[-/]/);
    return p.length === 3 ? p[2] + "-" + p[1] + "-" + p[0] : d;
  }
  function dmy(iso) {
    var p = String(iso || "").split("-");
    return p.length === 3 ? p[2] + "-" + p[1] + "-" + p[0] : "";
  }
  root.querySelectorAll("[data-date-mask]").forEach(function (input) {
    input.addEventListener("input", function () {
      var digits = input.value.replace(/\D/g, "").slice(0, 8);
      var out = digits.slice(0, 2);
      if (digits.length > 2) out += "-" + digits.slice(2, 4);
      if (digits.length > 4) out += "-" + digits.slice(4, 8);
      input.value = out;
    });
  });

  root.querySelector("[data-view]").addEventListener("click", function () {
    show("");
    fetch(root.dataset.viewUrl, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrf, "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify({
        run_date: dmyToIso(runDate.value), gp_percent: gpPercent.value, closing_stock: closingStock.value,
      }),
    })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) { show(res.body.message || "Could not load."); });
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  var initial = JSON.parse(document.getElementById("pls-initial-data").textContent);
  runDate.value = dmy(initial.run_date);
})();
