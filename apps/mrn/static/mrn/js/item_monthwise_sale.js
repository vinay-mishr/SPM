/* Item-wise Month-wise Sale (qty) -- read-only. Old VFP: ITEM-WISE/MONTHWISE SALE REPORT. */
(function () {
  "use strict";

  var root = document.querySelector("[data-item-monthwise-sale]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var fyFrom = root.querySelector("[data-fy-from]");
  var dateError = root.querySelector("[data-date-error]");
  var toast = document.querySelector("[data-toast]");

  var initial = JSON.parse(document.getElementById("iwms-initial-data").textContent);

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function cell(text, className) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (className) td.className = className;
    return td;
  }

  function render(rows) {
    tbody.textContent = "";
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.append(cell(r.item_name), cell(r.unit), cell(r.rop, "num"));
      r.months.forEach(function (m) { tr.appendChild(cell(Number(m) ? m : "", "num")); });
      tr.append(cell(r.total, "num"), cell(r.average, "num"));
      tbody.appendChild(tr);
    });
    emptyNote.hidden = rows.length > 0;
  }

  function currentQuery() {
    var params = new URLSearchParams();
    params.set("fy_from", window.DateMask.toIso(fyFrom.value));
    return params;
  }

  function view() {
    if (!window.DateMask.toIso(fyFrom.value)) { dateError.textContent = "Enter a valid financial year start date."; dateError.hidden = false; return; }
    dateError.hidden = true;
    fetch(root.dataset.dataUrl + "?" + currentQuery().toString(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        if (!res.ok) { showToast(res.body.message || "Could not load the report.", "error"); return; }
        render(res.body.rows || []);
      })
      .catch(function () { showToast("Could not reach the server.", "error"); });
  }

  root.querySelector("[data-view]").addEventListener("click", view);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    if (!window.DateMask.toIso(fyFrom.value)) { showToast("Enter a valid financial year start date.", "error"); return; }
    window.location.href = root.dataset.exportUrl + "?" + currentQuery().toString();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  fyFrom.value = window.DateMask.toDisplay(initial.fy_from);
  render(initial.rows || []);
})();
