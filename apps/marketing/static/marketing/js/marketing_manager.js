/* Marketing Manager — list screen: grid, selection, search, toolbar and delete dialog.
 * Uses window.SPManagerForm (marketing_manager_form.js) for Add / Modify / View.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-mm-master]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var countNote = root.querySelector("[data-count]");
  var searchBox = root.querySelector("[data-search]");
  var toast = document.querySelector("[data-toast]");
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var initial = JSON.parse(document.getElementById("mm-initial-data").textContent);
  var state = { managers: initial.managers, selected: null, query: "" };

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function selected() {
    return state.managers.find(function (m) { return m.id === state.selected; }) || null;
  }

  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text;
    if (cls) td.className = cls;
    return td;
  }

  function matches(m) {
    return !state.query || [m.name, m.city, m.mobile, m.code].join(" ").toLowerCase().indexOf(state.query) > -1;
  }

  function render() {
    var visible = state.managers.filter(matches);
    tbody.textContent = "";
    visible.forEach(function (m) {
      var tr = document.createElement("tr");
      tr.dataset.id = m.id;
      tr.tabIndex = 0;
      if (m.id === state.selected) tr.classList.add("is-selected");
      tr.append(cell(m.name), cell(m.mobile), cell(m.code, "master-table__code"));
      tbody.appendChild(tr);
    });
    emptyNote.hidden = visible.length > 0;
    countNote.textContent = visible.length + " of " + state.managers.length + " manager" + (state.managers.length === 1 ? "" : "s");
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
        state.managers = data.managers;
        if (selectId !== undefined) state.selected = selectId;
        if (!selected()) state.selected = null;
        render();
      });
  }

  var actions = {
    add: function () { SPManagerForm.open("add", null); },
    modify: function () { var m = selected(); if (m) SPManagerForm.open("modify", m); },
    view: function () { var m = selected(); if (m) SPManagerForm.open("view", m); },
    "delete": function () { var m = selected(); if (m) SPManagerForm.open("delete", m); },
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
    var map = { a: "add", m: "modify", d: "delete", v: "view", e: "exit" };
    var btn = map[e.key.toLowerCase()] && root.querySelector('[data-action="' + map[e.key.toLowerCase()] + '"]');
    if (btn && !btn.disabled) { e.preventDefault(); btn.click(); }
  });
  SPManagerForm.init({
    createUrl: root.dataset.createUrl,
    updateUrl: root.dataset.updateUrl,
    deleteUrl: root.dataset.deleteUrl,
    nextCodeUrl: root.dataset.nextCodeUrl,
    csrfToken: csrfToken,
    onSaved: function (m, message) { showToast(message); refresh(m.id); },
    onDeleted: function (message) { state.selected = null; showToast(message); refresh(); }
  });

  render();
})();
