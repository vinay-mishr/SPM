/* Creditor Outstanding > Outstanding Report: All / Single vendor, run date, Show and Excel. */
(function () {
  "use strict";

  var root = document.querySelector("[data-os]");
  if (!root) return;

  var modeRadios = root.querySelectorAll('input[name="os-mode"]');
  var mode = { get value() { return Array.prototype.find.call(modeRadios, function (r) { return r.checked; }).value; } };
  var partySearch = root.querySelector("[data-party-search]");
  var partyCode = root.querySelector("[data-party-code]");
  var runDate = root.querySelector("[data-run-date]");
  var tbody = root.querySelector("[data-rows]");

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
    params.set("run_date", window.DateMask.toIso(runDate.value));
    if (mode.value === "S") params.set("party_code", partyCode.value);
    return params.toString();
  }

  function show() {
    if (mode.value === "S" && !partyCode.value) { window.alert("Select a party first."); return; }
    fetch(root.dataset.dataUrl + "?" + query(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        tbody.textContent = "";
        if (!res.groups.length) {
          var tr = document.createElement("tr");
          tr.className = "empty";
          var td = document.createElement("td");
          td.colSpan = 10;
          td.textContent = "No outstanding bills for this run date.";
          tr.appendChild(td);
          tbody.appendChild(tr);
          return;
        }
        res.groups.forEach(function (g) {
          var head = document.createElement("tr");
          head.className = "pe-part";
          var hc = cell(g.party_name + ", " + g.city + ", " + g.party_code);
          hc.colSpan = 10;
          head.appendChild(hc);
          tbody.appendChild(head);
          g.lines.forEach(function (l) {
            var tr = document.createElement("tr");
            tr.append(cell(l.mrn_no), cell(l.bill_no), cell(dmy(l.bill_date)), cell(l.bill_amount, "num"),
              cell(l.tds, "num"), cell(l.paid, "num"), cell(l.dr_note, "num"), cell(l.c_dis, "num"), cell(l.balance, "num"), cell(l.due_days, "num"));
            tbody.appendChild(tr);
          });
          var total = document.createElement("tr");
          total.className = "pl-total";
          total.append(cell(""), cell(""), cell("TOTAL"), cell(""), cell(""), cell(""), cell(""), cell(""), cell(g.total, "num"), cell(""));
          tbody.appendChild(total);
        });
      });
  }

  function applyMode() {
    var single = mode.value === "S";
    partySearch.disabled = !single;
    if (!single) { partySearch.value = ""; partyCode.value = ""; }
  }
  modeRadios.forEach(function (r) { r.addEventListener("change", applyMode); });

  window.HelpLookup.attach(partySearch, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Party",
    onSelect: function (row) { partyCode.value = row.code; partySearch.value = row.name; },
  });

  root.querySelector("[data-show]").addEventListener("click", show);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    if (mode.value === "S" && !partyCode.value) { window.alert("Select a party first."); return; }
    window.location.href = root.dataset.exportUrl + "?" + query();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  runDate.value = window.DateMask.toDisplay(new Date().toISOString().slice(0, 10));
  applyMode();
  show();
})();
