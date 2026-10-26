/* Reports > Sales Reports > Party Outstanding Letter 2 -- direct port of
   the VFP "PARTY OUTSTANDING LETTER" (second variant) OLE-Excel export
   block: EXCEL only (no VIEW/PRINT/A4, matching the data this port has). */
(function () {
  "use strict";

  var root = document.querySelector("[data-party-outstanding-letter2]");
  if (!root) return;

  var partySearch = root.querySelector("[data-party-search]");
  var partyCode = root.querySelector("[data-party-code]");
  var runDate = root.querySelector("[data-run-date]");
  var alertBox = root.querySelector("[data-alert]");
  var initial = JSON.parse(document.getElementById("pol2-initial-data").textContent);

  function show(msg) {
    alertBox.textContent = msg || "";
    alertBox.hidden = !msg;
  }

  window.HelpLookup.attach(partySearch, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Party",
    onSelect: function (p) { partyCode.value = p.code; partySearch.value = p.name; },
  });

  root.querySelector("[data-excel]").addEventListener("click", function () {
    show("");
    if (!partyCode.value) { show("Select a party first."); return; }
    var params = new URLSearchParams();
    params.set("party_code", partyCode.value);
    params.set("run_date", window.DateMask.toIso(runDate.value));
    window.location.href = root.dataset.exportUrl + "?" + params.toString();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  runDate.value = window.DateMask.toDisplay(initial.run_date);
})();
