/* Quotation listing: row selection (click / arrow keys), toolbar actions, delete dialog. */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var page = document.querySelector("[data-qsp-list]");
    if (!page) return;
    var rows = Array.prototype.slice.call(page.querySelectorAll("[data-rows] tr[data-no]"));
    var dialog = document.querySelector("[data-delete-dialog]");
    var selected = null;

    function url(template, no) {
      return page.dataset[template].replace("__NO__", encodeURIComponent(no));
    }

    function select(row, focus) {
      rows.forEach(function (r) {
        r.classList.toggle("is-selected", r === row);
        r.setAttribute("aria-selected", r === row ? "true" : "false");
      });
      selected = row;
      page.querySelectorAll("[data-needs-row]").forEach(function (btn) {
        btn.disabled = !row || btn.hasAttribute("data-no-perm");
      });
      if (row && focus) row.focus();
    }

    function run(action) {
      if (action === "add") {
        window.location.href = page.dataset.addUrl;
        return;
      }
      if (!selected) return;
      var no = selected.dataset.no;
      if (action === "modify") window.location.href = url("editUrl", no);
      if (action === "view") window.location.href = url("viewUrl", no);
      if (action === "print") window.open(url("printUrl", no), "_blank", "noopener");
      if (action === "delete" && dialog) {
        dialog.querySelector("[data-delete-no]").textContent = no;
        dialog.querySelector("[data-delete-form]").action = url("deleteUrl", no);
        dialog.showModal();
        dialog.querySelector("[data-delete-cancel]").focus();
      }
    }

    page.querySelectorAll("[data-action]").forEach(function (btn) {
      var action = btn.dataset.action;
      if (action === "refresh" || action === "exit") return;
      btn.addEventListener("click", function () { run(action); });
    });

    rows.forEach(function (row, index) {
      row.addEventListener("click", function () { select(row); });
      row.addEventListener("dblclick", function () { select(row); run("view"); });
      row.addEventListener("keydown", function (event) {
        if (event.key === "ArrowDown" && rows[index + 1]) { event.preventDefault(); select(rows[index + 1], true); }
        if (event.key === "ArrowUp" && rows[index - 1]) { event.preventDefault(); select(rows[index - 1], true); }
        if (event.key === "Enter") { event.preventDefault(); select(row); run("view"); }
        if (event.key === " ") { event.preventDefault(); select(row); }
      });
      row.addEventListener("focus", function () { if (selected !== row) select(row); });
    });

    if (dialog) {
      dialog.querySelector("[data-delete-cancel]").addEventListener("click", function () { dialog.close(); });
      dialog.querySelector("[data-delete-form]").addEventListener("submit", function () {
        dialog.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
      });
    }

    var initial = rows.filter(function (r) { return r.dataset.no === page.dataset.selected; })[0] || rows[0] || null;
    select(initial, false);
  });
})();
