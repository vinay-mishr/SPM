/* Itemwise Party List report — read-only. Old VFP form: ITEMWISE PARTY LIST.
 * For one selected item (Part Master), lists each of its 4 supplier/rate slots. */
(function () {
  "use strict";

  var root = document.querySelector("[data-itemwise-party-list]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var itemCode = root.querySelector("[data-item-code]");
  var itemSearch = root.querySelector("[data-item-search]");
  var toast = document.querySelector("[data-toast]");

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  // Old VFP: EMPTY(this.value) -> clear Item Code.
  itemSearch.addEventListener("input", function () {
    if (!itemSearch.value.trim()) { itemCode.value = ""; render([]); }
  });

  if (window.HelpLookup) {
    window.HelpLookup.attach(itemSearch, {
      endpoint: root.dataset.partsUrl, resultsKey: "parts", valueField: "name",
      displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }], title: "Item",
      onSelect: function (row) { itemCode.value = row.code; search(); },
    });
  }

  function cell(text, className) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (className) td.className = className;
    return td;
  }

  function render(rows) {
    tbody.textContent = "";
    rows.forEach(function (row) {
      var tr = document.createElement("tr");
      tr.append(
        cell(row.party_code, "master-table__code"),
        cell(row.party_name),
        cell(row.city),
        cell(row.grade),
        cell(row.rate, "num")
      );
      tbody.appendChild(tr);
    });
    emptyNote.hidden = rows.length > 0;
    emptyNote.textContent = itemCode.value.trim()
      ? "No parties found for this item."
      : "Select an item to see its parties.";
  }

  function currentQuery() {
    var params = new URLSearchParams();
    params.set("part_code", itemCode.value.trim());
    return params;
  }

  function search() {
    if (!itemCode.value.trim()) { render([]); return; }
    fetch(root.dataset.dataUrl + "?" + currentQuery().toString(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        if (!res.ok) { showToast(res.body.message || "Could not load the report.", "error"); return; }
        render(res.body.rows || []);
      })
      .catch(function () { showToast("Could not reach the server.", "error"); });
  }

  root.querySelector("[data-excel]").addEventListener("click", function () {
    if (!itemCode.value.trim()) { showToast("Select an item first.", "error"); return; }
    window.location.href = root.dataset.exportUrl + "?" + currentQuery().toString();
  });
  root.querySelector("[data-print]").addEventListener("click", function () {
    if (!itemCode.value.trim()) { showToast("Select an item first.", "error"); return; }
    window.open(root.dataset.printUrl + "?" + currentQuery().toString(), "_blank");
  });
  root.querySelector("[data-exit]").addEventListener("click", function () {
    window.location.href = root.dataset.exitUrl;
  });

  render([]);
  itemSearch.focus();
})();
