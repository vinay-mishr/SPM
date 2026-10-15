/* Party Wise Pending Purchase Order report — read-only. Old VFP form: PARTY-WISE PENDING P.O. */
(function () {
  "use strict";

  var root = document.querySelector("[data-pending-report]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var asOn = root.querySelector("[data-as-on]");
  var quickSearch = root.querySelector("[data-quick-search]");
  var toast = document.querySelector("[data-toast]");

  var loadedGroups = []; // last data fetched from the server, before the quick-search filter

  var initial = JSON.parse(document.getElementById("por-initial-data").textContent);

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

  function money(v) { return Number(v || 0).toFixed(2); }

  function cell(text, className) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (className) td.className = className;
    return td;
  }

  /* Filters the already-loaded rows by party name/code, city, item code/name or
     order number -- client-side, so it reacts as you type instead of needing
     another round trip to the server for every keystroke. */
  function matchesQuery(group, line, query) {
    if (!query) return true;
    return [group.party_name, group.party_code, group.city, line.item_code, line.item_name, line.ord_no]
      .join(" ").toLowerCase().indexOf(query) > -1;
  }

  function render(groups) {
    loadedGroups = groups;
    renderFiltered();
  }

  function renderFiltered() {
    var query = quickSearch.value.trim().toLowerCase();
    tbody.textContent = "";
    var any = false;
    loadedGroups.forEach(function (group) {
      var shownPartyRow = false; // Party Name/City/Code print once per party, not on every one of its lines
      group.lines.forEach(function (line) {
        if (!matchesQuery(group, line, query)) return;
        any = true;
        var isFirst = !shownPartyRow;
        shownPartyRow = true;
        var tr = document.createElement("tr");
        tr.append(
          cell(isFirst ? (group.party_name || group.party_code) : ""),
          cell(isFirst ? group.city : ""),
          cell(isFirst ? group.party_code : "", "master-table__code"),
          cell(group.grade),
          cell(line.ord_no),
          cell(dmy(line.ord_date)),
          cell(line.item_code),
          cell(line.item_name),
          cell(line.pending_qty, "num"),
          cell(money(line.rate), "num"),
          cell(money(line.value), "num"),
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
    params.set("as_on", window.DateMask.toIso(asOn.value));
    return params;
  }

  function search() {
    var params = currentQuery();
    fetch(root.dataset.dataUrl + "?" + params.toString(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json(); })
      .then(function (body) { render(body.groups || []); })
      .catch(function () { showToast("Could not reach the server.", "error"); });
  }

  quickSearch.addEventListener("input", renderFiltered);
  root.querySelector("[data-search]").addEventListener("click", search);
  root.querySelector("[data-refresh]").addEventListener("click", function () {
    asOn.value = window.DateMask.toDisplay(initial.as_on);
    quickSearch.value = "";
    search();
  });
  root.querySelector("[data-excel]").addEventListener("click", function () {
    var params = currentQuery();
    var q = quickSearch.value.trim();
    if (q) params.set("q", q); // export only what the quick search is currently showing
    window.location.href = root.dataset.exportUrl + "?" + params.toString();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () {
    window.location.href = root.dataset.exitUrl;
  });

  asOn.value = window.DateMask.toDisplay(initial.as_on);
  render(initial.groups || []);
})();
