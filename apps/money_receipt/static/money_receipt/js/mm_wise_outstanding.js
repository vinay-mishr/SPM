/* Reports > Sales Reports > Mktg Manager Outstanding -- direct port of the
   VFP "MKTG MANAGER WISE PARTY WISE OUTSTANDING" OLE-Excel export block:
   EXCEL only (no VIEW/PRINT, matching the VFP form's own screenshot). */
(function () {
  "use strict";

  var root = document.querySelector("[data-mm-wise-outstanding]");
  if (!root) return;

  var mmSearch = root.querySelector("[data-mm-search]");
  var mmCode = root.querySelector("[data-mm-code]");
  var runDate = root.querySelector("[data-run-date]");
  var alertBox = root.querySelector("[data-alert]");
  var initial = JSON.parse(document.getElementById("mmo-initial-data").textContent);

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
    var params = new URLSearchParams();
    params.set("run_date", window.DateMask.toIso(runDate.value));
    params.set("scope", scope());
    if (scope() === "single") params.set("manager_code", mmCode.value);
    window.location.href = root.dataset.exportUrl + "?" + params.toString();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  runDate.value = window.DateMask.toDisplay(initial.run_date);
})();
