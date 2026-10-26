/* Reports > Sales Reports > Representative Wise Sale -- direct port of the
   VFP "REPRESENTATIVEWISE SALE" OLE-Excel export block: EXCEL only (no
   VIEW/PRINT, matching the VFP form's own screenshot). */
(function () {
  "use strict";

  var root = document.querySelector("[data-rep-sale-report]");
  if (!root) return;

  var repSearch = root.querySelector("[data-rep-search]");
  var repCode = root.querySelector("[data-rep-code]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var alertBox = root.querySelector("[data-alert]");
  var initial = JSON.parse(document.getElementById("rws-initial-data").textContent);

  function show(msg) {
    alertBox.textContent = msg || "";
    alertBox.hidden = !msg;
  }

  function scope() { return root.querySelector("[data-scope]:checked").value; }

  window.HelpLookup.attach(repSearch, {
    endpoint: root.dataset.repsUrl, resultsKey: "reps", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }],
    title: "Representative",
    onSelect: function (r) { repCode.value = r.code; repSearch.value = r.name; },
  });

  root.querySelectorAll("[data-scope]").forEach(function (radio) {
    radio.addEventListener("change", function () {
      var single = scope() === "single";
      repSearch.disabled = !single;
      if (!single) { repSearch.value = ""; repCode.value = ""; }
    });
  });

  root.querySelector("[data-excel]").addEventListener("click", function () {
    show("");
    if (scope() === "single" && !repCode.value) { show("Select a representative first."); return; }
    var start = window.DateMask.toIso(startDate.value);
    var end = window.DateMask.toIso(endDate.value);
    if (start > end) { show("Start Date cannot be later than End Date."); return; }
    var params = new URLSearchParams();
    params.set("start_date", start);
    params.set("end_date", end);
    params.set("scope", scope());
    if (scope() === "single") params.set("rep_code", repCode.value);
    window.location.href = root.dataset.exportUrl + "?" + params.toString();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  startDate.value = window.DateMask.toDisplay(initial.start_date);
  endDate.value = window.DateMask.toDisplay(initial.end_date);
})();
