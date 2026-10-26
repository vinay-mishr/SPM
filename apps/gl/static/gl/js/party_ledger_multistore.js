/* Accounts > Ledger Printing > Party Ledger Multistore -- direct port of the
   VFP "PARTY LEDGER" bill-wise report (pled.PRN): one row per sales bill for
   the selected party, with amount received/receipt date/balance/delay days
   pulled from the collection table. VIEW loads it, EXCEL downloads the same
   data as a workbook; no PRINT (matching the VFP form's own screenshot). */
(function () {
  "use strict";

  var root = document.querySelector("[data-party-ledger-multistore]");
  if (!root) return;

  var partyName = root.querySelector("[data-party-name]");
  var ccode = root.querySelector("[data-ccode]");
  var city = root.querySelector("[data-city]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var alertBox = root.querySelector("[data-alert]");
  var result = root.querySelector("[data-result]");
  var rows = root.querySelector("[data-r-rows]");

  function show(msg) {
    alertBox.textContent = msg || "";
    alertBox.hidden = !msg;
  }
  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (cls) td.className = cls;
    return td;
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

  window.HelpLookup.attach(partyName, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Party",
    onSelect: function (p) { ccode.value = p.code; city.value = p.city; },
  });
  partyName.addEventListener("input", function () {
    if (!partyName.value) { ccode.value = ""; city.value = ""; }
  });

  function query() {
    var params = new URLSearchParams();
    params.set("ccode", ccode.value);
    params.set("start_date", dmyToIso(startDate.value));
    params.set("end_date", dmyToIso(endDate.value));
    return params.toString();
  }

  function view() {
    show("");
    if (!ccode.value) { show("Select a party."); return; }
    fetch(root.dataset.dataUrl + "?" + query(), { credentials: "same-origin" })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        if (!res.ok) { show(res.body.message || "Could not load the Party Ledger."); result.hidden = true; return; }
        var d = res.body;
        root.querySelector("[data-r-start]").textContent = dmy(d.start_date);
        root.querySelector("[data-r-end]").textContent = dmy(d.end_date);
        root.querySelector("[data-r-party-line]").textContent = "PARTY NAME : " + partyName.value;
        root.querySelector("[data-r-city-line]").textContent = "PARTY CITY : " + city.value;
        root.querySelector("[data-r-total-bill]").textContent = d.total_bill;
        root.querySelector("[data-r-total-received]").textContent = d.total_received;
        root.querySelector("[data-r-total-balance]").textContent = d.total_balance;
        rows.textContent = "";
        if (!d.rows.length) {
          var tr = document.createElement("tr");
          tr.className = "cb-empty";
          var td = document.createElement("td");
          td.colSpan = 7;
          td.textContent = "No bills for this party in this date range.";
          tr.appendChild(td);
          rows.appendChild(tr);
        }
        d.rows.forEach(function (r) {
          var tr = document.createElement("tr");
          tr.append(
            cell(r.div + "-" + r.bill_no), cell(dmy(r.bill_date)), cell(r.bill_amount, "num"),
            cell(r.amount_received, "num"), cell(dmy(r.receipt_date)), cell(r.balance, "num"),
            cell(r.delay_days, "num"),
          );
          rows.appendChild(tr);
        });
        result.hidden = false;
      });
  }

  root.querySelector("[data-view]").addEventListener("click", view);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    if (!ccode.value) { show("Select a party."); return; }
    window.location.href = root.dataset.exportUrl + "?" + query();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  var initial = JSON.parse(document.getElementById("plm-initial-data").textContent);
  startDate.value = dmy(initial.start_date);
  endDate.value = dmy(initial.end_date);
})();
