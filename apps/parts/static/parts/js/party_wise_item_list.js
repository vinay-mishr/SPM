/* Reports > Sales Reports > Party Wise Item List -- direct port of the VFP
   "PARTY WISE ITEM LIST" OLE-Excel export block: EXCEL only (no
   VIEW/PRINT, matching the VFP form's own screenshot). */
(function () {
  "use strict";

  var root = document.querySelector("[data-party-wise-item-list]");
  if (!root) return;

  var partySearch = root.querySelector("[data-party-search]");
  var partyCode = root.querySelector("[data-party-code]");
  var alertBox = root.querySelector("[data-alert]");

  function show(msg) {
    alertBox.textContent = msg || "";
    alertBox.hidden = !msg;
  }

  window.HelpLookup.attach(partySearch, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }],
    title: "Party",
    onSelect: function (p) { partyCode.value = p.code; partySearch.value = p.name; },
  });

  root.querySelector("[data-excel]").addEventListener("click", function () {
    show("");
    if (!partyCode.value) { show("Select a party first."); return; }
    var params = new URLSearchParams();
    params.set("party_code", partyCode.value);
    window.location.href = root.dataset.exportUrl + "?" + params.toString();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });
})();
