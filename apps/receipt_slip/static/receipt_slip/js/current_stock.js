/* Stock > Current Stock -- read-only list of every item with its current stock. */
(function () {
  "use strict";

  var root = document.querySelector("[data-current-stock]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");

  function cell(text, className) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (className) td.className = className;
    return td;
  }

  var runDate = root.querySelector("[data-run-date]");
  var initial = JSON.parse(document.getElementById("cs-initial-data").textContent);

  function runQuery() {
    var iso = window.DateMask.toIso(runDate.value) || initial.run_date;
    return "run_date=" + encodeURIComponent(iso);
  }

  function load() {
    fetch(root.dataset.dataUrl + "?" + runQuery(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        tbody.textContent = "";
        res.rows.forEach(function (r) {
          var tr = document.createElement("tr");
          tr.append(cell(r.code, "master-table__code"), cell(r.name), cell(r.qty, "num"));
          tbody.appendChild(tr);
        });
        emptyNote.hidden = res.rows.length > 0;
      });
  }

  runDate.value = window.DateMask.toDisplay(initial.run_date);
  runDate.addEventListener("change", load);
  load();

  root.querySelector("[data-excel]").addEventListener("click", function () {
    window.location.href = root.dataset.exportUrl + "?" + runQuery();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () {
    window.location.href = root.dataset.exitUrl;
  });
})();
