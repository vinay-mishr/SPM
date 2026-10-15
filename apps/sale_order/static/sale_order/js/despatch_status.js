/* Sale Order > Pending Sales Order Status: orders due for despatch up to a date. */
(function () {
  "use strict";

  var root = document.querySelector("[data-despatch-status]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var totalCell = root.querySelector("[data-total]");
  var asOn = root.querySelector("[data-as-on]");
  var toast = document.querySelector("[data-toast]");
  var initial = JSON.parse(document.getElementById("ds-initial-data").textContent);

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

  function query() {
    var params = new URLSearchParams();
    params.set("as_on", window.DateMask.toIso(asOn.value));
    return params.toString();
  }

  function view() {
    fetch(root.dataset.dataUrl + "?" + query(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        tbody.textContent = "";
        if (!res.ok) { showToast(res.body.message || "Could not load the report.", "error"); return; }
        res.body.orders.forEach(function (o, i) {
          var tr = document.createElement("tr");
          tr.append(cell(i + 1, "num"), cell(o.party_name), cell(o.order_no, "master-table__code"),
            cell(dmy(o.order_date)), cell(dmy(o.despatch_date)), cell(o.amount, "num"));
          tbody.appendChild(tr);
        });
        totalCell.textContent = res.body.total;
        emptyNote.hidden = res.body.orders.length > 0;
      });
  }

  asOn.value = window.DateMask.toDisplay(initial.as_on);
  root.querySelector("[data-view]").addEventListener("click", view);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    window.location.href = root.dataset.exportUrl + "?" + query();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });
  view();
})();
