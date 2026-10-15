/* Sale Order > Rep Wise Order Received: orders booked in a date range, grouped by representative. */
(function () {
  "use strict";

  var root = document.querySelector("[data-rep-orders]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var grand = root.querySelector("[data-grand]");
  var repSearch = root.querySelector("[data-rep-search]");
  var repCode = root.querySelector("[data-rep-code]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var toast = document.querySelector("[data-toast]");
  var initial = JSON.parse(document.getElementById("ro-initial-data").textContent);

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
    params.set("start_date", window.DateMask.toIso(startDate.value));
    params.set("end_date", window.DateMask.toIso(endDate.value));
    if (scope() === "single" && repCode.value) params.set("rep_code", repCode.value);
    return params.toString();
  }

  function view() {
    if (scope() === "single" && !repCode.value) { showToast("Select a rep first.", "error"); return; }
    fetch(root.dataset.dataUrl + "?" + query(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        tbody.textContent = "";
        if (!res.ok) { showToast(res.body.message || "Could not load the report.", "error"); return; }
        res.body.groups.forEach(function (g) {
          var head = document.createElement("tr");
          head.className = "pe-part";
          var hc = cell(g.rep_name || g.rep_code);
          hc.colSpan = 5;
          head.appendChild(hc);
          tbody.appendChild(head);
          g.orders.forEach(function (o) {
            var tr = document.createElement("tr");
            tr.append(cell(o.party_name), cell(o.city), cell(o.div + o.order_no, "master-table__code"),
              cell(dmy(o.date)), cell(o.amount, "num"));
            tbody.appendChild(tr);
          });
          var total = document.createElement("tr");
          total.className = "pl-total";
          total.append(cell(""), cell(""), cell(""), cell("TOTAL"), cell(g.total, "num"));
          tbody.appendChild(total);
        });
        grand.textContent = res.body.grand_total;
        emptyNote.hidden = res.body.groups.length > 0;
      });
  }

  window.HelpLookup.attach(repSearch, {
    endpoint: root.dataset.repsUrl, resultsKey: "reps", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Rep" }],
    title: "Rep",
    onSelect: function (row) { repCode.value = row.code; repSearch.value = row.name; },
  });

  root.querySelectorAll("[data-scope]").forEach(function (radio) {
    radio.addEventListener("change", function () {
      var single = scope() === "single";
      repSearch.disabled = !single;
      if (!single) { repSearch.value = ""; repCode.value = ""; }
    });
  });

  startDate.value = window.DateMask.toDisplay(initial.start_date);
  endDate.value = window.DateMask.toDisplay(initial.end_date);
  root.querySelector("[data-view]").addEventListener("click", view);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    if (scope() === "single" && !repCode.value) { showToast("Select a rep first.", "error"); return; }
    window.location.href = root.dataset.exportUrl + "?" + query();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });
  view();
})();
