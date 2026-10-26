/* Money Receipts > Overdue Payment: pending bills past the party's credit
   period, as on a date -- direct port of the VFP "OVERDUE PAYMENT" report. */
(function () {
  "use strict";

  var root = document.querySelector("[data-overdue-payment]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var partySearch = root.querySelector("[data-party-search]");
  var partyCode = root.querySelector("[data-party-code]");
  var runDate = root.querySelector("[data-run-date]");
  var toast = document.querySelector("[data-toast]");
  var initial = JSON.parse(document.getElementById("ov-initial-data").textContent);

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
    params.set("run_date", window.DateMask.toIso(runDate.value));
    if (scope() === "single") params.set("party_code", partyCode.value);
    return params.toString();
  }

  function view() {
    if (scope() === "single" && !partyCode.value) { showToast("Select a party first.", "error"); return; }
    fetch(root.dataset.dataUrl + "?" + query(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        tbody.textContent = "";
        if (!res.ok) { showToast(res.body.message || "Could not load the report.", "error"); return; }
        var grand = 0;
        res.body.groups.forEach(function (g) {
          var head = document.createElement("tr");
          head.className = "po-party";
          var label = g.party_name + ", " + g.city + ", " + g.party_code;
          var hc = cell(label);
          hc.colSpan = 7;
          head.appendChild(hc);
          tbody.appendChild(head);

          g.rows.forEach(function (l) {
            var tr = document.createElement("tr");
            tr.append(cell(l.div), cell(l.bill_no), cell(dmy(l.bill_date)), cell(l.bill_amount, "num"),
              cell(l.amount_received, "num"), cell(l.balance, "num"), cell(l.delay_days, "num"));
            tbody.appendChild(tr);
          });

          var total = document.createElement("tr");
          total.className = "po-total";
          total.append(cell(""), cell(""), cell(""), cell(""), cell("TOTAL===>"), cell(g.total_balance, "num"), cell(""));
          tbody.appendChild(total);
        });
        emptyNote.hidden = res.body.groups.length > 0;
        root.querySelector("[data-g-total]").value = res.body.grand_total;
      });
  }

  window.HelpLookup.attach(partySearch, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Party",
    onSelect: function (p) { partyCode.value = p.code; partySearch.value = p.name; },
  });

  root.querySelectorAll("[data-scope]").forEach(function (radio) {
    radio.addEventListener("change", function () {
      var single = scope() === "single";
      partySearch.disabled = !single;
      if (!single) { partySearch.value = ""; partyCode.value = ""; }
    });
  });

  runDate.value = window.DateMask.toDisplay(initial.run_date);
  root.querySelector("[data-view]").addEventListener("click", view);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    if (scope() === "single" && !partyCode.value) { showToast("Select a party first.", "error"); return; }
    window.location.href = root.dataset.exportUrl + "?" + query();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });
  view();
})();
