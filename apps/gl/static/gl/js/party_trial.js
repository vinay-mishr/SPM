/* Accounts > Trial Balance > Party Trial -- direct port of the VFP "PARTY
   TRIAL" report: 6 radio modes (same per-party balance formula as
   apps.gl.party_ledger, as-of RUN DATE like apps.gl.main_trial), mode 6
   ("SUB TRIAL LIST") enables a listbox of gled_mst sub-ledger groups to
   pick from. Columns shown depend on the mode: DEBIT+CREDIT, DEBIT only,
   or CREDIT only. VIEW loads it, PRINT uses window.print(), EXCEL
   downloads the workbook. */
(function () {
  "use strict";

  var root = document.querySelector("[data-party-trial]");
  if (!root) return;

  var modeRadios = root.querySelectorAll('input[name="pt-mode"]');
  var sublist = root.querySelector("[data-sublist]");
  var runDate = root.querySelector("[data-run-date]");
  var alertBox = root.querySelector("[data-alert]");
  var result = root.querySelector("[data-result]");
  var thead = root.querySelector("[data-r-thead]");
  var tbody = root.querySelector("[data-r-rows]");
  var tfoot = root.querySelector("[data-r-tfoot]");
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

  function currentMode() {
    var checked = root.querySelector('input[name="pt-mode"]:checked');
    return checked ? parseInt(checked.value, 10) : 1;
  }

  function loadSublist() {
    fetch(root.dataset.groupsUrl, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (body) {
        sublist.textContent = "";
        (body.groups || []).forEach(function (g) {
          var opt = document.createElement("option");
          opt.value = g.code;
          opt.textContent = g.code + " - " + g.name;
          sublist.appendChild(opt);
        });
      });
  }

  modeRadios.forEach(function (radio) {
    radio.addEventListener("change", function () {
      var isSub = currentMode() === 6;
      sublist.disabled = !isSub;
      if (isSub && !sublist.options.length) loadSublist();
      if (isSub && sublist.options.length && sublist.selectedIndex < 0) sublist.selectedIndex = 0;
    });
  });

  function query() {
    var params = new URLSearchParams();
    params.set("mode", currentMode());
    params.set("run_date", dmyToIso(runDate.value));
    if (currentMode() === 6 && sublist.value) params.set("group_code", sublist.value);
    return params.toString();
  }

  function renderHead(columns) {
    var cols = ["S.NO", "LEDGER DESCRIPTION", "CITY"];
    if (columns === "both" || columns === "debit") cols.push("DEBIT");
    if (columns === "both" || columns === "credit") cols.push("CREDIT");
    var tr = document.createElement("tr");
    cols.forEach(function (c, i) { tr.appendChild(cell(c, i >= 3 ? "num" : "")); });
    thead.textContent = "";
    thead.appendChild(tr);
    return cols.length;
  }

  function view() {
    show("");
    printBtn.disabled = true;
    if (currentMode() === 6 && !sublist.value) { show("Select a sub-ledger from the list."); return; }
    fetch(root.dataset.dataUrl + "?" + query(), { credentials: "same-origin" })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        if (!res.ok) { show(res.body.message || "Could not load the Party Trial."); result.hidden = true; return; }
        var d = res.body;
        root.querySelector("[data-r-title]").textContent = d.title + " " + dmy(d.run_date);
        var colCount = renderHead(d.columns);
        tbody.textContent = "";
        if (!d.rows.length) {
          var tr = document.createElement("tr");
          tr.className = "cb-empty";
          var td = document.createElement("td");
          td.colSpan = colCount;
          td.textContent = "No parties match this mode as on this date.";
          tr.appendChild(td);
          tbody.appendChild(tr);
        }
        d.rows.forEach(function (r) {
          var tr = document.createElement("tr");
          tr.appendChild(cell(r.sno));
          tr.appendChild(cell(r.name));
          tr.appendChild(cell(r.city));
          if (d.columns === "both" || d.columns === "debit") tr.appendChild(cell(r.debit, "num"));
          if (d.columns === "both" || d.columns === "credit") tr.appendChild(cell(r.credit, "num"));
          tbody.appendChild(tr);
        });
        var totalTr = document.createElement("tr");
        totalTr.className = "cb-total";
        totalTr.appendChild(cell(""));
        totalTr.appendChild(cell("TOTAL"));
        totalTr.appendChild(cell(""));
        if (d.columns === "both" || d.columns === "debit") totalTr.appendChild(cell(d.total_debit, "num"));
        if (d.columns === "both" || d.columns === "credit") totalTr.appendChild(cell(d.total_credit, "num"));
        tfoot.textContent = "";
        tfoot.appendChild(totalTr);
        result.hidden = false;
        printBtn.disabled = false;
      });
  }

  root.querySelector("[data-view]").addEventListener("click", view);
  printBtn.addEventListener("click", function () { window.print(); });
  root.querySelector("[data-excel]").addEventListener("click", function () {
    if (currentMode() === 6 && !sublist.value) { show("Select a sub-ledger from the list."); return; }
    window.location.href = root.dataset.exportUrl + "?" + query();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  var initial = JSON.parse(document.getElementById("pt-initial-data").textContent);
  runDate.value = dmy(initial.run_date);
})();
