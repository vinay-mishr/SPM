/* Sale Order > Item Wise Pending Order: unadjusted order lines per item as on a date. */
(function () {
  "use strict";

  var root = document.querySelector("[data-item-pending]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var grand = root.querySelector("[data-grand]");
  var itemSearch = root.querySelector("[data-item-search]");
  var itemCode = root.querySelector("[data-item-code]");
  var asOn = root.querySelector("[data-as-on]");
  var toast = document.querySelector("[data-toast]");
  var initial = JSON.parse(document.getElementById("ip-initial-data").textContent);

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

  function dmy(iso) {
    if (!iso) return "";
    var p = String(iso).split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : iso;
  }

  function scope() { return root.querySelector("[data-scope]:checked").value; }

  function query() {
    var params = new URLSearchParams();
    params.set("as_on", window.DateMask.toIso(asOn.value));
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
        res.body.groups.forEach(function (g) {
          var head = document.createElement("tr");
          head.className = "pe-part";
          var hc = cell(g.item_name + ", " + g.item_code + "   CUR.STOCK " + g.current);
          hc.colSpan = 6;
          head.appendChild(hc);
          tbody.appendChild(head);
          g.lines.forEach(function (l) {
            var tr = document.createElement("tr");
            tr.append(cell(l.order_no), cell(dmy(l.date)), cell(l.party_name), cell(l.city), cell(l.pending, "num"), cell(""));
            tbody.appendChild(tr);
          });
          var total = document.createElement("tr");
          total.className = "pl-total";
          total.append(cell(""), cell(""), cell(""), cell("TOTAL"), cell(g.total, "num"), cell(""));
          tbody.appendChild(total);
        });
        grand.textContent = res.body.grand_total;
        emptyNote.hidden = res.body.groups.length > 0;
      });
  }

  window.HelpLookup.attach(itemSearch, {
    endpoint: root.dataset.itemsUrl, resultsKey: "parts", valueField: "name",
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

  asOn.value = window.DateMask.toDisplay(initial.as_on);
  root.querySelector("[data-view]").addEventListener("click", view);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    window.location.href = root.dataset.exportUrl + "?" + query();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });
  view();
})();
