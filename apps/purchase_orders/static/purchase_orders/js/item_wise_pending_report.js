/* Item-Wise Pending P.O. report — read-only. Old VFP form: ITEM-WISE PENDING P.O.
 * "Item" here is Part Master (part-mst), matching the rest of the Purchase Order module. */
(function () {
  "use strict";

  var root = document.querySelector("[data-item-wise-report]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var runDate = root.querySelector("[data-run-date]");
  var itemCode = root.querySelector("[data-item-code]");
  var itemSearch = root.querySelector("[data-item-search]");
  var toast = document.querySelector("[data-toast]");

  var initial = JSON.parse(document.getElementById("iwp-initial-data").textContent);

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

  function mode() { return root.querySelector('input[name="iwp-mode"]:checked').value; }

  // Old VFP: ALL disables Item Name and clears Name+Code; SINGLE enables Item Name
  // and clears Name+Code (a fresh item is picked each time the mode changes).
  function applyMode() {
    var single = mode() === "single";
    itemSearch.disabled = !single;
    itemSearch.value = "";
    itemCode.value = "";
  }
  root.querySelectorAll('input[name="iwp-mode"]').forEach(function (r) { r.addEventListener("change", applyMode); });

  if (window.HelpLookup) {
    window.HelpLookup.attach(itemSearch, {
      endpoint: root.dataset.partsUrl, resultsKey: "parts", valueField: "name",
      displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }], title: "Item",
      onSelect: function (row) { itemCode.value = row.code; },
    });
  }

  function cell(text, className) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (className) td.className = className;
    return td;
  }

  function render(groups) {
    tbody.textContent = "";
    var any = false;
    groups.forEach(function (group) {
      var shownItemRow = false; // Item Name prints once per item, not on every one of its lines
      group.lines.forEach(function (line) {
        any = true;
        var isFirst = !shownItemRow;
        shownItemRow = true;
        var tr = document.createElement("tr");
        tr.append(
          cell(isFirst ? (group.part_name || group.part_code) : ""),
          cell(line.ord_no),
          cell(dmy(line.ord_date)),
          cell(line.party_name || line.party_code),
          cell(line.city),
          cell(line.ord_qty, "num"),
          cell(line.rec_qty, "num"),
          cell(line.bal_qty, "num"),
          cell(dmy(line.despatch_date))
        );
        tbody.appendChild(tr);
      });
    });
    emptyNote.hidden = any;
  }

  function currentQuery() {
    var params = new URLSearchParams();
    params.set("run_date", window.DateMask.toIso(runDate.value));
    if (mode() === "single" && itemCode.value.trim()) params.set("part_code", itemCode.value.trim());
    return params;
  }

  function search() {
    var params = currentQuery();
    fetch(root.dataset.dataUrl + "?" + params.toString(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json(); })
      .then(function (body) { render(body.groups || []); })
      .catch(function () { showToast("Could not reach the server.", "error"); });
  }

  root.querySelector("[data-search]").addEventListener("click", search);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    window.location.href = root.dataset.exportUrl + "?" + currentQuery().toString();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () {
    window.location.href = root.dataset.exitUrl;
  });

  runDate.value = window.DateMask.toDisplay(initial.run_date);
  applyMode();
  render(initial.groups || []);
})();
