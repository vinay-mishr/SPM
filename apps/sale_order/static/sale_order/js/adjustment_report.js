/* Sale Order > Order Adjustment Report: unadjusted order lines per party as on a date. */
(function () {
  "use strict";

  var root = document.querySelector("[data-adjustment-report]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var grand = root.querySelector("[data-grand]");
  var partySearch = root.querySelector("[data-party-search]");
  var partyCode = root.querySelector("[data-party-code]");
  var asOn = root.querySelector("[data-as-on]");
  var toast = document.querySelector("[data-toast]");
  var initial = JSON.parse(document.getElementById("ar-initial-data").textContent);

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
    params.set("as_on", window.DateMask.toIso(asOn.value));
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
          head.className = "pe-part";
          var hc = cell(g.party_name + ", " + g.city + ", " + g.party_code);
          hc.colSpan = 6;
          head.appendChild(hc);
          tbody.appendChild(head);
          g.lines.forEach(function (l) {
            var tr = document.createElement("tr");
            tr.append(cell(l.order_no), cell(dmy(l.date)), cell(l.item_code, "master-table__code"), cell(l.item_name),
              cell(l.pending, "num"), cell(l.value, "num"));
            tbody.appendChild(tr);
          });
          var total = document.createElement("tr");
          total.className = "pl-total";
          total.append(cell(""), cell(""), cell(""), cell("TOTAL"), cell(""), cell(g.total, "num"));
          tbody.appendChild(total);
        });
        grand.textContent = res.body.grand_total;
        emptyNote.hidden = res.body.groups.length > 0;
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

  asOn.value = window.DateMask.toDisplay(initial.as_on);
  root.querySelector("[data-view]").addEventListener("click", view);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    if (scope() === "single" && !partyCode.value) { showToast("Select a party first.", "error"); return; }
    window.location.href = root.dataset.exportUrl + "?" + query();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });
  view();
})();
