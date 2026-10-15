/* Sale Order > Area Wise Pending Order: pending lines grouped by area, then by party. */
(function () {
  "use strict";

  var root = document.querySelector("[data-area-pending]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var grand = root.querySelector("[data-grand]");
  var areaSearch = root.querySelector("[data-area-search]");
  var areaCode = root.querySelector("[data-area-code]");
  var asOn = root.querySelector("[data-as-on]");
  var toast = document.querySelector("[data-toast]");
  var initial = JSON.parse(document.getElementById("ap-initial-data").textContent);

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
    if (scope() === "single" && areaCode.value) params.set("area_code", areaCode.value);
    return params.toString();
  }

  function view() {
    if (scope() === "single" && !areaCode.value) { showToast("Select an area first.", "error"); return; }
    fetch(root.dataset.dataUrl + "?" + query(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        tbody.textContent = "";
        if (!res.ok) { showToast(res.body.message || "Could not load the report.", "error"); return; }
        res.body.groups.forEach(function (g) {
          var head = document.createElement("tr");
          head.className = "pe-part";
          var hc = cell("AREA " + g.area_code + "  " + g.area_name);
          hc.colSpan = 5;
          head.appendChild(hc);
          tbody.appendChild(head);
          g.parties.forEach(function (p) {
            var ph = document.createElement("tr");
            var pc = cell(p.party_name + ", " + p.city + ", " + p.party_code);
            pc.colSpan = 5;
            pc.style.fontWeight = "700";
            ph.appendChild(pc);
            tbody.appendChild(ph);
            p.lines.forEach(function (l) {
              var tr = document.createElement("tr");
              tr.append(cell(l.order_no), cell(dmy(l.date)), cell(l.item_code, "master-table__code"), cell(l.item_name), cell(l.pending, "num"));
              tbody.appendChild(tr);
            });
          });
          var total = document.createElement("tr");
          total.className = "pl-total";
          total.append(cell(""), cell(""), cell(""), cell("AREA TOTAL"), cell(g.total, "num"));
          tbody.appendChild(total);
        });
        grand.textContent = res.body.grand_total;
        emptyNote.hidden = res.body.groups.length > 0;
      });
  }

  window.HelpLookup.attach(areaSearch, {
    endpoint: root.dataset.areasUrl, resultsKey: "areas", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Area" }],
    title: "Area",
    onSelect: function (row) { areaCode.value = row.code; areaSearch.value = row.name; },
  });

  root.querySelectorAll("[data-scope]").forEach(function (radio) {
    radio.addEventListener("change", function () {
      var single = scope() === "single";
      areaSearch.disabled = !single;
      if (!single) { areaSearch.value = ""; areaCode.value = ""; }
    });
  });

  asOn.value = window.DateMask.toDisplay(initial.as_on);
  root.querySelector("[data-view]").addEventListener("click", view);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    if (scope() === "single" && !areaCode.value) { showToast("Select an area first.", "error"); return; }
    window.location.href = root.dataset.exportUrl + "?" + query();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });
  view();
})();
