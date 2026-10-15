/* Stock > Production Schedule (New) > Based upon Inventory (VFP production schedule). */
(function () {
  "use strict";

  var root = document.querySelector("[data-production-schedule]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var totalHrs = root.querySelector("[data-total-hrs]");
  var pending = root.dataset.mode === "pending";
  var daysInput = root.querySelector("[data-days]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var dateError = root.querySelector("[data-date-error]");
  var toast = document.querySelector("[data-toast]");
  var initial = JSON.parse(document.getElementById("ps-initial-data").textContent);

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function cell(text, className) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (className) td.className = className;
    return td;
  }

  function validRange() {
    var s = window.DateMask.toIso(startDate.value);
    var e = window.DateMask.toIso(endDate.value);
    if (s && e && s > e) {
      dateError.textContent = "Start Date cannot be later than End Date.";
      dateError.hidden = false;
      return false;
    }
    dateError.hidden = true;
    return true;
  }

  function query() {
    var params = new URLSearchParams();
    params.set("start_date", window.DateMask.toIso(startDate.value));
    params.set("end_date", window.DateMask.toIso(endDate.value));
    if (!pending) params.set("days", daysInput.value || "30");
    return params.toString();
  }

  function setDayHeaders() {
    if (pending) return;
    var d = daysInput.value || "30";
    root.querySelector("[data-h-cur]").textContent = "Avg Curr. Sale For " + d + " Days";
    root.querySelector("[data-h-last]").textContent = "Avg Last Year Sale For " + d + " Days";
  }

  function view() {
    if (!validRange()) return;
    setDayHeaders();
    fetch(root.dataset.dataUrl + "?" + query(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        tbody.textContent = "";
        if (!res.ok) { showToast(res.body.message || "Could not load the schedule.", "error"); return; }
        res.body.rows.forEach(function (r) {
          var tr = document.createElement("tr");
          if (pending) {
            if (r.pending_only) {
              tr.append(cell(r.sno, "num"), cell(r.code, "master-table__code"), cell(r.name), cell(r.pending, "num"),
                cell(""), cell(""), cell(""), cell(""), cell(""));
            } else {
              tr.append(cell(r.sno, "num"), cell(r.code, "master-table__code"), cell(r.name), cell(r.pending, "num"),
                cell(r.in_process, "num"), cell(r.closing, "num"), cell(r.required, "num"), cell(r.man_hrs, "num"),
                cell(r.time_per_unit, "num"));
            }
          } else if (r.pending_only) {
            tr.append(cell(r.sno, "num"), cell(r.code, "master-table__code"), cell(r.name), cell(r.pending, "num"),
              cell(""), cell(""), cell(""), cell(""), cell(""), cell(""), cell(""));
          } else {
            tr.append(cell(r.sno, "num"), cell(r.code, "master-table__code"), cell(r.name), cell(r.pending, "num"),
              cell(r.cur_sale, "num"), cell(r.last_sale, "num"), cell(r.in_process, "num"), cell(r.closing, "num"),
              cell(r.required, "num"), cell(r.man_hrs, "num"), cell(r.time_per_unit, "num"));
          }
          tbody.appendChild(tr);
        });
        totalHrs.textContent = res.body.total_man_hrs;
        emptyNote.hidden = res.body.rows.length > 0;
      });
  }

  if (daysInput) daysInput.value = initial.days;
  startDate.value = window.DateMask.toDisplay(initial.start_date);
  endDate.value = window.DateMask.toDisplay(initial.end_date);
  root.querySelector("[data-view]").addEventListener("click", view);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    if (!validRange()) return;
    window.location.href = root.dataset.exportUrl + "?" + query();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });
  setDayHeaders();
  view();
})();
