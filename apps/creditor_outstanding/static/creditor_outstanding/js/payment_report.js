/* Creditor Outstanding > Payment Report: payments in a date range, all vendors or one vendor, with Excel. */
(function () {
  "use strict";

  var root = document.querySelector("[data-pr]");
  if (!root) return;

  var modeRadios = root.querySelectorAll('input[name="pr-mode"]');
  var partySearch = root.querySelector("[data-party-search]");
  var partyCode = root.querySelector("[data-party-code]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var rows = root.querySelector("[data-rows]");
  var totalCell = root.querySelector("[data-total]");
  var alertBox = root.querySelector("[data-alert]");
  var alertTimer = null;

  function single() {
    return Array.prototype.find.call(modeRadios, function (r) { return r.checked; }).value === "S";
  }

  function show(msg) {
    alertBox.textContent = msg || "";
    alertBox.hidden = !msg;
    clearTimeout(alertTimer);
    if (msg) alertTimer = setTimeout(function () { alertBox.hidden = true; }, 5000);
  }

  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (cls) td.className = cls;
    return td;
  }

  function dmy(iso) {
    var p = String(iso || "").split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : "";
  }

  function query() {
    var params = new URLSearchParams();
    params.set("start_date", window.DateMask.toIso(startDate.value));
    params.set("end_date", window.DateMask.toIso(endDate.value));
    if (single()) params.set("party_code", partyCode.value);
    return params.toString();
  }

  function valid() {
    if (!window.DateMask.toIso(startDate.value) || !window.DateMask.toIso(endDate.value)) { show("Enter valid dates."); return false; }
    if (single() && !partyCode.value) { show("Select a party first."); return false; }
    show("");
    return true;
  }

  function show_() {
    if (!valid()) return;
    fetch(root.dataset.dataUrl + "?" + query(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        if (!res.ok) { show(res.body.message || "Could not load the report."); return; }
        rows.textContent = "";
        res.body.rows.forEach(function (r) {
          var tr = document.createElement("tr");
          tr.append(cell(dmy(r.date)), cell(r.party_code), cell(r.party_name), cell(r.chq_no), cell(r.bills, "num"),
            cell(r.c_dis, "num"), cell(r.interest, "num"), cell(r.amount, "num"));
          rows.appendChild(tr);
        });
        if (!res.body.rows.length) {
          var empty = document.createElement("tr");
          empty.className = "empty";
          var td = document.createElement("td");
          td.colSpan = 8;
          td.textContent = "No payments in this range.";
          empty.appendChild(td);
          rows.appendChild(empty);
        }
        totalCell.textContent = res.body.total;
      });
  }

  function applyMode() {
    partySearch.disabled = !single();
    if (!single()) { partySearch.value = ""; partyCode.value = ""; }
  }
  modeRadios.forEach(function (r) { r.addEventListener("change", applyMode); });

  window.HelpLookup.attach(partySearch, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Party",
    onSelect: function (row) { partyCode.value = row.code; partySearch.value = row.name; },
  });

  root.querySelector("[data-show]").addEventListener("click", show_);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    if (valid()) window.location.href = root.dataset.exportUrl + "?" + query();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  var today = new Date().toISOString().slice(0, 10);
  startDate.value = window.DateMask.toDisplay(today.slice(0, 8) + "01");
  endDate.value = window.DateMask.toDisplay(today);
  applyMode();
  show_();
})();
