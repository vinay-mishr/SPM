/* Reports > Sales Reports > State Wise Outstanding -- direct port of the
   VFP "STATEWISE PARTY WISE OUTSTANDING" OLE-Excel export block: EXCEL
   only (no VIEW/PRINT, matching the VFP form's own screenshot). */
(function () {
  "use strict";

  var root = document.querySelector("[data-state-wise-outstanding]");
  if (!root) return;

  var division = root.querySelector("[data-division]");
  var stateSearch = root.querySelector("[data-state-search]");
  var stateCode = root.querySelector("[data-state-code]");
  var runDate = root.querySelector("[data-run-date]");
  var alertBox = root.querySelector("[data-alert]");
  var initial = JSON.parse(document.getElementById("swo-initial-data").textContent);

  function show(msg) {
    alertBox.textContent = msg || "";
    alertBox.hidden = !msg;
  }

  function scope() { return root.querySelector("[data-scope]:checked").value; }

  window.HelpLookup.attach(stateSearch, {
    endpoint: root.dataset.statesUrl, resultsKey: "states", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }],
    title: "State",
    onSelect: function (s) { stateCode.value = s.code; stateSearch.value = s.name; },
  });

  root.querySelectorAll("[data-scope]").forEach(function (radio) {
    radio.addEventListener("change", function () {
      var single = scope() === "single";
      stateSearch.disabled = !single;
      if (!single) { stateSearch.value = ""; stateCode.value = ""; }
    });
  });

  root.querySelector("[data-excel]").addEventListener("click", function () {
    show("");
    if (scope() === "single" && !stateCode.value) { show("Select a state first."); return; }
    var params = new URLSearchParams();
    params.set("division", division.value.trim() || "A");
    params.set("run_date", window.DateMask.toIso(runDate.value));
    params.set("scope", scope());
    if (scope() === "single") params.set("state_code", stateCode.value);
    window.location.href = root.dataset.exportUrl + "?" + params.toString();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  division.value = initial.division;
  runDate.value = window.DateMask.toDisplay(initial.run_date);
})();
