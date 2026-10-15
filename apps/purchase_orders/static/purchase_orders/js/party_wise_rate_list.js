/* Party-Wise Rate List report — read-only. Old VFP form: PARTY-WISE RATE LIST. */
(function () {
  "use strict";

  var root = document.querySelector("[data-party-wise-rate-list]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var dateError = root.querySelector("[data-date-error]");
  var partyCode = root.querySelector("[data-party-code]");
  var partySearch = root.querySelector("[data-party-search]");
  var toast = document.querySelector("[data-toast]");

  var initial = JSON.parse(document.getElementById("pwr-initial-data").textContent);

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

  function mode() { return root.querySelector('input[name="pwr-mode"]:checked').value; }

  // Old VFP: ALL disables Party Name/Code; SINGLE enables Party Name and focuses it.
  function applyMode() {
    var single = mode() === "single";
    partySearch.disabled = !single;
    partySearch.value = "";
    partyCode.value = "";
    if (single) partySearch.focus();
  }
  root.querySelectorAll('input[name="pwr-mode"]').forEach(function (r) { r.addEventListener("change", applyMode); });

  // Clearing Party Name clears Party Code (old VFP: EMPTY(this.value) -> tpcode.value = '').
  partySearch.addEventListener("input", function () {
    if (!partySearch.value.trim()) partyCode.value = "";
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
      heading.className = "pwr-party-row";
      var th = document.createElement("td");
      th.colSpan = 7;
      var label = (group.party_name || group.party_code) + (group.city ? ", " + group.city : "") + " (" + group.party_code + ")";
      if (group.grade) label += "  Grade: " + group.grade;
      th.textContent = label;
      heading.appendChild(th);
      tbody.appendChild(heading);

      group.lines.forEach(function (line) {
        var tr = document.createElement("tr");
        tr.append(
          cell(line.item_code, "master-table__code"),
          cell(line.item_name),
          cell(line.bill_no),
          cell(dmy(line.bill_date)),
          cell(line.qty, "num"),
          cell(line.po_qty, "num"),
          cell(line.rate, "num")
        );
        tbody.appendChild(tr);
      });
    });
    emptyNote.hidden = any;
  }

  function validRange() {
    var s = window.DateMask.toIso(startDate.value);
    var e = window.DateMask.toIso(endDate.value);
    if (s && e && s > e) {
      dateError.textContent = "Start Date cannot be later than End Date.";
      dateError.hidden = false;
      return false;
    }
    dateError.hidden = true;
    return true;
  }

  function currentQuery() {
    var params = new URLSearchParams();
    params.set("start_date", window.DateMask.toIso(startDate.value));
    params.set("end_date", window.DateMask.toIso(endDate.value));
    if (mode() === "single" && partyCode.value.trim()) params.set("party_code", partyCode.value.trim());
    return params;
  }

  function search() {
    if (!validRange()) { render([]); return; }
    fetch(root.dataset.dataUrl + "?" + currentQuery().toString(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        if (!res.ok) { showToast(res.body.message || "Could not load the report.", "error"); return; }
        render(res.body.groups || []);
      })
      .catch(function () { showToast("Could not reach the server.", "error"); });
  }

  startDate.addEventListener("change", search);
  endDate.addEventListener("change", search);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    if (!validRange()) return;
    window.location.href = root.dataset.exportUrl + "?" + currentQuery().toString();
  });
  root.querySelector("[data-print]").addEventListener("click", function () {
    if (!validRange()) return;
    window.open(root.dataset.printUrl + "?" + currentQuery().toString(), "_blank");
  });
  root.querySelector("[data-exit]").addEventListener("click", function () {
    window.location.href = root.dataset.exitUrl;
  });

  startDate.value = window.DateMask.toDisplay(initial.start_date);
  endDate.value = window.DateMask.toDisplay(initial.end_date);
  applyMode();
  render(initial.groups || []);
})();
