/* Consumption Master report — read-only, one item at a time. Old VFP form built this from
 * con-mst (order "itempart") joined to part-mst, printed to ITEMLIST.PRN or exported via
 * Excel automation. Item = item master (parent), components = part master rows. */
(function () {
  "use strict";

  var root = document.querySelector("[data-consumption-master]");
  if (!root) return;

  var itemCode = root.querySelector("[data-item-code]");
  var itemSearch = root.querySelector("[data-item-search]");
  var excelBtn = root.querySelector("[data-excel]");
  var errorBox = root.querySelector("[data-error]");
  var report = root.querySelector("[data-report]");
  var reportTotal = root.querySelector("[data-report-total]");
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
  }

  function render(data) {
    placeholder.hidden = true;
    errorBox.hidden = true;
    excelBtn.disabled = false;
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
        cell(line.weight_by_100, "num"),
        cell(line.gauge),
        cell(line.drawing_no),
        cell(line.value, "num")
      );
      tbody.appendChild(tr);
    });
    reportTotal.textContent = data.total;
  }

  function load() {
    var code = itemCode.value.trim();
    if (!code) { reset(); return; }
    fetch(root.dataset.dataUrl + "?item_code=" + encodeURIComponent(code), {
      credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        if (!res.ok) {
          placeholder.hidden = true;
          report.hidden = true;
          emptyNote.hidden = true;
          excelBtn.disabled = true;
          errorBox.textContent = res.body.message || "Could not load the report.";
          errorBox.hidden = false;
          return;
        }
        render(res.body.data);
      })
      .catch(function () { showToast("Could not reach the server.", "error"); });
  }

  if (window.HelpLookup) {
    window.HelpLookup.attach(itemSearch, {
      endpoint: root.dataset.itemsUrl, resultsKey: "items", valueField: "name",
      displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }], title: "Item",
      onSelect: function (row) { itemCode.value = row.code; itemSearch.value = row.name; load(); },
    });
  }

  var itemsCache = {};
  var searchTimer;
  itemSearch.addEventListener("input", function () {
    var q = itemSearch.value.trim();
    if (itemsCache[q.toUpperCase()]) {
      var hit = itemsCache[q.toUpperCase()];
      itemCode.value = hit.code;
      itemSearch.value = hit.name;
      load();
      return;
    }
    clearTimeout(searchTimer);
    if (!q) { itemCode.value = ""; reset(); return; }
    searchTimer = setTimeout(function () {
      fetch(root.dataset.itemsUrl + "?q=" + encodeURIComponent(q), { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (body) {
          (body.items || []).forEach(function (i) { itemsCache[i.code] = i; });
          var exact = (body.items || []).find(function (i) { return i.code === q.toUpperCase() || i.name.toUpperCase() === q.toUpperCase(); });
          if (exact) { itemCode.value = exact.code; itemSearch.value = exact.name; load(); }
        });
    }, 250);
  });

  excelBtn.addEventListener("click", function () {
    if (!itemCode.value.trim()) return;
    window.location.href = root.dataset.exportUrl + "?item_code=" + encodeURIComponent(itemCode.value.trim());
  });
  root.querySelector("[data-exit]").addEventListener("click", function () {
    window.location.href = root.dataset.exitUrl;
  });

  reset();
})();
