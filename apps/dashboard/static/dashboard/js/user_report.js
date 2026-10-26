/* Reports > Sales Reports > User Wise Report -- direct port of the VFP
   "USER WISE REPORT" OLE-Excel export block: EXCEL only (no VIEW/PRINT,
   matching the VFP form's own screenshot). A user is always required --
   see apps.dashboard.user_report's own docstring on why "ALL" is not a
   real option in the VFP source. */
(function () {
  "use strict";

  var root = document.querySelector("[data-user-report]");
  if (!root) return;

  var user = root.querySelector("[data-user]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var alertBox = root.querySelector("[data-alert]");
  var initial = JSON.parse(document.getElementById("ur-initial-data").textContent);

  function show(msg) {
    alertBox.textContent = msg || "";
    alertBox.hidden = !msg;
  }

  root.querySelector("[data-excel]").addEventListener("click", function () {
    show("");
    if (!user.value.trim()) { show("Enter a user."); return; }
    var start = window.DateMask.toIso(startDate.value);
    var end = window.DateMask.toIso(endDate.value);
    if (start > end) { show("Start Date cannot be later than End Date."); return; }
    var params = new URLSearchParams();
    params.set("user", user.value.trim());
    params.set("start_date", start);
    params.set("end_date", end);
    window.location.href = root.dataset.exportUrl + "?" + params.toString();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  startDate.value = window.DateMask.toDisplay(initial.start_date);
  endDate.value = window.DateMask.toDisplay(initial.end_date);
})();
