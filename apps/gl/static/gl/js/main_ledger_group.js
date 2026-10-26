/* Accounts > Ledger Printing > Main Ledger Group Wise -- direct port of the
   VFP "LEDGER PRINTING" form: same per-ledger opening/closing balance block
   layout as apps.gl.main_ledger.js, just one GROUP lookup (group1) instead
   of ALL/SINGLE + a single account, and VIEW/EXIT only (matching the VFP
   form's own screenshot). */
(function () {
  "use strict";

  var root = document.querySelector("[data-main-ledger-group]");
  if (!root) return;

  var group = root.querySelector("[data-group]");
  var grpCode = root.querySelector("[data-grp-code]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var alertBox = root.querySelector("[data-alert]");
  var result = root.querySelector("[data-result]");
  var blocksEl = root.querySelector("[data-blocks]");

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

  window.HelpLookup.attach(group, {
    endpoint: root.dataset.groupsUrl, resultsKey: "groups", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }],
    title: "Group",
    onSelect: function (g) { grpCode.value = g.code; },
  });
  group.addEventListener("input", function () {
    if (!group.value) grpCode.value = "";
  });

  function query() {
    var params = new URLSearchParams();
    params.set("grp_code", grpCode.value);
    params.set("start_date", dmyToIso(startDate.value));
    params.set("end_date", dmyToIso(endDate.value));
    return params.toString();
  }

  function buildBlock(b, start, end) {
    var block = document.createElement("div");
    block.className = "ml-ledger-block";

    var head = document.createElement("div");
    head.className = "vp-head ml-ledger-head";
    head.innerHTML =
      '<p class="vp-brand">' + root.dataset.brandName + "</p>" +
      "<p>" + root.dataset.brandAddress + "</p>" +
      "<p class=\"cb-range\">MAIN LEDGER FROM " + dmy(start) + " TO " + dmy(end) + "</p>" +
      '<p class="ml-ledger-code">A/C CODE : ' + b.code + "</p>" +
      "<p>A/C NAME : " + b.desc + "</p>";
    block.appendChild(head);

    var table = document.createElement("table");
    table.className = "vp-table cb-table";
    table.innerHTML = "<thead><tr><th>VNO</th><th>V.DATE</th><th>NARRATION</th><th class=\"num\">DEBIT</th>" +
      "<th class=\"num\">CREDIT</th><th class=\"num\">BALANCE</th></tr></thead>";
    var body = document.createElement("tbody");

    if (b.has_opening) {
      body.appendChild(row("cb-balance", [
        cell(""), cell(""), cell("OPENING BALANCE"), cell(""), cell(""),
        cell(b.opening_balance + " " + b.opening_side, "num"),
      ]));
    }
    b.lines.forEach(function (l) {
      body.appendChild(row("", [
        cell(l.vno), cell(dmy(l.date)), cell(l.narration1), cell(l.debit, "num"), cell(l.credit, "num"),
        cell(l.balance + " " + l.side, "num"),
      ]));
      if (l.narration2) {
        body.appendChild(row("cb-narration", [cell(""), cell(""), cell(l.narration2), cell(""), cell(""), cell("")]));
      }
    });
    body.appendChild(row("cb-total", [
      cell(""), cell(""), cell("TOTAL"), cell(b.total_debit, "num"), cell(b.total_credit, "num"), cell(""),
    ]));
    body.appendChild(row("cb-balance", [
      cell(""), cell(""), cell("CLOSING BALANCE"), cell(""), cell(""),
      cell(b.closing_balance + " " + b.closing_side, "num"),
    ]));
    table.appendChild(body);
    block.appendChild(table);
    return block;
  }

  function view() {
    show("");
    if (!grpCode.value) { show("Select a Group."); return; }
    fetch(root.dataset.dataUrl + "?" + query(), { credentials: "same-origin" })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        if (!res.ok) { show(res.body.message || "Could not load the Ledger Printing report."); result.hidden = true; return; }
        var d = res.body;
        blocksEl.textContent = "";
        if (!d.blocks.length) {
          var p = document.createElement("p");
          p.textContent = "No activity for this Group in this date range.";
          blocksEl.appendChild(p);
        }
        d.blocks.forEach(function (b) { blocksEl.appendChild(buildBlock(b, d.start_date, d.end_date)); });
        result.hidden = false;
      });
  }

  root.querySelector("[data-view]").addEventListener("click", view);
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  var initial = JSON.parse(document.getElementById("mlgr-initial-data").textContent);
  startDate.value = dmy(initial.start_date);
  endDate.value = dmy(initial.end_date);
})();
