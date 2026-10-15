/* Monthly Order Report — read-only, flat rows (not grouped). New report, no
   corresponding old VFP form under this exact name -- see services.monthly_order_report. */
(function () {
  "use strict";

  var root = document.querySelector("[data-monthly-order-report]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var dateError = root.querySelector("[data-date-error]");
  var headingRange = root.querySelector("[data-heading-range]");
  var toast = document.querySelector("[data-toast]");

  var initial = JSON.parse(document.getElementById("mor-initial-data").textContent);

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function dmy(iso) {
    if (!iso) return "";
    var p = String(iso).split("-");
    return p.length === 3 ? p[2] + "-" + p[1] + "-" + p[0] : iso;
  }

  function qty(v) { return Number(v || 0).toFixed(2); }

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
      var balCell = cell(qty(r.bal_qty), "num");
      if (Number(r.bal_qty) < 0) balCell.setAttribute("data-negative", "");
      tr.append(
        cell(r.item_name),
        cell(r.ord_no, "master-table__code"),
        cell(dmy(r.ord_date)),
        cell(r.party_name),
        cell(r.city),
        cell(qty(r.ord_qty), "num"),
        cell(qty(r.rec_qty), "num"),
        balCell,
        cell(dmy(r.despatch_date))
      );
      tbody.appendChild(tr);
    });
    emptyNote.hidden = rows.length > 0;
  }

  function currentQuery() {
    var params = new URLSearchParams();
    params.set("start_date", window.DateMask.toIso(startDate.value));
    params.set("end_date", window.DateMask.toIso(endDate.value));
    return params;
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

  function updateHeading() {
    headingRange.textContent = "ORDER REPORT AS ON " + dmy(window.DateMask.toIso(startDate.value)) +
      " TO " + dmy(window.DateMask.toIso(endDate.value));
  }

  function search() {
    if (!validRange()) { render([]); return; }
    updateHeading();
    fetch(root.dataset.dataUrl + "?" + currentQuery().toString(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        if (!res.ok) { showToast(res.body.message || "Could not load the report.", "error"); return; }
        render(res.body.rows || []);
      })
      .catch(function () { showToast("Could not reach the server.", "error"); });
  }

  startDate.addEventListener("change", search);
  endDate.addEventListener("change", search);
  root.querySelector("[data-generate]").addEventListener("click", search);
  root.querySelector("[data-refresh]").addEventListener("click", search);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    if (!validRange()) return;
    window.location.href = root.dataset.exportUrl + "?" + currentQuery().toString();
  });
  root.querySelector("[data-print]").addEventListener("click", function () {
    if (!validRange()) return;
    window.open(root.dataset.printUrl + "?" + currentQuery().toString(), "_blank");
  });
  root.querySelector("[data-exit]").addEventListener("click", function () {
    window.location.href = root.dataset.exitUrl;
  });

  startDate.value = window.DateMask.toDisplay(initial.start_date);
  endDate.value = window.DateMask.toDisplay(initial.end_date);
  updateHeading();
  render(initial.rows || []);
  startDate.focus();
})();
