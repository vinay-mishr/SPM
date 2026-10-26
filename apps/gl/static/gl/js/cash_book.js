/* Accounts > Book Printing > Cash Book -- direct port of the VFP "CASH BOOK"
   PRN report: opening/closing balance per day, debit/credit lines in
   between, VIEW loads it, PRINT uses window.print() on the same letter
   (apps.gl.voucher_printing's own convention). */
(function () {
  "use strict";

  var root = document.querySelector("[data-cash-book]");
  if (!root) return;

  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var alertBox = root.querySelector("[data-alert]");
  var result = root.querySelector("[data-result]");
  var body = root.querySelector("[data-r-body]");
  var printBtn = root.querySelector("[data-print]");

  function show(msg) {
    alertBox.textContent = msg || "";
    alertBox.hidden = !msg;
  }
  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (cls) td.className = cls;
    return td;
  }
  function row(cls, cells) {
    var tr = document.createElement("tr");
    tr.className = cls;
    cells.forEach(function (c) { tr.appendChild(c); });
    return tr;
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

  function query() {
    var params = new URLSearchParams();
    params.set("start_date", dmyToIso(startDate.value));
    params.set("end_date", dmyToIso(endDate.value));
    return params.toString();
  }

  function view() {
    show("");
    printBtn.disabled = true;
    fetch(root.dataset.dataUrl + "?" + query(), { credentials: "same-origin" })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        if (!res.ok) { show(res.body.message || "Could not load the Cash Book."); result.hidden = true; return; }
        var d = res.body;
        root.querySelector("[data-r-start]").textContent = dmy(d.start_date);
        root.querySelector("[data-r-end]").textContent = dmy(d.end_date);
        body.textContent = "";
        if (!d.days.length) {
          body.appendChild(row("cb-empty", [(function () {
            var td = document.createElement("td");
            td.colSpan = 4;
            td.textContent = "No Cash Book transactions in this date range.";
            return td;
          })()]));
        }
        d.days.forEach(function (day) {
          body.appendChild(row("cb-balance", [
            cell(dmy(day.date)),
            cell("OPENING BALANCE AS ON " + dmy(day.date)),
            cell(""), cell(day.opening_balance + " " + day.opening_side, "num"),
          ]));
          day.lines.forEach(function (l) {
            body.appendChild(row("", [cell(""), cell(l.account), cell(l.debit, "num"), cell(l.credit, "num")]));
            body.appendChild(row("cb-narration", [cell(""), cell(l.prefix + " " + l.narration), cell(""), cell("")]));
          });
          body.appendChild(row("cb-balance", [
            cell(""), cell("CLOSING BALANCE AS ON " + dmy(day.date)),
            cell(""), cell(day.closing_balance + " " + day.closing_side, "num"),
          ]));
          body.appendChild(row("cb-total", [cell(""), cell("TOTAL"), cell(day.total_debit, "num"), cell(day.total_credit, "num")]));
        });
        result.hidden = false;
        printBtn.disabled = false;
      });
  }

  root.querySelector("[data-view]").addEventListener("click", view);
  printBtn.addEventListener("click", function () { window.print(); });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  var initial = JSON.parse(document.getElementById("cb-initial-data").textContent);
  startDate.value = dmy(initial.start_date);
  endDate.value = dmy(initial.end_date);
})();
