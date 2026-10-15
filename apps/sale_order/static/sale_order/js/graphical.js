/* Sale Order > Graphical Printing: look up an order, preview it and print it. */
(function () {
  "use strict";

  var root = document.querySelector("[data-graphical]");
  if (!root) return;

  var ordNo = root.querySelector("[data-ord-no]");
  var ordDate = root.querySelector("[data-ord-date]");
  var partyCode = root.querySelector("[data-party-code]");
  var partyName = root.querySelector("[data-party-name]");
  var partyCity = root.querySelector("[data-party-city]");
  var errorBox = root.querySelector("[data-error]");
  var preview = root.querySelector("[data-preview]");
  var current = null;

  function dmy(iso) {
    if (!iso) return "";
    var p = String(iso).split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : iso;
  }

  function showError(msg) {
    errorBox.textContent = msg || "";
    errorBox.hidden = !msg;
  }

  function printUrl(no) {
    return root.dataset.printUrlTemplate.replace("__NO__", encodeURIComponent(no));
  }

  function load() {
    var no = ordNo.value.trim();
    showError("");
    preview.hidden = true;
    current = null;
    ordDate.value = "";
    partyCode.value = "";
    partyName.value = "";
    partyCity.value = "";
    if (!no) { showError("Enter the order no."); return Promise.resolve(null); }
    return fetch(root.dataset.detailUrlTemplate.replace("__NO__", encodeURIComponent(no)), {
      credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" },
    }).then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        if (!res.ok) { showError(res.body.message || "Order not found."); return null; }
        current = res.body;
        ordDate.value = dmy(res.body.order_date);
        partyCode.value = res.body.party_code;
        partyName.value = res.body.party_name;
        partyCity.value = res.body.city;
        return res.body;
      });
  }

  root.querySelector("[data-view]").addEventListener("click", function () {
    load().then(function (order) {
      if (!order) return;
      preview.src = printUrl(order.order_no);
      preview.hidden = false;
    });
  });

  root.querySelector("[data-print]").addEventListener("click", function () {
    if (current) { window.open(printUrl(current.order_no), "_blank"); return; }
    load().then(function (order) {
      if (order) window.open(printUrl(order.order_no), "_blank");
    });
  });

  ordNo.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); load(); }
  });
  root.querySelector("[data-exit]").addEventListener("click", function () {
    window.location.href = root.dataset.exitUrl;
  });
})();
