/* Raw Material Stock Ledger -- read-only. Old VFP: RAW MATERIAL STOCK LEDGER. */
(function () {
  "use strict";

  var root = document.querySelector("[data-stock-ledger]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var grade = root.querySelector("[data-grade]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var dateError = root.querySelector("[data-date-error]");
  var toast = document.querySelector("[data-toast]");

  var initial = JSON.parse(document.getElementById("sl-initial-data").textContent);

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function mode() { return root.querySelector('input[name="sl-mode"]:checked').value; }

  function applyMode() {
    var single = mode() === "single";
    grade.disabled = !single;
    if (!single) grade.value = "";
    if (single) grade.focus();
  }
  root.querySelectorAll('input[name="sl-mode"]').forEach(function (r) { r.addEventListener("change", applyMode); });

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
      tr.append(cell(r.item_code, "master-table__code"), cell(r.item_name), cell(r.balance, "num"), cell(r.value, "num"), cell(r.weight, "num"));
      tbody.appendChild(tr);
    });
    emptyNote.hidden = rows.length > 0;
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

  function currentQuery() {
    var params = new URLSearchParams();
    params.set("start_date", window.DateMask.toIso(startDate.value));
    params.set("end_date", window.DateMask.toIso(endDate.value));
    params.set("mode", mode());
    if (mode() === "single") params.set("grade", grade.value.trim());
    return params;
  }

  function view() {
    if (!validRange()) { render([]); return; }
    if (mode() === "single" && !grade.value.trim()) { showToast("Enter a grade first.", "error"); return; }
    fetch(root.dataset.dataUrl + "?" + currentQuery().toString(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        if (!res.ok) { showToast(res.body.message || "Could not load the ledger.", "error"); return; }
        render(res.body.rows || []);
      })
      .catch(function () { showToast("Could not reach the server.", "error"); });
  }

  function guard(action) {
    if (!validRange()) return;
    if (mode() === "single" && !grade.value.trim()) { showToast("Enter a grade first.", "error"); return; }
    action();
  }

  root.querySelector("[data-view]").addEventListener("click", view);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    guard(function () { window.location.href = root.dataset.exportUrl + "?" + currentQuery().toString(); });
  });
  root.querySelector("[data-print]").addEventListener("click", function () {
    guard(function () { window.open(root.dataset.printUrl + "?" + currentQuery().toString() + "&preview=1", "_blank"); });
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  startDate.value = window.DateMask.toDisplay(initial.start_date);
  endDate.value = window.DateMask.toDisplay(initial.end_date);
  applyMode();
  render(initial.rows || []);
})();
