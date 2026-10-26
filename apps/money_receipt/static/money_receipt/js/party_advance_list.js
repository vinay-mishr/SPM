/* Money Receipts > Party Advance List: every party with a pending advance, grand total. */
(function () {
  "use strict";

  var root = document.querySelector("[data-party-advance-list]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var toast = document.querySelector("[data-toast]");

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

  function view() {
    fetch(root.dataset.dataUrl, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        tbody.textContent = "";
        if (!res.ok) { showToast(res.body.message || "Could not load the report.", "error"); return; }
        res.body.rows.forEach(function (r) {
          var tr = document.createElement("tr");
          tr.append(cell(r.party_name), cell(r.city), cell(r.amount, "num"));
          tbody.appendChild(tr);
        });
        emptyNote.hidden = res.body.rows.length > 0;
        root.querySelector("[data-g-total]").value = res.body.total;
      });
  }

  root.querySelector("[data-view]").addEventListener("click", view);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    window.location.href = root.dataset.exportUrl;
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });
  view();
})();
