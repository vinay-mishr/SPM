/* Spare Sale Order > Itemwise Spare Part Pending Order: pending spare quantity per part. */
(function () {
  "use strict";

  var root = document.querySelector("[data-spare-item-pending]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var grand = root.querySelector("[data-grand]");
  var itemSearch = root.querySelector("[data-item-search]");
  var itemCode = root.querySelector("[data-item-code]");
  var toast = document.querySelector("[data-toast]");

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (cls) td.className = cls;
    return td;
  }

  function scope() { return root.querySelector("[data-scope]:checked").value; }

  function query() {
    var params = new URLSearchParams();
    if (scope() === "single" && itemCode.value) params.set("item_code", itemCode.value);
    return params.toString();
  }

  function view() {
    if (scope() === "single" && !itemCode.value) { showToast("Select an item first.", "error"); return; }
    fetch(root.dataset.dataUrl + "?" + query(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        tbody.textContent = "";
        if (!res.ok) { showToast(res.body.message || "Could not load the report.", "error"); return; }
        res.body.rows.forEach(function (r) {
          var tr = document.createElement("tr");
          tr.append(cell(r.item_code, "master-table__code"), cell(r.item_name), cell(r.pending, "num"));
          tbody.appendChild(tr);
        });
        grand.textContent = res.body.grand_total;
        emptyNote.hidden = res.body.rows.length > 0;
      });
  }

  window.HelpLookup.attach(itemSearch, {
    endpoint: root.dataset.itemsUrl, resultsKey: "parts", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }],
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
    if (scope() === "single" && !itemCode.value) { showToast("Select an item first.", "error"); return; }
    window.location.href = root.dataset.exportUrl + "?" + query();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });
  view();
})();
