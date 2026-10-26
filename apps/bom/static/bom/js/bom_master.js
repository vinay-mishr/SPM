/* Bill of Material Master — list of parts that have a BOM; ADD / MODIFY / VIEW open a
 * form where components are searched and added one at a time (CODE + QTY + OK), then
 * CONFIRM saves the whole set for that part in one go (old VFP "BILL OF MATERIAL MASTER").
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-bom-master]");
  if (!root) return;

  // Same fixed unit codes as Part Master's own unit datalist -- kept in sync manually
  // since Part Master's list lives in a plain <datalist>, not a shared JS constant.
  var UNIT_OPTIONS = ["NUM", "UNT", "SET", "PCS", "KG", "MTR", "LIT", "PKT", "BOX", "DAY", "MIL"]
    .map(function (u) { return { value: u }; });

  var initial = JSON.parse(document.getElementById("bom-initial-data").textContent);
  var canEdit = initial.can_edit;
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var countNote = root.querySelector("[data-count]");
  var searchBox = root.querySelector("[data-search]");
  var toast = document.querySelector("[data-toast]");

  var state = { parents: initial.parents, selected: null, query: "" };

  /* --- Helpers ------------------------------------------------------------------ */

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text;
    if (cls) td.className = cls;
    return td;
  }

  function selectedParent() {
    return state.parents.find(function (p) { return p.part_code === state.selected; }) || null;
  }

  function matches(p) {
    if (!state.query) return true;
    return (p.part_code + " " + p.part_name).toLowerCase().indexOf(state.query) > -1;
  }

  function fetchJson(url, options) {
    return fetch(url, Object.assign({ credentials: "same-origin" }, options || {})).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; });
    });
  }

  function postJson(url, data) {
    return fetchJson(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(data)
    });
  }

  function postForm(url) {
    return fetchJson(url, { method: "POST", headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" } });
  }

  /* --- List ------------------------------------------------------------------- */

  function render() {
    var visible = state.parents.filter(matches);
    tbody.textContent = "";
    visible.forEach(function (p) {
      var tr = document.createElement("tr");
      tr.dataset.code = p.part_code;
      tr.tabIndex = 0;
      if (p.part_code === state.selected) tr.classList.add("is-selected");
      if (p.is_duplicate) tr.classList.add("is-duplicate");
      tr.append(
        cell(p.part_code, "master-table__code"),
        cell(p.part_name + (p.is_duplicate ? " (ambiguous part number)" : "")),
        cell(p.unit),
        cell(Number(p.component_count).toFixed(3), "num")
      );
      tbody.appendChild(tr);
    });
    emptyNote.hidden = state.parents.length > 0;
    countNote.textContent = visible.length + " of " + state.parents.length + " Bills of Material";
    updateToolbar();
  }

  function updateToolbar() {
    var p = selectedParent();
    var has = Boolean(p);
    var ambiguous = has && p.is_duplicate;
    root.querySelector('[data-action="view"]').disabled = !has;
    root.querySelector('[data-action="modify"]').disabled = !has || !canEdit || ambiguous;
    root.querySelector('[data-action="delete"]').disabled = !has || !canEdit || ambiguous;
  }

  function select(code) {
    state.selected = code;
    tbody.querySelectorAll("tr").forEach(function (tr) { tr.classList.toggle("is-selected", tr.dataset.code === code); });
    updateToolbar();
  }

  function refresh(selectCode) {
    return fetchJson(root.dataset.listUrl).then(function (res) {
      state.parents = res.body.parents;
      state.selected = selectCode !== undefined ? selectCode : state.selected;
      if (!selectedParent()) state.selected = null;
      render();
    });
  }

  tbody.addEventListener("click", function (e) { var tr = e.target.closest("tr"); if (tr) select(tr.dataset.code); });
  tbody.addEventListener("dblclick", function (e) {
    var tr = e.target.closest("tr");
    if (tr) { select(tr.dataset.code); openForm(canEdit ? "modify" : "view"); }
  });
  tbody.addEventListener("keydown", function (e) {
    var tr = e.target.closest("tr");
    if (!tr) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      var next = e.key === "ArrowDown" ? tr.nextElementSibling : tr.previousElementSibling;
      if (next) { next.focus(); select(next.dataset.code); }
    }
  });
  searchBox.addEventListener("input", function () { state.query = searchBox.value.trim().toLowerCase(); render(); });

  /* --- Form (ADD / MODIFY / VIEW) ------------------------------------------------ */

  var dialog = document.getElementById("bom-form-dialog");
  var form = dialog.querySelector("[data-bom-form]");
  var alertBox = dialog.querySelector("[data-form-alert]");
  var confirmBox = dialog.querySelector("[data-confirm-box]");
  var confirmText = dialog.querySelector("[data-confirm-text]");
  var confirmBtn = dialog.querySelector("[data-form-confirm]");
  var partCode = dialog.querySelector('[data-field="part_code"]');
  var partSearch = dialog.querySelector("[data-part-search]");
  var partList = dialog.querySelector("[data-part-list]");
  var rowItemCode = dialog.querySelector("[data-row-item-code]");
  var rowItemSearch = dialog.querySelector("[data-row-item-search]");
  var itemList = dialog.querySelector("[data-item-list]");
  var rowQty = dialog.querySelector("[data-row-qty]");
  var rowUnit = dialog.querySelector("[data-row-unit]");
  var rowError = dialog.querySelector("[data-row-error]");
  var gridBody = dialog.querySelector("[data-grid-rows]");
  var gridEmpty = dialog.querySelector("[data-grid-empty]");

  var formState = { mode: "add", parts: {}, items: {}, components: [], snapshot: "", afterConfirm: null, selectedRow: -1, editIndex: -1 };

  function clearErrors() {
    alertBox.hidden = true;
    form.querySelectorAll("[data-error-for]").forEach(function (el) { el.textContent = ""; });
    form.querySelectorAll(".mform__field.is-invalid").forEach(function (el) { el.classList.remove("is-invalid"); });
  }

  function showErrors(errors) {
    var generic = [];
    Object.keys(errors || {}).forEach(function (key) {
      if (key === "part_code") {
        var target = form.querySelector('[data-error-for="part_code"]');
        target.textContent = errors[key];
        partCode.closest(".mform__field").classList.add("is-invalid");
      } else {
        generic.push(errors[key]);
      }
    });
    if (generic.length) {
      alertBox.textContent = generic.join(" ");
      alertBox.hidden = false;
    }
  }

  function selectGridRow(index) {
    if (index < 0 || index >= formState.components.length) index = -1;
    formState.selectedRow = index;
    gridBody.querySelectorAll("tr").forEach(function (tr, i) {
      tr.classList.toggle("is-selected", i === index);
    });
    if (index > -1) {
      var tr = gridBody.children[index];
      if (tr) tr.focus();
    }
  }

  function removeGridRow(index) {
    if (index < 0 || index >= formState.components.length) return;
    formState.components.splice(index, 1);
    renderGrid();
    var next = Math.min(index, formState.components.length - 1);
    selectGridRow(next);
  }

  // Double-click a grid row to pull it back into the Part Description add-row for
  // editing (e.g. to fix its Unit) -- removes the row so OK re-adds the edited version
  // in the SAME position (editIndex), instead of at the end of the list.
  function editRow(index) {
    if (index < 0 || index >= formState.components.length) return;
    var row = formState.components[index];
    formState.components.splice(index, 1);
    formState.editIndex = index;
    renderGrid();
    rowItemCode.value = row.item_code;
    rowItemSearch.value = row.item_name;
    rowQty.value = row.quantity;
    rowUnit.value = row.unit || "";
    rowError.textContent = "";
    rowItemSearch.focus();
    rowItemSearch.select();
  }

  function renderGrid() {
    gridBody.textContent = "";
    formState.components.forEach(function (row, index) {
      var tr = document.createElement("tr");
      if (formState.mode !== "view") {
        tr.tabIndex = 0;
        tr.addEventListener("click", function () { selectGridRow(index); });
        tr.addEventListener("dblclick", function () { editRow(index); });
        tr.addEventListener("keydown", function (e) {
          if (e.key === "ArrowDown") { e.preventDefault(); selectGridRow(index + 1); }
          else if (e.key === "ArrowUp") { e.preventDefault(); selectGridRow(index - 1); }
          else if (e.key === " " || e.key === "Spacebar") { e.preventDefault(); removeGridRow(index); }
          else if (e.key === "Enter") { e.preventDefault(); editRow(index); }
        });
      }
      tr.append(
        (function () { var td = document.createElement("td"); td.className = "num"; td.textContent = index + 1; return td; })(),
        (function () { var td = document.createElement("td"); td.textContent = row.item_code; return td; })(),
        (function () { var td = document.createElement("td"); td.textContent = row.item_name; return td; })(),
        (function () { var td = document.createElement("td"); td.className = "num"; td.textContent = Number(row.quantity).toFixed(3); return td; })(),
        (function () { var td = document.createElement("td"); td.textContent = row.unit || ""; return td; })()
      );
      gridBody.appendChild(tr);
    });
    gridEmpty.hidden = formState.components.length > 0;
  }

  function loadParts(q) {
    if (!q) return Promise.resolve([]);
    return fetchJson(root.dataset.partsUrl + "?q=" + encodeURIComponent(q)).then(function (res) {
      partList.textContent = "";
      (res.body.parts || []).forEach(function (p) {
        formState.parts[p.code] = p;
        var o = document.createElement("option");
        o.value = p.code;
        o.label = p.name + (p.is_duplicate ? " (ambiguous)" : "");
        o.textContent = o.label;
        partList.appendChild(o);
      });
      return res.body.parts || [];
    });
  }

  // The component field searches Part Master too (confirmed against a real reference
  // screenshot: parent ABM01's components are part-mst rows like ABM01_001 "FLAT"),
  // not Item Master. Kept as "loadItems"/"rowItemCode" internally to limit the blast
  // radius of this fix, but the data source is now the same Part Master as the parent.
  function loadItems(q) {
    if (!q) return Promise.resolve([]);
    return fetchJson(root.dataset.partsUrl + "?q=" + encodeURIComponent(q)).then(function (res) {
      itemList.textContent = "";
      (res.body.parts || []).forEach(function (i) {
        formState.items[i.code] = i;
        var o = document.createElement("option");
        o.value = i.code;
        o.label = i.name + (i.is_duplicate ? " (ambiguous)" : "");
        o.textContent = o.label;
        itemList.appendChild(o);
      });
      return res.body.parts || [];
    });
  }

  // If the part picked in ADD mode already has a Bill of Material, show it immediately
  // (matches the same behavior added to the plain Bill of Material Master screen).
  // Never overwrites rows the user already added.
  function loadExistingComponentsIfAny(code) {
    if (formState.mode !== "add" || !code || formState.components.length) return;
    fetchJson(root.dataset.detailUrlTemplate.replace("__CODE__", encodeURIComponent(code))).then(function (res) {
      if (formState.mode !== "add" || formState.components.length) return;
      var rows = (res.body.components || []).map(function (c) {
        return { item_code: c.item_code, item_name: c.item_name || c.item_code, quantity: c.quantity, unit: c.unit };
      });
      if (!rows.length) return;
      formState.components = rows;
      renderGrid();
      formState.snapshot = snapshot();
    });
  }

  var partSearchTimer;
  partSearch.addEventListener("input", function () {
    var q = partSearch.value.trim();
    if (formState.parts[q.toUpperCase()]) {
      var hit = formState.parts[q.toUpperCase()];
      partCode.value = hit.code;
      partSearch.value = hit.name;
      return;
    }
    clearTimeout(partSearchTimer);
    partSearchTimer = setTimeout(function () { loadParts(q); }, 200);
  });
  partCode.addEventListener("change", function () {
    var code = partCode.value.trim().toUpperCase();
    partCode.value = code;
    loadParts(code).then(function (list) {
      var hit = list.find(function (p) { return p.code === code; });
      partSearch.value = hit ? hit.name : "";
    });
    loadExistingComponentsIfAny(code);
  });

  var itemSearchTimer;
  rowItemSearch.addEventListener("input", function () {
    var q = rowItemSearch.value.trim();
    if (formState.items[q.toUpperCase()]) {
      var cacheHit = formState.items[q.toUpperCase()];
      rowItemCode.value = cacheHit.code;
      rowItemSearch.value = cacheHit.name;
      rowUnit.value = cacheHit.unit || "";
      return;
    }
    clearTimeout(itemSearchTimer);
    itemSearchTimer = setTimeout(function () { loadItems(q); }, 200);
  });
  rowItemCode.addEventListener("change", function () {
    var code = rowItemCode.value.trim().toUpperCase();
    rowItemCode.value = code;
    loadItems(code).then(function (list) {
      var hit = list.find(function (i) { return i.code === code; });
      rowItemSearch.value = hit ? hit.name : "";
      rowUnit.value = hit ? (hit.unit || "") : "";
    });
  });

  // Universal Help/Lookup: focus a code field, press Enter, pick from a searchable grid.
  if (window.HelpLookup) {
    window.HelpLookup.attach(partCode, {
      endpoint: root.dataset.partsUrl,
      resultsKey: "parts",
      valueField: "code",
      filters: { sub_assembly: "1" },
      displayFields: [
        { key: "code", label: "Code" }, { key: "name", label: "Name" },
        { key: "sub_assembly", label: "Sub Assembly" },
      ],
      title: "Part",
      onSelect: function (row) {
        formState.parts[row.code] = row;
        partSearch.value = row.name;
        loadExistingComponentsIfAny(row.code);
      },
    });
    window.HelpLookup.attach(partSearch, {
      endpoint: root.dataset.partsUrl,
      resultsKey: "parts",
      valueField: "name",
      filters: { sub_assembly: "1" },
      displayFields: [
        { key: "code", label: "Code" }, { key: "name", label: "Name" },
        { key: "sub_assembly", label: "Sub Assembly" },
      ],
      title: "Part",
      onSelect: function (row) {
        formState.parts[row.code] = row;
        partCode.value = row.code;
        loadExistingComponentsIfAny(row.code);
      },
    });
    // Component field: Part Master too (see the loadItems comment above).
    window.HelpLookup.attach(rowItemCode, {
      endpoint: root.dataset.partsUrl,
      resultsKey: "parts",
      valueField: "code",
      displayFields: [
        { key: "code", label: "Code" }, { key: "name", label: "Name" },
        { key: "unit", label: "Unit" }, { key: "sub_assembly", label: "Sub Assembly" },
      ],
      title: "Part",
      onSelect: function (row) {
        formState.items[row.code] = row;
        rowItemSearch.value = row.name;
        rowUnit.value = row.unit || "";
      },
    });
    window.HelpLookup.attach(rowItemSearch, {
      endpoint: root.dataset.partsUrl,
      resultsKey: "parts",
      valueField: "name",
      displayFields: [
        { key: "code", label: "Code" }, { key: "name", label: "Name" },
        { key: "unit", label: "Unit" }, { key: "sub_assembly", label: "Sub Assembly" },
      ],
      title: "Part",
      onSelect: function (row) {
        formState.items[row.code] = row;
        rowItemCode.value = row.code;
        rowUnit.value = row.unit || "";
      },
    });
    // Unit: Enter opens a searchable Unit Help grid (same units as Part Master's own
    // unit list); Enter again on the highlighted unit fills it AND adds the row --
    // matching Qty's own Enter-to-add shortcut just below.
    window.HelpLookup.attach(rowUnit, {
      data: UNIT_OPTIONS,
      valueField: "value",
      displayFields: [{ key: "value", label: "Unit" }],
      title: "Unit",
      onSelect: function (row) {
        rowUnit.value = row.value;
        addRow();
      },
    });
  }

  function addRow() {
    rowError.textContent = "";
    var code = rowItemCode.value.trim().toUpperCase();
    var name = rowItemSearch.value.trim();
    var qtyRaw = rowQty.value.trim().replace(/,/g, "");
    var unitRaw = rowUnit.value.trim().toUpperCase().slice(0, 3);
    if (!code) { rowError.textContent = "Select a component."; return; }
    if (!/^\d*\.?\d+$/.test(qtyRaw) || Number(qtyRaw) <= 0) { rowError.textContent = "Enter a quantity more than 0."; return; }
    if (formState.components.some(function (r) { return r.item_code === code; })) {
      rowError.textContent = "Part " + code + " is already in the list.";
      return;
    }
    var newRow = { item_code: code, item_name: name || code, quantity: qtyRaw, unit: unitRaw };
    if (formState.editIndex > -1 && formState.editIndex <= formState.components.length) {
      formState.components.splice(formState.editIndex, 0, newRow);
    } else {
      formState.components.push(newRow);
    }
    formState.editIndex = -1;
    renderGrid();
    rowItemCode.value = "";
    rowItemSearch.value = "";
    rowQty.value = "";
    rowUnit.value = "";
    rowItemSearch.focus();
  }
  dialog.querySelector("[data-row-add]").addEventListener("click", addRow);
  rowQty.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); addRow(); } });

  var MODE_LABELS = { add: "Add", modify: "Modify", view: "View", "delete": "Delete" };

  function setMode(mode) {
    formState.mode = mode;
    dialog.dataset.mode = mode;
    dialog.querySelector("[data-mode-label]").textContent = MODE_LABELS[mode];
    var readOnly = mode === "view" || mode === "delete";
    partCode.readOnly = readOnly || mode === "modify";
    partSearch.readOnly = readOnly || mode === "modify";
    dialog.querySelector(".bom-add-row").hidden = readOnly;
    confirmBtn.hidden = mode === "view";
    confirmBtn.textContent = mode === "delete" ? "Delete" : "Confirm";
    confirmBtn.classList.toggle("btn--danger", mode === "delete");
    confirmBtn.classList.toggle("btn--primary", mode !== "delete");
  }

  function snapshot() {
    return JSON.stringify({ part_code: partCode.value, components: formState.components });
  }

  function isDirty() {
    return formState.mode !== "view" && formState.mode !== "delete" && snapshot() !== formState.snapshot;
  }

  function openForm(mode) {
    var parent = mode === "add" ? null : selectedParent();
    clearErrors();
    confirmBox.hidden = true;
    formState.parts = {};
    formState.items = {};
    formState.components = [];
    formState.selectedRow = -1;
    formState.editIndex = -1;
    setMode(mode);

    partCode.value = parent ? parent.part_code : "";
    partSearch.value = parent ? parent.part_name : "";
    if (parent) formState.parts[parent.part_code] = { code: parent.part_code, name: parent.part_name, is_duplicate: parent.is_duplicate };
    rowItemCode.value = "";
    rowItemSearch.value = "";
    rowQty.value = "";
    rowUnit.value = "";
    rowError.textContent = "";

    var ready = mode === "add" ? Promise.resolve() : fetchJson(root.dataset.detailUrlTemplate.replace("__CODE__", encodeURIComponent(parent.part_code)))
      .then(function (res) {
        formState.components = (res.body.components || []).map(function (c) {
          return { item_code: c.item_code, item_name: c.item_name || c.item_code, quantity: c.quantity, unit: c.unit };
        });
      });

    ready.then(function () {
      renderGrid();
      formState.snapshot = snapshot();
      dialog.showModal();
      (mode === "add" ? partSearch : mode === "delete" ? confirmBtn : rowItemSearch).focus();
    });
  }

  function ask(text, onYes) {
    confirmText.textContent = text;
    formState.afterConfirm = onYes;
    confirmBox.hidden = false;
    dialog.querySelector("[data-confirm-no]").focus();
  }
  dialog.querySelector("[data-confirm-yes]").addEventListener("click", function () {
    confirmBox.hidden = true;
    if (formState.afterConfirm) formState.afterConfirm();
  });
  dialog.querySelector("[data-confirm-no]").addEventListener("click", function () { confirmBox.hidden = true; });

  function save() {
    clearErrors();
    var code = partCode.value.trim().toUpperCase();
    if (!code) { showErrors({ part_code: "Select a part." }); return; }
    if (!formState.components.length) { alertBox.textContent = "Add at least one component."; alertBox.hidden = false; return; }

    confirmBtn.disabled = true;
    postJson(root.dataset.saveUrl, {
      part_code: code,
      components: formState.components.map(function (r) { return { item_code: r.item_code, quantity: r.quantity, unit: r.unit }; })
    }).then(function (res) {
      if (res.ok) {
        dialog.close();
        showToast(res.body.message);
        refresh(code);
      } else if (res.body.errors) {
        showErrors(res.body.errors);
      } else {
        alertBox.textContent = res.body.message || "Could not save (error " + res.status + ").";
        alertBox.hidden = false;
      }
    }).catch(function () {
      alertBox.textContent = "Could not reach the server. Nothing was saved.";
      alertBox.hidden = false;
    }).finally(function () {
      confirmBtn.disabled = false;
    });
  }

  function performDelete() {
    var parent = selectedParent();
    if (!parent) return;
    confirmBtn.disabled = true;
    postForm(root.dataset.deleteUrlTemplate.replace("__CODE__", encodeURIComponent(parent.part_code))).then(function (res) {
      if (res.ok) {
        dialog.close();
        showToast(res.body.message);
        state.selected = null;
        refresh();
      } else {
        alertBox.textContent = res.body.message || "Could not delete.";
        alertBox.hidden = false;
        confirmBtn.disabled = false;
      }
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (formState.mode === "delete") { ask("Are you sure you want to delete this record?", performDelete); return; }
    if (formState.mode === "view") return;
    ask("Are you sure?", save);
  });

  function requestExit() {
    dialog.close();
  }
  dialog.querySelectorAll("[data-form-exit]").forEach(function (b) { b.addEventListener("click", requestExit); });
  dialog.addEventListener("cancel", function (e) {
    e.preventDefault();
    if (!confirmBox.hidden) confirmBox.hidden = true;
    else requestExit();
  });

  /* --- Toolbar ------------------------------------------------------------------ */

  var actions = {
    add: function () { openForm("add"); },
    modify: function () { if (selectedParent()) openForm("modify"); },
    view: function () { if (selectedParent()) openForm("view"); },
    "delete": function () { if (selectedParent()) openForm("delete"); },
    exit: function () { window.location.href = root.dataset.exitUrl; }
  };
  root.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function () { actions[btn.dataset.action](); });
  });
  document.addEventListener("keydown", function (e) {
    if (!e.altKey || document.querySelector("dialog[open]")) return;
    var map = { a: "add", m: "modify", v: "view", d: "delete", e: "exit" };
    var btn = map[e.key.toLowerCase()] && root.querySelector('[data-action="' + map[e.key.toLowerCase()] + '"]');
    if (btn && !btn.disabled) { e.preventDefault(); btn.click(); }
  });

  render();
})();
