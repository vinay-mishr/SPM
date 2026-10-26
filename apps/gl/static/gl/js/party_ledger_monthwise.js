/* Accounts > Ledger Printing > Party Ledger Monthwise -- direct port of the
   VFP "PARTY LEDGER MONTHWISE" OLE-Excel export block: EXCEL only (no VIEW/
   PRINT, matching the VFP form's own screenshot), RUN DATE must fall within
   its own financial year. */
(function () {
  "use strict";

  var root = document.querySelector("[data-party-ledger-monthwise]");
  if (!root) return;

  var partyName = root.querySelector("[data-party-name]");
  var ccode = root.querySelector("[data-ccode]");
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

  window.HelpLookup.attach(partyName, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Party",
    onSelect: function (p) { ccode.value = p.code; },
  });
  partyName.addEventListener("input", function () {
    if (!partyName.value) ccode.value = "";
  });

  var initial = JSON.parse(document.getElementById("plmw-initial-data").textContent);

  root.querySelector("[data-excel]").addEventListener("click", function () {
    show("");
    if (!ccode.value) { show("Select a party."); return; }
    var iso = dmyToIso(runDate.value);
    if (iso < initial.fy_start || iso > initial.fy_end) {
      show("Run Date must fall within the financial year (" + dmy(initial.fy_start) + " to " + dmy(initial.fy_end) + ").");
      return;
    }
    var params = new URLSearchParams();
    params.set("ccode", ccode.value);
    params.set("run_date", iso);
    window.location.href = root.dataset.exportUrl + "?" + params.toString();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  runDate.value = dmy(initial.run_date);
})();
