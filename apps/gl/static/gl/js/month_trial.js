/* Accounts > Trial Balance > Month Trial -- direct port of the VFP "MONTH
   TRIAL" OLE-Excel export block: EXCEL only (no VIEW/PRINT, matching the
   VFP form's own screenshot). */
(function () {
  "use strict";

  var root = document.querySelector("[data-month-trial]");
  if (!root) return;

  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
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

  root.querySelector("[data-excel]").addEventListener("click", function () {
    show("");
    var start = dmyToIso(startDate.value);
    var end = dmyToIso(endDate.value);
    if (start > end) { show("Start Date cannot be later than End Date."); return; }
    var params = new URLSearchParams();
    params.set("start_date", start);
    params.set("end_date", end);
    window.location.href = root.dataset.exportUrl + "?" + params.toString();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  var initial = JSON.parse(document.getElementById("mnt-initial-data").textContent);
  startDate.value = dmy(initial.start_date);
  endDate.value = dmy(initial.end_date);
})();
