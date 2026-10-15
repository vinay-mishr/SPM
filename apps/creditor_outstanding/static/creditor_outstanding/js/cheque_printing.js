/* Creditor Outstanding > Cheque Printing: show the cheque for a payment no., then print it. */
(function () {
  "use strict";

  var root = document.querySelector("[data-cp]");
  if (!root) return;

  var chq = root.querySelector("[data-chq-no]");
  var cheque = root.querySelector("[data-cheque]");
  var alertBox = root.querySelector("[data-alert]");
  var timer = null;

  function show(msg) {
    alertBox.textContent = msg || "";
    alertBox.hidden = !msg;
    clearTimeout(timer);
    if (msg) timer = setTimeout(function () { alertBox.hidden = true; }, 5000);
  }

  function dmy(iso) {
    var p = String(iso || "").split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : "";
  }

  root.querySelector("[data-show]").addEventListener("click", function () {
    var no = chq.value.trim();
    if (!no) { show("Enter the cheque no."); return; }
    fetch(root.dataset.dataUrl + "?chq_no=" + encodeURIComponent(no), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        if (!res.ok) { show(res.body.message || "Invalid Chq No."); cheque.hidden = true; return; }
        show("");
        root.querySelector("[data-payee]").textContent = res.body.payee;
        root.querySelector("[data-date]").textContent = dmy(res.body.date);
        root.querySelector("[data-amount]").textContent = res.body.amount;
        root.querySelector("[data-words]").textContent = res.body.words;
        cheque.hidden = false;
      });
  });

  root.querySelector("[data-print]").addEventListener("click", function () {
    if (cheque.hidden) { show("Show the cheque first."); return; }
    window.print();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });
})();
