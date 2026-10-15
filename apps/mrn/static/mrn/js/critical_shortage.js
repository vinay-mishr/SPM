/* Critical Shortage -- read-only. Old VFP: STOCK STATEMENT (critical shortage). */
(function () {
  "use strict";

  var root = document.querySelector("[data-critical-shortage]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var days1 = root.querySelector("[data-days1]");
  var days2 = root.querySelector("[data-days2]");
  var dateError = root.querySelector("[data-date-error]");
  var toast = document.querySelector("[data-toast]");

  var initial = JSON.parse(document.getElementById("cr-initial-data").textContent);

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

  function render(rows) {
    tbody.textContent = "";
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.append(cell(r.sno), cell(r.item_code, "master-table__code"), cell(r.item_name), cell(r.unit),
        cell(r.balance, "num"), cell(r.value, "num"), cell(r.cur_use, "num"), cell(r.last_use, "num"),
        cell(r.planning, "num"), cell(r.shortage, "num"), cell(r.excess, "num"), cell(r.suppliers[0]));
      tbody.appendChild(tr);
    });
    emptyNote.hidden = rows.length > 0;
  }

  function validRange() {
    var s = window.DateMask.toIso(startDate.value);
    var e = window.DateMask.toIso(endDate.value);
    if (!s || !e) { dateError.textContent = "Enter both dates."; dateError.hidden = false; return false; }
    if (s > e) { dateError.textContent = "Start Date cannot be later than End Date."; dateError.hidden = false; return false; }
    dateError.hidden = true;
    return true;
  }

  function currentQuery() {
    var params = new URLSearchParams();
    params.set("start_date", window.DateMask.toIso(startDate.value));
    params.set("end_date", window.DateMask.toIso(endDate.value));
    params.set("days1", days1.value || "30");
    params.set("days2", days2.value || "30");
    return params;
  }

  function view() {
    if (!validRange()) { render([]); return; }
    fetch(root.dataset.dataUrl + "?" + currentQuery().toString(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        if (!res.ok) { showToast(res.body.message || "Could not load the report.", "error"); return; }
        render(res.body.rows || []);
      })
      .catch(function () { showToast("Could not reach the server.", "error"); });
  }

  root.querySelector("[data-view]").addEventListener("click", view);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    if (!validRange()) return;
    window.location.href = root.dataset.exportUrl + "?" + currentQuery().toString();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  startDate.value = window.DateMask.toDisplay(initial.start_date);
  endDate.value = window.DateMask.toDisplay(initial.end_date);
  render(initial.rows || []);
})();
