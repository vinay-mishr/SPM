/* Money Receipts > Party Outstanding: aging-bucketed pending bills per party
   as on a date -- direct port of the VFP "posparty" report. */
(function () {
  "use strict";

  var root = document.querySelector("[data-party-outstanding]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var partySearch = root.querySelector("[data-party-search]");
  var partyCode = root.querySelector("[data-party-code]");
  var runDate = root.querySelector("[data-run-date]");
  var toast = document.querySelector("[data-toast]");
  var initial = JSON.parse(document.getElementById("po-initial-data").textContent);

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

  function bucketValue(row, key) { return row.bucket === key ? row.balance : ""; }

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
        res.body.groups.forEach(function (g) {
          var head = document.createElement("tr");
          head.className = "po-party";
          var label = g.party_name + ", " + g.city + ", " + g.party_code + (g.phone ? ", PH:" + g.phone : "");
          var hc = cell(label);
          hc.colSpan = 11;
          head.appendChild(hc);
          tbody.appendChild(head);

          if (Number(g.advance) > 0) {
            var adv = document.createElement("tr");
            adv.className = "po-advance";
            var ac = cell("ADVANCE  " + g.advance);
            ac.colSpan = 11;
            adv.appendChild(ac);
            tbody.appendChild(adv);
          }

          g.rows.forEach(function (l) {
            var tr = document.createElement("tr");
            tr.append(cell(l.bill_no), cell(dmy(l.bill_date)), cell(l.bill_amount, "num"),
              cell(l.amount_received, "num"), cell(l.dr_note, "num"), cell(l.cr_note, "num"),
              cell(l.balance, "num"),
              cell(bucketValue(l, "below_30"), "num"), cell(bucketValue(l, "between_31_60"), "num"),
              cell(bucketValue(l, "between_61_90"), "num"), cell(bucketValue(l, "above_90"), "num"));
            tbody.appendChild(tr);
          });

          var total = document.createElement("tr");
          total.className = "po-total";
          total.append(cell(""), cell(""), cell(""), cell(""), cell(""), cell("TOTAL===>"),
            cell(g.total_balance, "num"), cell(g.below_30, "num"), cell(g.between_31_60, "num"),
            cell(g.between_61_90, "num"), cell(g.above_90, "num"));
          tbody.appendChild(total);

          if (g.ledger_mismatch) {
            var warn = document.createElement("tr");
            warn.className = "po-warn";
            var wc = cell("LEDGER BAL " + g.ledger_balance + " (differs from the figure above)");
            wc.colSpan = 11;
            warn.appendChild(wc);
            tbody.appendChild(warn);
          }
        });
        emptyNote.hidden = res.body.groups.length > 0;

        root.querySelector("[data-g-below-30]").value = res.body.below_30;
        root.querySelector("[data-g-31-60]").value = res.body.between_31_60;
        root.querySelector("[data-g-61-90]").value = res.body.between_61_90;
        root.querySelector("[data-g-above-90]").value = res.body.above_90;
        root.querySelector("[data-g-total]").value = res.body.total_balance;
        root.querySelector("[data-g-advance]").value = res.body.advance;
        root.querySelector("[data-g-net]").value = res.body.net_outstanding;
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
