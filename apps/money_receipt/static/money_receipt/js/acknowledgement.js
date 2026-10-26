/* Money Receipt > Payment Acknowledgement: pick a party, pick a receipt, EXCEL downloads the letter. */
(function () {
  "use strict";

  var root = document.querySelector("[data-ack]");
  if (!root) return;

  var partySearch = root.querySelector("[data-party-search]");
  var partyCode = root.querySelector("[data-party-code]");
  var runDate = root.querySelector("[data-run-date]");
  var rows = root.querySelector("[data-rows]");
  var alertBox = root.querySelector("[data-alert]");
  var excelBtn = root.querySelector("[data-excel]");
  var selected = null;
  var alertTimer = null;

  function show(msg) {
    alertBox.textContent = msg || "";
    alertBox.hidden = !msg;
    clearTimeout(alertTimer);
    if (msg) alertTimer = setTimeout(function () { alertBox.hidden = true; }, 5000);
  }

  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (cls) td.className = cls;
    return td;
  }

  function dmy(iso) {
    var p = String(iso || "").split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : "";
  }

  function render(receipts) {
    rows.textContent = "";
    selected = null;
    excelBtn.disabled = true;
    if (!receipts.length) {
      var tr = document.createElement("tr");
      tr.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 3;
      td.textContent = "No receipt for this party.";
      tr.appendChild(td);
      rows.appendChild(tr);
      return;
    }
    receipts.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.append(cell(r.chq_no || "CASH"), cell(dmy(r.chq_dt || r.slip_dt)), cell(r.amount, "num"));
      tr.addEventListener("click", function () {
        rows.querySelectorAll("tr").forEach(function (t) { t.classList.remove("is-sel"); });
        tr.classList.add("is-sel");
        selected = r;
        excelBtn.disabled = false;
      });
      rows.appendChild(tr);
    });
  }

  window.HelpLookup.attach(partySearch, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Party",
    onSelect: function (p) {
      partyCode.value = p.code;
      partySearch.value = p.name;
      show("");
      fetch(root.dataset.receiptsUrl + "?party_code=" + encodeURIComponent(p.code), { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          render(d.receipts || []);
          if (!d.receipts || !d.receipts.length) show("No receipt for this party.");
        });
    },
  });

  excelBtn.addEventListener("click", function () {
    if (!selected || !partyCode.value) { show("Select a receipt first."); return; }
    var params = new URLSearchParams();
    params.set("party_code", partyCode.value);
    params.set("chq_no", selected.chq_no);
    params.set("slip_dt", selected.slip_dt);
    params.set("run_date", window.DateMask.toIso(runDate.value));
    window.location.href = root.dataset.exportUrl + "?" + params.toString();
  });

  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  runDate.value = window.DateMask.toDisplay(new Date().toISOString().slice(0, 10));
})();
