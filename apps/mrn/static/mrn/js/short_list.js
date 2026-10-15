/* MRN > Short List New -- parts below their reorder level, A (all) or P (pending PO). */
(function () {
  "use strict";

  var root = document.querySelector("[data-short-list]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var modeSelect = root.querySelector("[data-mode]");
  var vfp = root.dataset.layout === "vfp";

  function cell(text, className) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (className) td.className = className;
    return td;
  }

  function query() {
    var mode = modeSelect ? modeSelect.value : "A";
    return "?mode=" + encodeURIComponent(mode) + (vfp ? "&layout=vfp" : "");
  }

  function show() {
    fetch(root.dataset.dataUrl + query(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        tbody.textContent = "";
        res.rows.forEach(function (r) {
          var tr = document.createElement("tr");
          if (vfp) {
            tr.append(cell(r.code, "master-table__code"), cell(r.name), cell(r.unit),
              cell(r.current, "num"), cell(r.reorder, "num"), cell(r.short, "num"), cell(r.on_order, "num"));
          } else {
            tr.append(cell(r.code, "master-table__code"), cell(r.name), cell(r.unit), cell(r.reorder, "num"),
              cell(r.current, "num"), cell(r.pending_sale, "num"), cell(r.short, "num"), cell(r.on_order, "num"));
          }
          tbody.appendChild(tr);
        });
        emptyNote.hidden = res.rows.length > 0;
      });
  }

  root.querySelector("[data-show]").addEventListener("click", show);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    window.location.href = root.dataset.exportUrl + query();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });
  show();
})();
