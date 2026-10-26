/* Reports > Sales Reports > Mktg Managerwise Sale -- direct port of the VFP
   "MKTG MANAGERWISE SALE" OLE-Excel export block: EXCEL only (no
   VIEW/PRINT, matching the VFP form's own screenshot). */
(function () {
  "use strict";

  var root = document.querySelector("[data-mm-sale-report]");
  if (!root) return;

  var mmSearch = root.querySelector("[data-mm-search]");
  var mmCode = root.querySelector("[data-mm-code]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var alertBox = root.querySelector("[data-alert]");
  var initial = JSON.parse(document.getElementById("mms-initial-data").textContent);

  function show(msg) {
    alertBox.textContent = msg || "";
    alertBox.hidden = !msg;
  }

  function scope() { return root.querySelector("[data-scope]:checked").value; }

  window.HelpLookup.attach(mmSearch, {
    endpoint: root.dataset.managersUrl, resultsKey: "managers", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }],
    title: "Marketing Manager",
    onSelect: function (m) { mmCode.value = m.code; mmSearch.value = m.name; },
  });

  root.querySelectorAll("[data-scope]").forEach(function (radio) {
    radio.addEventListener("change", function () {
      var single = scope() === "single";
      mmSearch.disabled = !single;
      if (!single) { mmSearch.value = ""; mmCode.value = ""; }
    });
  });

  root.querySelector("[data-excel]").addEventListener("click", function () {
    show("");
    if (scope() === "single" && !mmCode.value) { show("Select a marketing manager first."); return; }
    var start = window.DateMask.toIso(startDate.value);
    var end = window.DateMask.toIso(endDate.value);
    if (start > end) { show("Start Date cannot be later than End Date."); return; }
    var params = new URLSearchParams();
    params.set("start_date", start);
    params.set("end_date", end);
    params.set("scope", scope());
    if (scope() === "single") params.set("mm_code", mmCode.value);
    window.location.href = root.dataset.exportUrl + "?" + params.toString();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  startDate.value = window.DateMask.toDisplay(initial.start_date);
  endDate.value = window.DateMask.toDisplay(initial.end_date);
})();
