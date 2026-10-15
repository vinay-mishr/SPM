/* Job Card Listing -- legacy JOB CARD LIST (date range, Excel export). */
(function () {
  "use strict";

  var root = document.querySelector("[data-job-listing]");
  if (!root) return;

  var startInput = root.querySelector("[data-start-date]");
  var endInput = root.querySelector("[data-end-date]");
  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var totalCell = root.querySelector("[data-total]");
  var alertBox = root.querySelector("[data-listing-alert]");
  var initial = JSON.parse(document.getElementById("jc-listing-initial").textContent);

  function dmy(iso) {
    if (!iso) return "";
    var p = String(iso).split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : iso;
  }

  function cell(text, className) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (className) td.className = className;
    return td;
  }

  function query() {
    var params = new URLSearchParams();
    params.set("start_date", window.DateMask.toIso(startInput.value));
    params.set("end_date", window.DateMask.toIso(endInput.value));
    return params.toString();
  }

  function show() {
    alertBox.hidden = true;
    fetch(root.dataset.dataUrl + "?" + query(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        if (!res.ok) { alertBox.textContent = res.body.message || "Could not load the listing."; alertBox.hidden = false; return; }
        tbody.textContent = "";
        res.body.rows.forEach(function (r, i) {
          var tr = document.createElement("tr");
          tr.append(cell(i + 1), cell(r.job_no), cell(dmy(r.date)), cell(r.code), cell(r.item_name), cell(r.unit),
            cell(r.qty, "num"), cell(r.prod, "num"), cell(r.time_reqd, "num"), cell(r.time_taken, "num"),
            cell(r.closed), cell(dmy(r.close_date)), cell(r.supervisor), cell(r.rate, "num"), cell(r.amount, "num"));
          tbody.appendChild(tr);
        });
        emptyNote.hidden = res.body.rows.length > 0;
        totalCell.textContent = res.body.total;
      });
  }

  function exportExcel() {
    window.location.href = root.dataset.exportUrl + "?" + query();
  }

  startInput.value = window.DateMask.toDisplay(initial.start_date);
  endInput.value = window.DateMask.toDisplay(initial.end_date);
  root.querySelector("[data-show]").addEventListener("click", show);
  root.querySelector("[data-export]").addEventListener("click", exportExcel);
  show();
})();
