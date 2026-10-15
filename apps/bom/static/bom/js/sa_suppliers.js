/* Bill of Material Master Suppliers (Sub Assembly, no value) — read-only, one PART at a
 * time. Same data source as Value-Wise (conms / Part Master parent like ABM01), but each
 * component row shows Supplier-1..4 (resolved from Part Master's party1..4 codes via the
 * existing Party Master) instead of rates. */
(function () {
  "use strict";

  var root = document.querySelector("[data-sa-suppliers]");
  if (!root) return;

  var partCode = root.querySelector("[data-part-code]");
  var partSearch = root.querySelector("[data-part-search]");
  var partUnit = root.querySelector("[data-part-unit]");
  var excelBtn = root.querySelector("[data-excel]");
  var errorBox = root.querySelector("[data-error]");
  var report = root.querySelector("[data-report]");
  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var placeholder = root.querySelector("[data-placeholder]");
  var toast = document.querySelector("[data-toast]");

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

  function reset() {
    errorBox.hidden = true;
    report.hidden = true;
    emptyNote.hidden = true;
    placeholder.hidden = false;
    excelBtn.disabled = true;
    partUnit.value = "";
  }

  function render(data) {
    placeholder.hidden = true;
    errorBox.hidden = true;
    excelBtn.disabled = false;
    partUnit.value = data.unit || "";
    tbody.textContent = "";
    if (!data.lines.length) {
      report.hidden = true;
      emptyNote.hidden = false;
      return;
    }
    emptyNote.hidden = true;
    report.hidden = false;
    data.lines.forEach(function (line) {
      var tr = document.createElement("tr");
      tr.append(
        cell(line.sno, "num"),
        cell(line.code, "master-table__code"),
        cell(line.item_description),
        cell(line.unit),
        cell(line.quantity, "num"),
        cell(line.material),
        cell(line.supplier_1),
        cell(line.supplier_2),
        cell(line.supplier_3),
        cell(line.supplier_4)
      );
      tbody.appendChild(tr);
    });
  }

  function load() {
    var code = partCode.value.trim();
    if (!code) { reset(); return; }
    fetch(root.dataset.dataUrl + "?part_code=" + encodeURIComponent(code), {
      credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        if (!res.ok) {
          placeholder.hidden = true;
          report.hidden = true;
          emptyNote.hidden = true;
          excelBtn.disabled = true;
          partUnit.value = "";
          errorBox.textContent = res.body.message || "Could not load the report.";
          errorBox.hidden = false;
          return;
        }
        render(res.body.data);
      })
      .catch(function () { showToast("Could not reach the server.", "error"); });
  }

  if (window.HelpLookup) {
    window.HelpLookup.attach(partSearch, {
      endpoint: root.dataset.partsUrl, resultsKey: "parts", valueField: "name",
      displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }], title: "Part",
      onSelect: function (row) { partCode.value = row.code; partSearch.value = row.name; load(); },
    });
  }

  var partsCache = {};
  var searchTimer;
  partSearch.addEventListener("input", function () {
    var q = partSearch.value.trim();
    if (partsCache[q.toUpperCase()]) {
      var hit = partsCache[q.toUpperCase()];
      partCode.value = hit.code;
      partSearch.value = hit.name;
      load();
      return;
    }
    clearTimeout(searchTimer);
    if (!q) { partCode.value = ""; reset(); return; }
    searchTimer = setTimeout(function () {
      fetch(root.dataset.partsUrl + "?q=" + encodeURIComponent(q), { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (body) {
          (body.parts || []).forEach(function (p) { partsCache[p.code] = p; });
          var exact = (body.parts || []).find(function (p) { return p.code === q.toUpperCase() || p.name.toUpperCase() === q.toUpperCase(); });
          if (exact) { partCode.value = exact.code; partSearch.value = exact.name; load(); }
        });
    }, 250);
  });

  excelBtn.addEventListener("click", function () {
    if (!partCode.value.trim()) return;
    window.location.href = root.dataset.exportUrl + "?part_code=" + encodeURIComponent(partCode.value.trim());
  });
  root.querySelector("[data-exit]").addEventListener("click", function () {
    window.location.href = root.dataset.exitUrl;
  });

  reset();
})();
