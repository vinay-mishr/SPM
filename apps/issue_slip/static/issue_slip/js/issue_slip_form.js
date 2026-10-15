/* Single Issue Slip — shared Add / Modify / View form, matching the supplied
   reference layout. Exposes window.SPIssueSlipForm.open(mode, row). */
(function () {
  "use strict";

  var root = document.querySelector("[data-issue-slip-entry]");
  if (!root) return;

  var dialog = document.getElementById("mis-form-dialog");
  var form = dialog.querySelector("[data-mis-form]");
  var alertBox = dialog.querySelector("[data-form-alert]");
  var confirmBox = dialog.querySelector("[data-confirm-box]");
  var confirmText = dialog.querySelector("[data-confirm-text]");

  var misNo = dialog.querySelector("#mis-mis_no");
  var misDate = dialog.querySelector("#mis-mis_date");
  var unameInput = dialog.querySelector("#mis-uname");
  var remarks = dialog.querySelector("#mis-remarks");

  var rowPartSearch = dialog.querySelector("[data-row-part-search]");
  var rowQty = dialog.querySelector("[data-row-qty]");
  var rowRemarks = dialog.querySelector("[data-row-remarks]");
  var rowError = dialog.querySelector("[data-row-error]");
  var lineFieldset = dialog.querySelector("[data-line-fieldset]");
  var partCode = ""; // resolved from the part-search HelpLookup selection, not a visible field

  var gridBody = dialog.querySelector("[data-grid-rows]");

  var entry = window.SPIssueSlipEntry;
  var formState = { mode: "add", key: null, lines: [], editingIndex: -1, snapshot: "", afterConfirm: null, afterDecline: null };

  function n(v) { return parseFloat(v) || 0; }
  function qtyFmt(v) { return n(v).toFixed(3); }

  function clearErrors() {
    alertBox.hidden = true;
    form.querySelectorAll("[data-error-for]").forEach(function (el) { el.textContent = ""; });
  }

  function showErrors(errors) {
    var generic = [];
    Object.keys(errors || {}).forEach(function (name) {
      var msg = errors[name];
      var target = form.querySelector('[data-error-for="' + name + '"]');
      if (target) target.textContent = msg; else generic.push(msg);
    });
    if (generic.length) { alertBox.textContent = generic.join(" "); alertBox.hidden = false; }
  }

  /* --- Item help lookup -------------------------------------------------------- */

  if (window.HelpLookup) {
    window.HelpLookup.attach(rowPartSearch, {
      endpoint: root.dataset.partsUrl, resultsKey: "parts", valueField: "name",
      displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "material", label: "Material" }, { key: "gst_percent", label: "GST %" }],
      title: "Item",
      onSelect: function (row) { partCode = row.code; focusField(rowQty); },
    });
  }

  /* --- Grid --------------------------------------------------------------------- */

  function renderGrid() {
    gridBody.textContent = "";
    if (!formState.lines.length) {
      gridBody.innerHTML = '<tr class="empty" data-grid-empty><td colspan="5">No items added yet. Press Space on a row to remove it, double-click to edit.</td></tr>';
      return;
    }
    formState.lines.forEach(function (row, index) {
      var tr = document.createElement("tr");
      tr.tabIndex = 0;
      if (index === formState.editingIndex) tr.classList.add("is-editing");
      if (formState.mode !== "view") {
        tr.addEventListener("dblclick", function () { loadRowForEdit(index); });
        tr.addEventListener("keydown", function (e) {
          if (e.key === " " || e.key === "Spacebar") { e.preventDefault(); removeGridRow(index); }
        });
      }
      [
        [index + 1], [row.part_code], [row.part_name],
        [qtyFmt(row.qty_issued), "num"], [row.remarks],
      ].forEach(function (pair) {
        var td = document.createElement("td");
        if (pair[1]) td.className = pair[1];
        td.textContent = pair[0];
        tr.appendChild(td);
      });
      gridBody.appendChild(tr);
    });
  }

  function removeGridRow(index) {
    formState.lines.splice(index, 1);
    if (formState.editingIndex === index) cancelEdit(); else renderGrid();
  }

  function loadRowForEdit(index) {
    if (formState.mode === "view") return;
    var row = formState.lines[index];
    formState.editingIndex = index;
    partCode = row.part_code;
    rowPartSearch.value = row.part_name;
    rowQty.value = row.qty_issued;
    rowRemarks.value = row.remarks;
    renderGrid();
    rowPartSearch.focus();
  }

  function cancelEdit() {
    formState.editingIndex = -1;
    partCode = "";
    rowPartSearch.value = ""; rowQty.value = ""; rowRemarks.value = "";
    rowError.textContent = "";
    renderGrid();
  }

  /* data-row-add's own click handler is the ONLY place a row is ever added --
   * the Enter-navigation handler below explicitly ignores the OK button (it's
   * a <button>, not an input/select), so Enter-to-click and a direct mouse
   * click can never both fire for the same press and add the row twice. */
  dialog.querySelector("[data-row-add]").addEventListener("click", function () {
    rowError.textContent = "";
    if (!partCode) { rowError.textContent = "Select an item."; return; }
    var qty = rowQty.value.trim();
    if (n(qty) <= 0) { rowError.textContent = "Enter a quantity issued more than 0."; return; }
    var line = {
      part_code: partCode, part_name: rowPartSearch.value.trim() || partCode,
      qty_issued: qty, remarks: rowRemarks.value.trim(),
    };
    if (formState.editingIndex > -1) formState.lines[formState.editingIndex] = line;
    else formState.lines.push(line);
    formState.editingIndex = -1;
    cancelEdit();
    rowPartSearch.focus();
  });

  lineFieldset.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && formState.editingIndex > -1) { e.preventDefault(); cancelEdit(); }
  });

  /* --- Enter-key focus sequence --------------------------------------------------
   * CHALLAN NO -> DATE -> ITEM DESCRIPTION -> QTY ISSUED -> REMARKS -> OK, same
   * centralized-handler convention as the MRN Entry form. ITEM DESCRIPTION has
   * HelpLookup attached, which intercepts Enter on that field itself (and calls
   * stopPropagation()) to open its popup instead of just advancing focus; after
   * a selection there, onSelect above moves straight to QTY ISSUED. */
  var HEADER_ORDER = [misNo, misDate];
  var ITEM_ORDER = [rowPartSearch, rowQty, rowRemarks];

  function focusField(el) {
    el.focus();
    if (el.select) el.select();
  }

  function handleEnter(event) {
    var tag = event.target.tagName;
    if (event.key !== "Enter" || tag !== "INPUT") return;
    event.preventDefault();

    var fromHeader = HEADER_ORDER.indexOf(event.target);
    if (fromHeader > -1) {
      if (fromHeader < HEADER_ORDER.length - 1) focusField(HEADER_ORDER[fromHeader + 1]);
      else if (!lineFieldset.hidden) focusField(rowPartSearch); // DATE -> ITEM DESCRIPTION
      return;
    }

    var fromItem = ITEM_ORDER.indexOf(event.target);
    if (fromItem > -1) {
      if (fromItem < ITEM_ORDER.length - 1) focusField(ITEM_ORDER[fromItem + 1]);
      else dialog.querySelector("[data-row-add]").focus(); // REMARKS -> OK
    }
  }
  form.addEventListener("keydown", handleEnter);

  /* --- Mode / open / save ----------------------------------------------------------- */

  function setMode(mode) {
    formState.mode = mode;
    dialog.dataset.mode = mode;
    dialog.querySelector("[data-mode-label]").textContent = mode;
    var readOnly = mode === "view";
    misDate.disabled = readOnly;
    remarks.disabled = readOnly;
    lineFieldset.hidden = readOnly;
    dialog.querySelector("[data-form-confirm]").hidden = readOnly;
  }

  function snapshot() { return JSON.stringify({ mis_date: misDate.value, lines: formState.lines }); }

  function open(mode, row) {
    formState.key = row ? row.mis_no : null;
    formState.lines = []; formState.editingIndex = -1;
    clearErrors();
    confirmBox.hidden = true;
    setMode(mode);

    misDate.value = window.DateMask.toDisplay(row ? row.mis_date : new Date().toISOString().slice(0, 10));
    remarks.value = "";
    cancelEdit();

    var ready = !row
      ? entry.fetchJson(root.dataset.nextNoUrl).then(function (res) { misNo.value = res.ok ? res.body.mis_no : "Auto"; })
      : entry.fetchJson(root.dataset.detailUrlTemplate.replace("__MISNO__", encodeURIComponent(row.mis_no)))
        .then(function (res) {
          if (!res.ok) return;
          misNo.value = res.body.mis_no;
          unameInput.value = res.body.uname || "";
          remarks.value = res.body.remarks || "";
          formState.lines = res.body.items || [];
        });

    ready.then(function () {
      renderGrid();
      formState.snapshot = snapshot();
      dialog.showModal();
      focusField(mode === "add" ? misNo : rowPartSearch);
    });
  }

  function ask(text, onYes, onNo) {
    confirmText.textContent = text;
    confirmBox.hidden = false;
    formState.afterConfirm = onYes;
    formState.afterDecline = onNo;
  }
  dialog.querySelector("[data-form-confirm-yes]").addEventListener("click", function () {
    confirmBox.hidden = true;
    if (formState.afterConfirm) formState.afterConfirm();
  });
  dialog.querySelector("[data-confirm-no]").addEventListener("click", function () {
    confirmBox.hidden = true;
    if (formState.afterDecline) formState.afterDecline();
  });

  function save() {
    var payload = {
      mis_date: window.DateMask.toIso(misDate.value),
      remarks: remarks.value,
      items: formState.lines,
      key: formState.key || "",
    };
    entry.postJson(root.dataset.saveUrl, payload).then(function (res) {
      if (res.ok) {
        dialog.close();
        entry.showToast(res.body.message);
        entry.refresh(res.body.mis_no);
      } else if (res.body.errors) {
        showErrors(res.body.errors);
      } else {
        alertBox.textContent = res.body.message || "Could not save (error " + res.status + ").";
        alertBox.hidden = false;
      }
    }).catch(function () {
      alertBox.textContent = "Could not reach the server. Nothing was saved.";
      alertBox.hidden = false;
    });
  }

  dialog.querySelector("[data-form-confirm]").addEventListener("click", function () {
    clearErrors();
    if (!misNo.value.trim()) { showErrors({ mis_no: "Challan no is missing." }); return; }
    if (!window.DateMask.toIso(misDate.value)) { showErrors({ mis_date: "Enter a valid date." }); return; }
    if (!formState.lines.length) { alertBox.textContent = "Add at least one item."; alertBox.hidden = false; return; }
    ask("Are you sure?", save);
  });

  dialog.querySelectorAll("[data-form-exit]").forEach(function (btn) { btn.addEventListener("click", function () { dialog.close(); }); });
  dialog.addEventListener("cancel", function (e) {
    e.preventDefault();
    if (!confirmBox.hidden) confirmBox.hidden = true; else dialog.close();
  });

  window.SPIssueSlipForm = { open: open };
})();
