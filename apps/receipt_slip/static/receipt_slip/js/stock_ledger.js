/* Stock > Stock Ledger -- opening, receipts, issues and closing per item (VFP STOCK LEDGER). */
(function () {
  "use strict";

  var root = document.querySelector("[data-stock-ledger]");
  if (!root) return;

  var output = root.querySelector("[data-output]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var dateError = root.querySelector("[data-date-error]");
  var itemSearch = root.querySelector("[data-item-search]");
  var itemCode = root.querySelector("[data-item-code]");
  var toast = document.querySelector("[data-toast]");
  var initial = JSON.parse(document.getElementById("sl-initial-data").textContent);

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function cell(text, className) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (className) td.className = className;
    return td;
  }

  function dmy(iso) {
    if (!iso) return "";
    var p = String(iso).split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : iso;
  }

  function scope() { return root.querySelector("[data-scope]:checked").value; }

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

  function query() {
    var params = new URLSearchParams();
    params.set("start_date", window.DateMask.toIso(startDate.value));
    params.set("end_date", window.DateMask.toIso(endDate.value));
    if (scope() === "single") params.set("part_code", itemCode.value);
    return params.toString();
  }

  function renderPart(p) {
    var wrap = document.createElement("div");
    wrap.className = "sl-part";
    var code = document.createElement("p");
    code.textContent = "ITEM CODE : " + p.code;
    var name = document.createElement("p");
    name.textContent = "ITEM NAME : " + p.name;
    var table = document.createElement("table");
    table.className = "table master-table srr-table";
    table.innerHTML = "<thead><tr><th>REF. DATE</th><th>REF.NO</th><th>PARTY</th><th class=\"num\">QTY RECD</th><th class=\"num\">QTY ISSUED</th><th class=\"num\">BALANCE</th></tr></thead>";
    var tbody = document.createElement("tbody");
    var opening = document.createElement("tr");
    opening.append(cell("OPENING BALANCE"), cell(""), cell(""), cell(""), cell(""), cell(p.opening, "num"));
    tbody.appendChild(opening);
    p.rows.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.append(cell(dmy(r.date)), cell(r.ref_no), cell(r.party), cell(r.rec, "num"), cell(r.iss, "num"), cell(r.bal, "num"));
      tbody.appendChild(tr);
    });
    var total = document.createElement("tr");
    total.className = "pl-total";
    total.append(cell("TOTAL"), cell(""), cell(""), cell(p.rec_total, "num"), cell(p.iss_total, "num"), cell(p.closing, "num"));
    tbody.appendChild(total);
    table.appendChild(tbody);
    wrap.append(code, name, table);
    return wrap;
  }

  function view() {
    if (!validRange()) return;
    if (scope() === "single" && !itemCode.value) { showToast("Select an item first.", "error"); return; }
    fetch(root.dataset.dataUrl + "?" + query(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        output.textContent = "";
        if (!res.ok) { showToast(res.body.message || "Could not load the ledger.", "error"); return; }
        if (!res.body.parts.length) { showToast("No items found.", "error"); return; }
        res.body.parts.forEach(function (p) { output.appendChild(renderPart(p)); });
      });
  }

  window.HelpLookup.attach(itemSearch, {
    endpoint: root.dataset.partsUrl, resultsKey: "parts", valueField: "code",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "unit", label: "Unit" }],
    title: "Item",
    onSelect: function (row) { itemCode.value = row.code; itemSearch.value = row.name; },
  });

  root.querySelectorAll("[data-scope]").forEach(function (radio) {
    radio.addEventListener("change", function () {
      var single = scope() === "single";
      itemSearch.disabled = !single;
      if (!single) { itemSearch.value = ""; itemCode.value = ""; }
    });
  });

  root.querySelector("[data-view]").addEventListener("click", view);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    if (!validRange()) return;
    window.location.href = root.dataset.exportUrl + "?" + query();
  });
  root.querySelector("[data-print]").addEventListener("click", function () { window.print(); });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  root.dataset.dataUrl = root.dataset.dataUrl || root.getAttribute("data-data-url");
  startDate.value = window.DateMask.toDisplay(initial.start_date);
  endDate.value = window.DateMask.toDisplay(initial.end_date);
})();
