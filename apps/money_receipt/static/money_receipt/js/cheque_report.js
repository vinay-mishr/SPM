/* Money Receipts > Cheque Report: every chq_file row in a date range, split
   into SBI/HDFC columns -- direct port of the VFP "CHEQUE REPORT" Excel macro. */
(function () {
  "use strict";

  var root = document.querySelector("[data-cheque-report]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var toast = document.querySelector("[data-toast]");
  var initial = JSON.parse(document.getElementById("cq-initial-data").textContent);

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (cls) td.className = cls;
    return td;
  }

  function dmy(iso) {
    if (!iso) return "";
    var p = String(iso).split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : iso;
  }

  function query() {
    var params = new URLSearchParams();
    params.set("start_date", window.DateMask.toIso(startDate.value));
    params.set("end_date", window.DateMask.toIso(endDate.value));
    return params.toString();
  }

  function view() {
    fetch(root.dataset.dataUrl + "?" + query(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        tbody.textContent = "";
        if (!res.ok) { showToast(res.body.message || "Could not load the report.", "error"); return; }
        res.body.rows.forEach(function (r, i) {
          var tr = document.createElement("tr");
          tr.append(cell(i + 1), cell(r.chq_no), cell(dmy(r.chq_dt)), cell(r.party_name), cell(r.bank),
            cell(r.sbi_amount, "num"), cell(r.hdfc_amount, "num"));
          tbody.appendChild(tr);
        });
        emptyNote.hidden = res.body.rows.length > 0;
        root.querySelector("[data-g-sbi]").value = res.body.totals.sbi;
        root.querySelector("[data-g-hdfc]").value = res.body.totals.hdfc;
      });
  }

  startDate.value = window.DateMask.toDisplay(initial.start_date);
  endDate.value = window.DateMask.toDisplay(initial.end_date);
  root.querySelector("[data-view]").addEventListener("click", view);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    window.location.href = root.dataset.exportUrl + "?" + query();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });
  view();
})();
