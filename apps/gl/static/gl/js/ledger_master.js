/* General Ledger Master — list screen + shared Add/Modify/View form (old VFP "do form gl"). */
(function () {
  "use strict";

  var root = document.querySelector("[data-gl-master]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var countNote = root.querySelector("[data-count]");
  var searchBox = root.querySelector("[data-search]");
  var toast = document.querySelector("[data-toast]");
  var deleteDialog = document.getElementById("gl-delete-dialog");
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var money = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  var initial = JSON.parse(document.getElementById("gl-initial-data").textContent);
  var state = { ledgers: initial.ledgers, selectedId: null, query: "" };

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function selectedLedger() {
    return state.ledgers.find(function (l) { return l.id === state.selectedId; }) || null;
  }

  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text;
    if (cls) td.className = cls;
    return td;
  }

  function matches(l) {
    if (!state.query) return true;
    return [l.description, l.group_name, l.ledger_code].join(" ").toLowerCase().indexOf(state.query) > -1;
  }

  function render() {
    var visible = state.ledgers.filter(matches);
    tbody.textContent = "";
    visible.forEach(function (l) {
      var tr = document.createElement("tr");
      tr.dataset.id = l.id;
      tr.tabIndex = 0;
      tr.setAttribute("aria-selected", String(l.id === state.selectedId));
      if (l.id === state.selectedId) tr.classList.add("is-selected");
      tr.append(
        cell(l.description),
        cell(l.group_name),
        cell(money.format(Number(l.opening_balance)), "num"),
        cell(l.ledger_code, "master-table__code")
      );
      tbody.appendChild(tr);
    });
    emptyNote.hidden = state.ledgers.length > 0;
    countNote.textContent = state.ledgers.length
      ? visible.length + " of " + state.ledgers.length + " ledgers"
      : "";
    updateToolbar();
  }

  function updateToolbar() {
    var hasSelection = Boolean(selectedLedger());
    root.querySelectorAll('[data-action="modify"], [data-action="delete"], [data-action="view"]').forEach(function (btn) {
      btn.disabled = !hasSelection;
    });
  }

  function select(id) {
    state.selectedId = id;
    tbody.querySelectorAll("tr").forEach(function (tr) {
      var on = tr.dataset.id === id;
      tr.classList.toggle("is-selected", on);
      tr.setAttribute("aria-selected", String(on));
    });
    updateToolbar();
  }

  function refresh(selectId) {
    return fetch(root.dataset.listUrl, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        state.ledgers = data.ledgers;
        if (selectId !== undefined) state.selectedId = selectId;
        if (!selectedLedger()) state.selectedId = null;
        render();
      });
  }

  tbody.addEventListener("click", function (e) { var tr = e.target.closest("tr"); if (tr) select(tr.dataset.id); });
  tbody.addEventListener("dblclick", function (e) { var tr = e.target.closest("tr"); if (tr) { select(tr.dataset.id); openForm("view"); } });
  tbody.addEventListener("keydown", function (e) {
    var tr = e.target.closest("tr");
    if (!tr) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      var next = e.key === "ArrowDown" ? tr.nextElementSibling : tr.previousElementSibling;
      if (next) { next.focus(); select(next.dataset.id); }
    } else if (e.key === "Enter") { select(tr.dataset.id); openForm("view"); }
  });
  searchBox.addEventListener("input", function () { state.query = searchBox.value.trim().toLowerCase(); render(); });

  /* --- Form (ADD / MODIFY / VIEW) ------------------------------------------------ */

  var dialog = document.getElementById("gl-form-dialog");
  var form = dialog.querySelector("[data-gl-form]");
  var alertBox = dialog.querySelector("[data-form-alert]");
  var discard = dialog.querySelector("[data-discard]");
  var confirmBtn = dialog.querySelector("[data-form-confirm]");
  var descriptionInput = dialog.querySelector('[data-field="description"]');
  var codeInput = dialog.querySelector('[data-field="ledger_code"]');
  var groupSearch = dialog.querySelector('[data-field="group_code_search"]');
  var groupCode = dialog.querySelector('[data-field="group_code"]');
  var groupList = dialog.querySelector("[data-group-list]");
  var balanceInput = dialog.querySelector('[data-field="opening_balance"]');
  var treeSearch = dialog.querySelector('[data-field="tree_search"]');
  var treeCode = dialog.querySelector('[data-field="gl_type"]');
  var TREE = [];

  var GROUPS = [];
  var formState = { mode: "add", ledger: null, snapshot: "" };

  function loadGroups() {
    if (GROUPS.length) return;
    GROUPS = (initial.groups || []);
    TREE = (initial.tree_groups || []);
  }

  function fillGroupList() {
    groupList.textContent = "";
    GROUPS.forEach(function (g) {
      var o = document.createElement("option");
      o.value = g.name;
      o.dataset.code = g.code;
      groupList.appendChild(o);
    });
  }

  groupSearch.addEventListener("input", function () {
    var hit = GROUPS.find(function (g) { return g.name.toLowerCase() === groupSearch.value.trim().toLowerCase(); });
    groupCode.value = hit ? hit.code : "";
  });

  // Universal Help/Lookup: focus Ledger Group, press Enter, pick from a searchable grid.
  if (window.HelpLookup) {
    window.HelpLookup.attach(groupSearch, {
      data: function () { return GROUPS.map(function (g) { return { code: g.code, name: g.name }; }); },
      valueField: "name",
      displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Group" }],
      title: "Ledger Group",
      seedText: function () { return ""; },
      onSelect: function (row) { groupCode.value = row.code; },
    });
  }

  function treeLabel(g) { return "    ".repeat(g.level) + g.name; }

  function treeName(code) {
    var hit = TREE.find(function (g) { return g.code === code; });
    return hit ? hit.name : "";
  }

  treeSearch.addEventListener("input", function () {
    var hit = TREE.find(function (g) { return g.name.toLowerCase() === treeSearch.value.trim().toLowerCase(); });
    treeCode.value = hit ? hit.code : "";
  });

  if (window.HelpLookup) {
    window.HelpLookup.attach(treeSearch, {
      data: function () { return TREE.map(function (g) { return { code: g.code, name: g.name, label: treeLabel(g) }; }); },
      valueField: "name",
      displayFields: [{ key: "code", label: "Code" }, { key: "label", label: "Group" }],
      title: "Group",
      seedText: function () { return ""; },
      onSelect: function (row) { treeCode.value = row.code; },
    });
  }

  function values() {
    return {
      description: descriptionInput.value.trim(),
      group_code: groupCode.value.trim(),
      gl_type: treeCode.value.trim(),
      opening_balance: balanceInput.value.trim()
    };
  }

  function clearErrors() {
    alertBox.hidden = true;
    alertBox.textContent = "";
    form.querySelectorAll("[data-error-for]").forEach(function (el) { el.textContent = ""; });
    form.querySelectorAll(".mform__field.is-invalid").forEach(function (el) { el.classList.remove("is-invalid"); });
  }

  function showErrors(errors) {
    var first = null;
    Object.keys(errors || {}).forEach(function (name) {
      var message = typeof errors[name] === "string" ? errors[name]
        : (errors[name].map ? errors[name].map(function (e) { return e.message || e; }).join(" ") : String(errors[name]));
      var target = form.querySelector('[data-error-for="' + name + '"]');
      var field = name === "group_code" ? groupSearch : form.querySelector('[data-field="' + name + '"]');
      if (target) {
        target.textContent = message;
        if (field) { field.closest(".mform__field").classList.add("is-invalid"); first = first || field; }
      } else {
        alertBox.textContent = message;
        alertBox.hidden = false;
      }
    });
    if (first) first.focus();
  }

  function previewCode() {
    if (formState.mode !== "add" || !root.dataset.nextCodeUrl) return;
    var description = descriptionInput.value.trim();
    if (!description) { codeInput.value = ""; return; }
    fetch(root.dataset.nextCodeUrl + "?description=" + encodeURIComponent(description), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) { if (formState.mode === "add") codeInput.value = data.code || ""; })
      .catch(function () {});
  }

  function setMode(mode) {
    formState.mode = mode;
    dialog.dataset.mode = mode;
    dialog.querySelector("[data-mode-label]").textContent = mode === "add" ? "Add" : mode === "modify" ? "Modify" : "View";
    var readOnly = mode === "view";
    descriptionInput.readOnly = readOnly;
    groupSearch.readOnly = readOnly;
    treeSearch.readOnly = readOnly;
    balanceInput.readOnly = readOnly;
    confirmBtn.hidden = readOnly;
  }

  function fill(ledger) {
    codeInput.value = ledger ? ledger.ledger_code : "";
    descriptionInput.value = ledger ? ledger.description : "";
    groupCode.value = ledger ? ledger.group_code : "";
    groupSearch.value = ledger ? ledger.group_name : "";
    treeCode.value = ledger ? ledger.gl_type : "";
    treeSearch.value = ledger ? treeName(ledger.gl_type) : "";
    balanceInput.value = ledger ? ledger.opening_balance : "0.00";
  }

  function isDirty() {
    return formState.mode !== "view" && JSON.stringify(values()) !== formState.snapshot;
  }

  function close() {
    discard.hidden = true;
    dialog.close();
  }

  function requestExit() {
    close();
  }

  function save() {
    if (formState.mode === "view") return;
    clearErrors();
    var data = new FormData();
    var v = values();
    data.append("description", v.description);
    data.append("gl_type", v.gl_type);
    data.append("group_code", v.group_code);
    data.append("opening_balance", v.opening_balance);

    var url = formState.mode === "modify"
      ? root.dataset.updateUrl.replace("/0/", "/" + encodeURIComponent(formState.ledger.id) + "/")
      : root.dataset.createUrl;

    confirmBtn.disabled = true;
    fetch(url, {
      method: "POST", body: data, credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" }
    })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; }); })
      .then(function (result) {
        if (result.ok) {
          close();
          showToast(result.body.message);
          refresh(result.body.ledger.id);
        } else if (result.body.errors) {
          showErrors(result.body.errors);
        } else {
          alertBox.textContent = result.body.message || "Could not save (error " + result.status + ").";
          alertBox.hidden = false;
        }
      })
      .catch(function () {
        alertBox.textContent = "Could not reach the server. Nothing was saved.";
        alertBox.hidden = false;
      })
      .finally(function () { confirmBtn.disabled = false; });
  }

  form.addEventListener("submit", function (e) { e.preventDefault(); save(); });
  descriptionInput.addEventListener("change", previewCode);
  form.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" || (e.target.tagName !== "INPUT")) return;
    e.preventDefault();
    var order = [descriptionInput, groupSearch, balanceInput].filter(function (el) { return !el.readOnly; });
    var index = order.indexOf(e.target);
    if (index > -1 && index < order.length - 1) order[index + 1].focus();
    else if (formState.mode !== "view") confirmBtn.focus();
  });

  dialog.querySelectorAll("[data-form-exit]").forEach(function (b) { b.addEventListener("click", requestExit); });
  dialog.addEventListener("cancel", function (e) {
    e.preventDefault();
    if (!discard.hidden) discard.hidden = true; else requestExit();
  });
  dialog.querySelector("[data-discard-cancel]").addEventListener("click", function () { discard.hidden = true; });
  dialog.querySelector("[data-discard-confirm]").addEventListener("click", close);

  function openForm(mode) {
    var ledger = mode === "add" ? null : selectedLedger();
    formState.ledger = ledger;
    loadGroups();
    fillGroupList();
    clearErrors();
    fill(ledger);
    setMode(mode);
    discard.hidden = true;
    formState.snapshot = JSON.stringify(values());
    dialog.showModal();
    (mode === "view" ? dialog.querySelector(".modal__footer [data-form-exit]") : descriptionInput).focus();
  }

  /* --- Delete -------------------------------------------------------------------- */

  function openDelete(ledger) {
    var list = deleteDialog.querySelector("[data-delete-details]");
    var alertBox2 = deleteDialog.querySelector("[data-delete-alert]");
    list.textContent = "";
    [["Ledger Code", ledger.ledger_code], ["Description", ledger.description],
     ["Group", ledger.group_name], ["Opening Balance", money.format(Number(ledger.opening_balance))]]
      .forEach(function (pair) {
        var dt = document.createElement("dt"), dd = document.createElement("dd");
        dt.textContent = pair[0]; dd.textContent = pair[1] || "—";
        list.append(dt, dd);
      });
    alertBox2.hidden = true;
    deleteDialog.querySelector("[data-delete-confirm]").disabled = false;
    deleteDialog.showModal();
    deleteDialog.querySelector("[data-delete-cancel]").focus();
  }

  function confirmDelete() {
    var ledger = selectedLedger();
    var button = deleteDialog.querySelector("[data-delete-confirm]");
    var alertBox2 = deleteDialog.querySelector("[data-delete-alert]");
    if (!ledger) return;
    button.disabled = true;
    fetch(root.dataset.deleteUrl.replace("/0/", "/" + encodeURIComponent(ledger.id) + "/"), {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" }
    })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (result) {
        if (result.ok) {
          deleteDialog.close();
          state.selectedId = null;
          showToast(result.body.message);
          return refresh();
        }
        alertBox2.textContent = result.body.message || "The ledger could not be deleted.";
        alertBox2.hidden = false;
      })
      .catch(function () {
        alertBox2.textContent = "Could not reach the server. Please try again.";
        alertBox2.hidden = false;
        button.disabled = false;
      });
  }

  deleteDialog.querySelectorAll("[data-delete-cancel]").forEach(function (b) { b.addEventListener("click", function () { deleteDialog.close(); }); });
  deleteDialog.querySelector("[data-delete-confirm]").addEventListener("click", confirmDelete);

  /* --- Toolbar ------------------------------------------------------------------ */

  var actions = {
    add: function () { openForm("add"); },
    modify: function () { if (selectedLedger()) openForm("modify"); },
    view: function () { if (selectedLedger()) openForm("view"); },
    "delete": function () { var l = selectedLedger(); if (l) openDelete(l); },
    print: function () { window.print(); },
    exit: function () { window.location.href = root.dataset.exitUrl; }
  };
  root.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function () { actions[btn.dataset.action](); });
  });
  document.addEventListener("keydown", function (e) {
    if (!e.altKey || document.querySelector("dialog[open]")) return;
    var map = { a: "add", m: "modify", d: "delete", v: "view", p: "print", e: "exit" };
    var action = map[e.key.toLowerCase()];
    var button = action && root.querySelector('[data-action="' + action + '"]');
    if (button && !button.disabled) { e.preventDefault(); button.click(); }
  });

  render();
})();
