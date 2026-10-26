/* Accounts > Ledger Printing > Ledger Groupwise -- direct port of the VFP
   "LEDGER" (groupwise) screen: a grid of ledgers with a tick-box per row
   (TAG ALL / UNTAG ALL / click a row to toggle), SEARCH filters the grid by
   ledger-name prefix, VIEW renders one apps.gl.main_ledger-style block per
   ticked ledger. */
(function () {
  "use strict";

  var root = document.querySelector("[data-ledger-groupwise]");
  if (!root) return;

  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var search = root.querySelector("[data-search]");
  var alertBox = root.querySelector("[data-alert]");
  var rowsEl = root.querySelector("[data-rows]");
  var result = root.querySelector("[data-result]");
  var blocksEl = root.querySelector("[data-blocks]");
  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;

  var tagged = {};

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

  function renderRows(ledgerRows) {
    rowsEl.textContent = "";
    ledgerRows.forEach(function (l) {
      var checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = Boolean(tagged[l.code]);
      checkbox.addEventListener("change", function () {
        if (checkbox.checked) tagged[l.code] = l.desc; else delete tagged[l.code];
        tr.classList.toggle("is-tagged", checkbox.checked);
      });
      var flagCell = document.createElement("td");
      flagCell.className = "lgw-flag";
      flagCell.appendChild(checkbox);
      var tr = row(tagged[l.code] ? "is-tagged" : "", [cell(l.code), cell(l.desc)]);
      tr.appendChild(flagCell);
      tr.addEventListener("click", function (e) {
        if (e.target !== checkbox) checkbox.click();
      });
      rowsEl.appendChild(tr);
    });
    if (!ledgerRows.length) {
      var empty = document.createElement("tr");
      empty.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 3;
      td.textContent = "No ledgers found.";
      empty.appendChild(td);
      rowsEl.appendChild(empty);
    }
  }

  function loadRows() {
    var params = new URLSearchParams();
    params.set("name", search.value.trim());
    fetch(root.dataset.rowsUrl + "?" + params.toString(), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (body) { renderRows(body.rows || []); });
  }

  root.querySelector("[data-ok]").addEventListener("click", loadRows);

  root.querySelector("[data-tag-all]").addEventListener("click", function () {
    rowsEl.querySelectorAll("tr").forEach(function (tr) {
      var checkbox = tr.querySelector('input[type="checkbox"]');
      if (checkbox && !checkbox.checked) checkbox.click();
    });
  });
  root.querySelector("[data-untag-all]").addEventListener("click", function () {
    rowsEl.querySelectorAll("tr").forEach(function (tr) {
      var checkbox = tr.querySelector('input[type="checkbox"]');
      if (checkbox && checkbox.checked) checkbox.click();
    });
  });

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
    var codes = Object.keys(tagged);
    if (!codes.length) { show("Tag at least one ledger."); return; }
    fetch(root.dataset.dataUrl, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrf, "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify({
        codes: codes, start_date: dmyToIso(startDate.value), end_date: dmyToIso(endDate.value),
      }),
    })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        if (!res.ok) { show(res.body.message || "Could not load the ledgers."); result.hidden = true; return; }
        var d = res.body;
        blocksEl.textContent = "";
        if (!d.blocks.length) {
          var p = document.createElement("p");
          p.textContent = "No activity for the tagged ledgers in this date range.";
          blocksEl.appendChild(p);
        }
        d.blocks.forEach(function (b) { blocksEl.appendChild(buildBlock(b, d.start_date, d.end_date)); });
        result.hidden = false;
      });
  }

  root.querySelector("[data-view]").addEventListener("click", view);
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  var initial = JSON.parse(document.getElementById("lgw-initial-data").textContent);
  startDate.value = dmy(initial.start_date);
  endDate.value = dmy(initial.end_date);
  loadRows();
})();
