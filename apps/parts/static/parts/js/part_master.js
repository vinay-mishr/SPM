/* Part Master — list screen: grid, selection, search, toolbar and delete dialog.
 * Uses window.SPPartForm (part_master_form.js) for Add / Modify / View.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-part-master]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var countNote = root.querySelector("[data-count]");
  var searchBox = root.querySelector("[data-search]");
  var toast = document.querySelector("[data-toast]");
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var initial = JSON.parse(document.getElementById("part-initial-data").textContent);
  var money = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  var state = { parts: initial.parts, selected: null, query: "" };

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function selected() {
    return state.parts.find(function (p) { return p.id === state.selected; }) || null;
  }

  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text;
    if (cls) td.className = cls;
    return td;
  }

  function matches(p) {
    if (!state.query) return true;
    return [p.part_number, p.description_1, p.description_2, p.drawing_no, p.hsn_code, p.unit]
      .join(" ").toLowerCase().indexOf(state.query) > -1;
  }

  function render() {
    var visible = state.parts.filter(matches);
    tbody.textContent = "";
    visible.forEach(function (p) {
      var tr = document.createElement("tr");
      tr.dataset.id = p.id;
      tr.tabIndex = 0;
      if (p.id === state.selected) tr.classList.add("is-selected");
      tr.append(
        cell(p.part_number, "master-table__code"),
        cell(p.description_1),
        cell(p.drawing_no),
        cell(p.hsn_code),
        cell(p.unit),
        cell(money.format(Number(p.gst_percent)), "num"),
        cell(money.format(Number(p.purchase_rate)), "num"),
        cell(money.format(Number(p.sale_rate)), "num"),
        cell(p.sub_assembly ? "Y" : "", "part-table__sa")
      );
      tbody.appendChild(tr);
    });
    emptyNote.hidden = visible.length > 0;
    countNote.textContent = visible.length + " of " + state.parts.length + " part" + (state.parts.length === 1 ? "" : "s");
    updateToolbar();
  }

  function updateToolbar() {
    var has = Boolean(selected());
    ["modify", "delete", "view"].forEach(function (a) {
      root.querySelector('[data-action="' + a + '"]').disabled = !has;
    });
  }

  function select(id) {
    state.selected = id;
    tbody.querySelectorAll("tr").forEach(function (tr) { tr.classList.toggle("is-selected", tr.dataset.id === id); });
    updateToolbar();
  }

  function refresh(selectId) {
    return fetch(root.dataset.listUrl, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        state.parts = data.parts;
        if (selectId !== undefined) state.selected = selectId;
        if (!selected()) state.selected = null;
        render();
        var row = tbody.querySelector('tr[data-id="' + CSS.escape(state.selected || "") + '"]');
        if (row) row.scrollIntoView({ block: "nearest" });
      });
  }

  var actions = {
    add: function () { SPPartForm.open("add", null); },
    modify: function () { var p = selected(); if (p) SPPartForm.open("modify", p); },
    view: function () { var p = selected(); if (p) SPPartForm.open("view", p); },
    "delete": function () { var p = selected(); if (p) SPPartForm.open("delete", p); },
    exit: function () { window.location.href = root.dataset.exitUrl; }
  };

  root.querySelectorAll("[data-action]").forEach(function (b) {
    b.addEventListener("click", function () { actions[b.dataset.action](); });
  });
  tbody.addEventListener("click", function (e) { var tr = e.target.closest("tr"); if (tr) select(tr.dataset.id); });
  tbody.addEventListener("dblclick", function (e) { var tr = e.target.closest("tr"); if (tr) { select(tr.dataset.id); actions.view(); } });
  tbody.addEventListener("keydown", function (e) {
    var tr = e.target.closest("tr");
    if (!tr) return;
    if (e.key === "Enter") { select(tr.dataset.id); actions.view(); }
    else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      var next = e.key === "ArrowDown" ? tr.nextElementSibling : tr.previousElementSibling;
      if (next) { next.focus(); select(next.dataset.id); }
    }
  });
  searchBox.addEventListener("input", function () { state.query = searchBox.value.trim().toLowerCase(); render(); });
  document.addEventListener("keydown", function (e) {
    if (!e.altKey || document.querySelector("dialog[open]")) return;
    var map = { a: "add", m: "modify", d: "delete", v: "view", x: "exit" };
    var btn = map[e.key.toLowerCase()] && root.querySelector('[data-action="' + map[e.key.toLowerCase()] + '"]');
    if (btn && !btn.disabled) { e.preventDefault(); btn.click(); }
  });
  SPPartForm.init({
    createUrl: root.dataset.createUrl,
    updateUrl: root.dataset.updateUrl,
    deleteUrl: root.dataset.deleteUrl,
    partiesUrl: root.dataset.partiesUrl,
    csrfToken: csrfToken,
    onSaved: function (p, message) { showToast(message); refresh(p.id); },
    onDeleted: function (message) { state.selected = null; showToast(message); refresh(); }
  });

  render();
})();
