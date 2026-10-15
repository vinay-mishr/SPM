/* MRN > Stock Ledger -- per-part ledger (All / Single), with Excel export. */
(function () {
  "use strict";

  var root = document.querySelector("[data-part-ledger]");
  if (!root) return;

  var partSearch = root.querySelector("[data-part-search]");
  var partCode = root.querySelector("[data-part-code]");
  var itemName = root.querySelector("[data-item-name]");
  var startInput = root.querySelector("[data-start-date]");
  var endInput = root.querySelector("[data-end-date]");
  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var alertBox = root.querySelector("[data-ledger-alert]");
  var toast = document.querySelector("[data-toast]");
  var initial = JSON.parse(document.getElementById("pl-initial-data").textContent);

  function mode() { return root.querySelector('input[name="pl-mode"]:checked').value; }

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
    if (mode() === "single") params.set("part_code", partCode.value.trim());
    return params.toString();
  }

  function validate() {
    if (mode() === "single" && !partCode.value.trim()) { alertBox.textContent = "Select a part first."; alertBox.hidden = false; return false; }
    if (!window.DateMask.toIso(startInput.value) || !window.DateMask.toIso(endInput.value)) { alertBox.textContent = "Enter valid dates."; alertBox.hidden = false; return false; }
    alertBox.hidden = true;
    return true;
  }

  function view() {
    if (!validate()) return;
    fetch(root.dataset.dataUrl + "?" + query(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        if (!res.ok) { alertBox.textContent = res.body.message || "Could not load the ledger."; alertBox.hidden = false; return; }
        tbody.textContent = "";
        res.body.parts.forEach(function (p) {
          var head = document.createElement("tr");
          head.className = "pl-part";
          var hc = cell(p.code + "  " + p.name);
          hc.colSpan = 7;
          head.appendChild(hc);
          tbody.appendChild(head);
          var open = document.createElement("tr");
          open.append(cell(""), cell(""), cell("OPENING"), cell(""), cell(""), cell(""), cell(p.opening, "num"));
          tbody.appendChild(open);
          p.rows.forEach(function (r) {
            var tr = document.createElement("tr");
            tr.append(cell(dmy(r.date)), cell(r.ref_no), cell(r.party), cell(r.rate, "num"), cell(r.rec, "num"), cell(r.iss, "num"), cell(r.bal, "num"));
            tbody.appendChild(tr);
          });
          var total = document.createElement("tr");
          total.className = "pl-total";
          total.append(cell(""), cell(""), cell("TOTAL"), cell(""), cell(p.rec_total, "num"), cell(p.iss_total, "num"), cell(p.closing, "num"));
          tbody.appendChild(total);
        });
        emptyNote.hidden = res.body.parts.length > 0;
      });
  }

  function exportExcel() {
    if (!validate()) return;
    window.location.href = root.dataset.exportUrl + "?" + query();
  }

  function applyMode() {
    var single = mode() === "single";
    partSearch.disabled = !single;
    if (!single) { partSearch.value = ""; partCode.value = ""; itemName.value = ""; }
    if (single) partSearch.focus();
  }
  root.querySelectorAll('input[name="pl-mode"]').forEach(function (r) { r.addEventListener("change", applyMode); });

  window.HelpLookup.attach(partSearch, {
    endpoint: root.dataset.partsUrl, resultsKey: "parts", valueField: "code",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "unit", label: "Unit" }],
    title: "Part",
    onSelect: function (row) { partCode.value = row.code; partSearch.value = row.code; itemName.value = row.name; },
  });

  startInput.value = window.DateMask.toDisplay(initial.start_date);
  endInput.value = window.DateMask.toDisplay(initial.end_date);
  root.querySelector("[data-view]").addEventListener("click", view);
  root.querySelector("[data-excel]").addEventListener("click", exportExcel);
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });
  applyMode();
})();
