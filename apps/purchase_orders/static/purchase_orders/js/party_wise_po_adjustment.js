/* Order Adjustment Report — read-only. Old VFP form: "PARTY-WISE PURCHASE ORDER
   ADJUSTMENT" (ALL/SINGLE, Party Name, Run Date, Excel, Exit). */
(function () {
  "use strict";

  var root = document.querySelector("[data-party-wise-po-adjustment]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var runDate = root.querySelector("[data-run-date]");
  var partyCode = root.querySelector("[data-party-code]");
  var partySearch = root.querySelector("[data-party-search]");
  var toast = document.querySelector("[data-toast]");

  var initial = JSON.parse(document.getElementById("pwpoa-initial-data").textContent);

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

  function mode() { return root.querySelector('input[name="pwpoa-mode"]:checked').value; }

  // Old VFP: ALL disables Party Name/Code; SINGLE enables Party Name and focuses it.
  function applyMode() {
    var single = mode() === "single";
    partySearch.disabled = !single;
    partySearch.value = "";
    partyCode.value = "";
    if (single) partySearch.focus();
  }
  root.querySelectorAll('input[name="pwpoa-mode"]').forEach(function (r) { r.addEventListener("change", function () { applyMode(); search(); }); });

  // Clearing Party Name clears Party Code (old VFP: EMPTY(this.value) -> tpcode.value = '').
  partySearch.addEventListener("input", function () {
    if (!partySearch.value.trim()) { partyCode.value = ""; search(); }
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

  function render(groups) {
    tbody.textContent = "";
    var any = false;
    groups.forEach(function (group) {
      any = true;
      var heading = document.createElement("tr");
      heading.className = "pwpoa-party-row";
      var th = document.createElement("td");
      th.colSpan = 5;
      th.textContent = (group.party_name || group.party_code) + (group.city ? ", " + group.city : "") + " (" + group.party_code + ")";
      heading.appendChild(th);
      tbody.appendChild(heading);

      group.lines.forEach(function (line) {
        var tr = document.createElement("tr");
        tr.append(
          cell(line.ord_no, "master-table__code"),
          cell(dmy(line.ord_date)),
          cell(line.item_code),
          cell(line.item_name),
          cell(line.pending_qty, "num")
        );
        tbody.appendChild(tr);
      });
    });
    emptyNote.hidden = any;
  }

  function currentQuery() {
    var params = new URLSearchParams();
    params.set("run_date", window.DateMask.toIso(runDate.value));
    if (mode() === "single" && partyCode.value.trim()) params.set("party_code", partyCode.value.trim());
    return params;
  }

  function search() {
    fetch(root.dataset.dataUrl + "?" + currentQuery().toString(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        if (!res.ok) { showToast(res.body.message || "Could not load the report.", "error"); return; }
        render(res.body.groups || []);
      })
      .catch(function () { showToast("Could not reach the server.", "error"); });
  }

  runDate.addEventListener("change", search);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    if (mode() === "single" && !partyCode.value.trim()) {
      showToast("Select a party first.", "error");
      return;
    }
    window.location.href = root.dataset.exportUrl + "?" + currentQuery().toString();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () {
    window.location.href = root.dataset.exitUrl;
  });

  runDate.value = window.DateMask.toDisplay(initial.run_date);
  applyMode();
  render(initial.groups || []);
})();
