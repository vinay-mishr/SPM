/* Accounts > Trial Balance > Group Trial -- direct port of the VFP
   "GROUPWISE MAIN TRIAL" report: same per-ledger balance-as-on-RUN-DATE
   logic as apps.gl.main_trial.js, grouped under a "<<group name>>" heading
   per group1/gl_type with its own subtotal, plus a grand total. VIEW loads
   it, PRINT uses window.print(), EXCEL downloads the workbook. */
(function () {
  "use strict";

  var root = document.querySelector("[data-group-trial]");
  if (!root) return;

  var runDate = root.querySelector("[data-run-date]");
  var alertBox = root.querySelector("[data-alert]");
  var result = root.querySelector("[data-result]");
  var rows = root.querySelector("[data-r-rows]");
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
    params.set("run_date", dmyToIso(runDate.value));
    return params.toString();
  }

  function view() {
    show("");
    printBtn.disabled = true;
    fetch(root.dataset.dataUrl + "?" + query(), { credentials: "same-origin" })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        if (!res.ok) { show(res.body.message || "Could not load the Group Trial."); result.hidden = true; return; }
        var d = res.body;
        root.querySelector("[data-r-date]").textContent = dmy(d.run_date);
        root.querySelector("[data-r-grand-debit]").textContent = d.grand_debit;
        root.querySelector("[data-r-grand-credit]").textContent = d.grand_credit;
        root.querySelector("[data-r-difference]").textContent = "Difference " + d.difference;
        rows.textContent = "";
        if (!d.groups.length) {
          var tr = document.createElement("tr");
          tr.className = "cb-empty";
          var td = document.createElement("td");
          td.colSpan = 4;
          td.textContent = "No group balances as on this date.";
          tr.appendChild(td);
          rows.appendChild(tr);
        }
        d.groups.forEach(function (g) {
          rows.appendChild(row("cb-balance", [cell(""), cell("<<" + g.grp_name + ">>"), cell(""), cell("")]));
          g.ledgers.forEach(function (l) {
            rows.appendChild(row("", [
              cell((l.has_subledger ? "*" : "") + l.code), cell(l.desc), cell(l.debit, "num"), cell(l.credit, "num"),
            ]));
          });
          rows.appendChild(row("cb-total", [cell(""), cell("TOTAL"), cell(g.total_debit, "num"), cell(g.total_credit, "num")]));
        });
        result.hidden = false;
        printBtn.disabled = false;
      });
  }

  root.querySelector("[data-view]").addEventListener("click", view);
  printBtn.addEventListener("click", function () { window.print(); });
  root.querySelector("[data-excel]").addEventListener("click", function () {
    window.location.href = root.dataset.exportUrl + "?" + query();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  var initial = JSON.parse(document.getElementById("gt-initial-data").textContent);
  runDate.value = dmy(initial.run_date);
})();
