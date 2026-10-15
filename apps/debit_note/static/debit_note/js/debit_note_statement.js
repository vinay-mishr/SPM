/* Debit Note Statement: debit notes in a date range, with totals and Excel. */
(function () {
  "use strict";

  var root = document.querySelector("[data-st]");
  if (!root) return;

  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var rows = root.querySelector("[data-rows]");
  var totalCell = root.querySelector("[data-total]");
  var alertBox = root.querySelector("[data-alert]");

  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (cls) td.className = cls;
    return td;
  }

  function dmy(iso) {
    var p = String(iso || "").split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : "";
  }

  function query() {
    var params = new URLSearchParams();
    params.set("start_date", window.DateMask.toIso(startDate.value));
    params.set("end_date", window.DateMask.toIso(endDate.value));
    return params.toString();
  }

  function show() {
    alertBox.hidden = true;
    fetch(root.dataset.dataUrl + "?" + query(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        if (!res.ok) { alertBox.textContent = res.body.message || "Could not load the statement."; alertBox.hidden = false; return; }
        rows.textContent = "";
        res.body.rows.forEach(function (r) {
          var tr = document.createElement("tr");
          tr.append(cell(r.dn_no), cell(dmy(r.dn_date)), cell(r.bill_no), cell(dmy(r.bill_date)), cell(r.party),
            cell(r.city), cell(r.amount, "num"));
          rows.appendChild(tr);
        });
        if (!res.body.rows.length) {
          var empty = document.createElement("tr");
          empty.className = "empty";
          var td = document.createElement("td");
          td.colSpan = 7;
          td.textContent = "No debit notes in this date range.";
          empty.appendChild(td);
          rows.appendChild(empty);
        }
        totalCell.textContent = res.body.total;
      });
  }

  root.querySelector("[data-show]").addEventListener("click", show);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    window.location.href = root.dataset.exportUrl + "?" + query();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  var today = new Date().toISOString().slice(0, 10);
  startDate.value = window.DateMask.toDisplay(today);
  endDate.value = window.DateMask.toDisplay(today);
  show();
})();
