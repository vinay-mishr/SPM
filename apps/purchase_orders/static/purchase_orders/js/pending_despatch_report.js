/* Party Wise Pending P.O. Despatch Report — read-only.
 * Old VFP form: PARTY-WISE PENDING P.O. DESPATCH REPORT. */
(function () {
  "use strict";

  var root = document.querySelector("[data-despatch-report]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var runDate = root.querySelector("[data-run-date]");
  var itemCode = root.querySelector("[data-item-code]");
  var itemSearch = root.querySelector("[data-item-search]");
  var toast = document.querySelector("[data-toast]");

  var initial = JSON.parse(document.getElementById("pdr-initial-data").textContent);

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

  function mode() { return root.querySelector('input[name="pdr-mode"]:checked').value; }

  // Old VFP: ALL disables Party Name and clears Name+Code; SINGLE enables Party Name
  // and clears Name+Code (the user picks a fresh party each time the mode changes).
  function applyMode() {
    var single = mode() === "single";
    itemSearch.disabled = !single;
    itemSearch.value = "";
    itemCode.value = "";
  }
  root.querySelectorAll('input[name="pdr-mode"]').forEach(function (r) { r.addEventListener("change", applyMode); });

  if (window.HelpLookup) {
    window.HelpLookup.attach(itemSearch, {
      endpoint: root.dataset.itemsUrl, resultsKey: "parts", valueField: "name",
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
      any = true;
      var heading = document.createElement("tr");
      heading.className = "pdr-party-row";
      var th = document.createElement("td");
      th.colSpan = 7;
      th.textContent = (group.party_name || group.party_code) + ", " + group.city + ", " + group.party_code;
      heading.appendChild(th);
      tbody.appendChild(heading);

      group.lines.forEach(function (line) {
        var tr = document.createElement("tr");
        tr.append(
          cell(line.ord_no),
          cell(dmy(line.ord_date)),
          cell(line.item_code),
          cell(line.item_name),
          cell(line.pending_qty, "num"),
          cell(dmy(line.despatch_date)),
          cell(line.delay_days == null ? "" : line.delay_days, "num")
        );
        tbody.appendChild(tr);
      });
    });
    emptyNote.hidden = any;
  }

  function currentQuery() {
    var params = new URLSearchParams();
    params.set("start_date", window.DateMask.toIso(startDate.value));
    params.set("end_date", window.DateMask.toIso(endDate.value));
    params.set("run_date", window.DateMask.toIso(runDate.value));
    if (mode() === "single" && itemCode.value.trim()) params.set("item_code", itemCode.value.trim());
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

  startDate.value = window.DateMask.toDisplay(initial.start_date);
  endDate.value = window.DateMask.toDisplay(initial.end_date);
  runDate.value = window.DateMask.toDisplay(initial.run_date);
  applyMode();
  render(initial.groups || []);
})();
