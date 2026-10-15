/* Party Wise Item List report — read-only. Old VFP form: PARTY WISE ITEM LIST (pwil.PRN).
 * For one selected party, lists every part whose supplier1..4 slot matches that party,
 * using that slot's own rate1..4. */
(function () {
  "use strict";

  var root = document.querySelector("[data-party-wise-item-list]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var partyCode = root.querySelector("[data-party-code]");
  var partyGrade = root.querySelector("[data-party-grade]");
  var partySearch = root.querySelector("[data-party-search]");
  var excelBtn = root.querySelector("[data-excel]");
  var toast = document.querySelector("[data-toast]");

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  // Old VFP: EMPTY(this.value) -> clear Party Code / list.
  partySearch.addEventListener("input", function () {
    if (!partySearch.value.trim()) { partyCode.value = ""; partyGrade.value = ""; render([]); }
  });

  if (window.HelpLookup) {
    window.HelpLookup.attach(partySearch, {
      endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
      displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }], title: "Party",
      onSelect: function (row) { partyCode.value = row.code; search(); },
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
      tr.append(cell(row.code, "master-table__code"), cell(row.name), cell(row.rate, "num"));
      tbody.appendChild(tr);
    });
    emptyNote.hidden = rows.length > 0;
    emptyNote.textContent = partyCode.value.trim()
      ? "No items found for this party."
      : "Select a party to see its items.";
    excelBtn.disabled = rows.length === 0;
  }

  function currentQuery() {
    var params = new URLSearchParams();
    params.set("party_code", partyCode.value.trim());
    return params;
  }

  function search() {
    if (!partyCode.value.trim()) { render([]); return; }
    fetch(root.dataset.dataUrl + "?" + currentQuery().toString(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        if (!res.ok) { showToast(res.body.message || "Could not load the report.", "error"); return; }
        partyGrade.value = (res.body.party && res.body.party.grade) || "";
        render(res.body.rows || []);
      })
      .catch(function () { showToast("Could not reach the server.", "error"); });
  }

  root.querySelector("[data-excel]").addEventListener("click", function () {
    if (!partyCode.value.trim()) { showToast("Select a party first.", "error"); return; }
    window.location.href = root.dataset.exportUrl + "?" + currentQuery().toString();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () {
    window.location.href = root.dataset.exitUrl;
  });

  render([]);
  partySearch.focus();
})();
