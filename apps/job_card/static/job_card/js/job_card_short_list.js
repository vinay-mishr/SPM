/* Short List -- item lookup for the Show form. */
(function () {
  "use strict";

  var root = document.querySelector("[data-short-list]");
  if (!root) return;

  var search = root.querySelector("[data-item-search]");
  var code = root.querySelector("[data-item-code]");

  window.HelpLookup.attach(search, {
    endpoint: root.dataset.itemsUrl, resultsKey: "items", valueField: "code",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "unit", label: "Unit" }],
    title: "Item",
    onSelect: function (row) { code.value = row.code; search.value = row.code; },
  });
})();
