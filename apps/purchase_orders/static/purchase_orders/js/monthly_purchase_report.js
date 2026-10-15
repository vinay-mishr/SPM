/* Monthly Purchase Report — read-only. Old VFP form/report: PURCHASE REPORT. */
(function () {
  "use strict";

  var root = document.querySelector("[data-monthly-purchase-report]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var dateError = root.querySelector("[data-date-error]");
  var totalGross = root.querySelector("[data-total-gross]");
  var totalNet = root.querySelector("[data-total-net]");
  var toast = document.querySelector("[data-toast]");

  var initial = JSON.parse(document.getElementById("mpr-initial-data").textContent);

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function dmy(iso) {
    if (!iso) return "";
    var p = String(iso).split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : iso;
  }

  function money(v) { return Number(v || 0).toFixed(2); }

  function cell(text, className) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (className) td.className = className;
    return td;
  }

  function render(rows) {
    tbody.textContent = "";
    var gross = 0, net = 0;
    rows.forEach(function (r) {
      gross += Number(r.gross_amount || 0);
      net += Number(r.net_amount || 0);
      var tr = document.createElement("tr");
      tr.append(
        cell(r.code, "master-table__code"),
        cell(r.party_name),
        cell(r.bill_no),
        cell(dmy(r.bill_date)),
        cell(r.mrn_no),
        cell(dmy(r.mrn_date)),
        cell(money(r.gross_amount), "num"),
        cell(money(r.net_amount), "num")
      );
      tbody.appendChild(tr);
    });
    emptyNote.hidden = rows.length > 0;
    totalGross.textContent = money(gross);
    totalNet.textContent = money(net);
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

  function search() {
    if (!validRange()) { render([]); return; }
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
  root.querySelector("[data-excel]").addEventListener("click", function () {
    if (!validRange()) return;
    window.location.href = root.dataset.exportUrl + "?" + currentQuery().toString();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () {
    window.location.href = root.dataset.exitUrl;
  });

  startDate.value = window.DateMask.toDisplay(initial.start_date);
  endDate.value = window.DateMask.toDisplay(initial.end_date);
  render(initial.rows || []);
  startDate.focus();
})();
