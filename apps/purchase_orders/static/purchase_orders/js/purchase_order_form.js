/* Purchase Order Master — shared Add / Modify / View form.
 * Exposes window.SPPurchaseOrderForm.open(mode, order).
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-po-master]");
  if (!root) return;

  var dialog = document.getElementById("po-form-dialog");
  var form = dialog.querySelector("[data-po-form]");
  var alertBox = dialog.querySelector("[data-form-alert]");
  var confirmBox = dialog.querySelector("[data-confirm-box]");
  var confirmText = dialog.querySelector("[data-confirm-text]");
  var confirmBtn = dialog.querySelector("[data-form-confirm]");

  var poNo = dialog.querySelector("#po-po_no");
  var orderDate = dialog.querySelector("#po-order_date");
  var partyCode = dialog.querySelector("#po-party_code");
  var partySearch = dialog.querySelector("[data-party-search]");
  var partyName = dialog.querySelector("[data-party-name]");
  var remarks = dialog.querySelector('[data-field="remarks"]');
  var payment = dialog.querySelector('[data-field="payment"]');
  var note = dialog.querySelector('[data-field="note"]');

  var rowPartCode = dialog.querySelector("[data-row-part-code]");
  var rowPartSearch = dialog.querySelector("[data-row-part-search]");
  var rowMaterial = dialog.querySelector("[data-row-material]");
  var rowDespatch = dialog.querySelector("[data-row-despatch]");
  var rowPoQty = dialog.querySelector("[data-row-po-qty]");
  var rowQty = dialog.querySelector("[data-row-qty]");
  var rowUnit = dialog.querySelector("[data-row-unit]");
  var rowDiscount = dialog.querySelector("[data-row-discount]");
  var rowHsn = dialog.querySelector("[data-row-hsn]");
  var rowRate = dialog.querySelector("[data-row-rate]");
  var rowSize = dialog.querySelector("[data-row-size]");
  var rowPacking = dialog.querySelector("[data-row-packing]");
  var rowLastRate = dialog.querySelector("[data-row-last-rate]");
  var rowCurrentStock = dialog.querySelector("[data-row-current-stock]");
  var rowParticulars = dialog.querySelector("[data-row-particulars]");
  var rowError = dialog.querySelector("[data-row-error]");
  var lineFieldset = dialog.querySelector("[data-line-fieldset]");

  var gridBody = dialog.querySelector("[data-grid-rows]");
  var gridEmpty = dialog.querySelector("[data-grid-empty]");
  var totalAmount = dialog.querySelector("[data-total-amount]");
  var totalGst = dialog.querySelector("[data-total-gst]");
  var totalDiscount = dialog.querySelector("[data-total-discount]");
  var totalNet = dialog.querySelector("[data-total-net]");

  var master = window.SPPurchaseOrderMaster;
  var formState = { mode: "add", key: null, lines: [], parties: {}, currentRef: null, snapshot: "", selectedRow: -1, editingIndex: -1 };

  function todayIso() {
    var d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  function money(v) { return Number(v || 0).toFixed(2); }
  function qtyFmt(v) { return Number(v || 0).toFixed(3); }

  var alertTimer;
  function showAlert(message) {
    alertBox.textContent = message;
    alertBox.hidden = false;
    clearTimeout(alertTimer);
    alertTimer = setTimeout(function () { alertBox.hidden = true; }, 6000);
  }

  function clearErrors() {
    alertBox.hidden = true;
    clearTimeout(alertTimer);
    form.querySelectorAll("[data-error-for]").forEach(function (el) { el.textContent = ""; });
    form.querySelectorAll(".mform__field.is-invalid").forEach(function (el) { el.classList.remove("is-invalid"); });
  }

  function showErrors(errors) {
    var generic = [];
    Object.keys(errors || {}).forEach(function (name) {
      var msg = errors[name];
      var target = form.querySelector('[data-error-for="' + name + '"]');
      if (target) {
        target.textContent = msg;
        target.closest(".mform__field").classList.add("is-invalid");
      } else {
        generic.push(msg);
      }
    });
    if (generic.length) showAlert(generic.join(" "));
  }

  function setPartyName(city) { partyName.textContent = city || ""; }

  /* --- Party Help ---------------------------------------------------------------- */

  if (window.HelpLookup) {
    var partyDisplayFields = [
      { key: "code", label: "Code" }, { key: "name", label: "Name" },
      { key: "city", label: "City" }, { key: "mobile", label: "Mobile" },
    ];
    window.HelpLookup.attach(partyCode, {
      endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "code",
      displayFields: partyDisplayFields, title: "Party",
      onSelect: function (row) {
        formState.parties[row.code] = row.name;
        partySearch.value = row.name;
        setPartyName(row.city);
        setTimeout(function () { rowPartSearch.focus(); if (rowPartSearch.select) rowPartSearch.select(); }, 0);
      },
    });
    window.HelpLookup.attach(partySearch, {
      endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
      displayFields: partyDisplayFields, title: "Party",
      onSelect: function (row) {
        formState.parties[row.code] = row.name;
        partyCode.value = row.code;
        setPartyName(row.city);
        // HelpLookup's own focusNext() runs right after this callback and would land on
        // Party Code (the next focusable field in DOM order) -- Party Code isn't part of
        // the Enter sequence, so override it once that default focus move has happened.
        setTimeout(function () { rowPartSearch.focus(); if (rowPartSearch.select) rowPartSearch.select(); }, 0);
      },
    });
    window.HelpLookup.attach(rowPartCode, {
      endpoint: root.dataset.partsUrl, resultsKey: "parts", valueField: "code",
      displayFields: [
        { key: "code", label: "Code" }, { key: "name", label: "Name" },
        { key: "material", label: "Material" }, { key: "gst_percent", label: "GST %" }, { key: "unit", label: "Unit" },
      ],
      title: "Part",
      onSelect: function (row) {
        rowPartSearch.value = row.name;
        fillPartReference(row.code);
        setTimeout(function () { rowMaterial.focus(); }, 0);
      },
    });
    window.HelpLookup.attach(rowPartSearch, {
      endpoint: root.dataset.partsUrl, resultsKey: "parts", valueField: "name",
      displayFields: [
        { key: "code", label: "Code" }, { key: "name", label: "Name" },
        { key: "material", label: "Material" }, { key: "gst_percent", label: "GST %" }, { key: "unit", label: "Unit" },
      ],
      title: "Part",
      onSelect: function (row) {
        rowPartCode.value = row.code;
        fillPartReference(row.code);
        setTimeout(function () { rowMaterial.focus(); }, 0);
      },
    });
  }

  partyCode.addEventListener("change", function () { partyCode.value = partyCode.value.trim().toUpperCase(); });
  rowPartCode.addEventListener("change", function () {
    rowPartCode.value = rowPartCode.value.trim().toUpperCase();
    if (rowPartCode.value) fillPartReference(rowPartCode.value);
  });

  /* --- Part reference (material / unit / gst / hsn / rate / last rate / stock) --- */

  function fillPartReference(code) {
    var url = root.dataset.partReferenceUrl + "?code=" + encodeURIComponent(code) + "&vendor=" + encodeURIComponent(partyCode.value.trim());
    return master.fetchJson(url).then(function (res) {
      if (!res.ok) { formState.currentRef = null; return; }
      var ref = res.body;
      formState.currentRef = ref;
      rowMaterial.value = ref.material || "";
      rowUnit.value = ref.unit || "";
      rowHsn.value = ref.hsn_code || "";
      rowRate.value = ref.rate || "0.00";
      rowSize.value = ref.size || "";
      rowPacking.value = ref.packing || 0;
      rowCurrentStock.value = ref.current_stock || "0.000";
      rowLastRate.value = ref.last_rate || "0.0000";
    });
  }

  /* --- Previous Info popup -------------------------------------------------------- */

  var previnfoDialog = document.getElementById("po-previnfo-dialog");
  if (previnfoDialog) {
    dialog.querySelector("[data-previous-info]").addEventListener("click", function () {
      var code = rowPartCode.value.trim().toUpperCase();
      if (!code) { rowError.textContent = "Select a part first to see its previous order history."; return; }
      rowError.textContent = "";
      var url = root.dataset.previousInfoUrlTemplate.replace("__CODE__", encodeURIComponent(code));
      master.fetchJson(url).then(function (res) {
        previnfoDialog.querySelector("[data-previnfo-part]").textContent = code;
        var rows = (res.body && res.body.history) || [];
        var tbody2 = previnfoDialog.querySelector("[data-previnfo-rows]");
        tbody2.textContent = "";
        rows.forEach(function (r) {
          var tr = document.createElement("tr");
          [master.dmy(r.date), (r.party_name || r.party_code), r.quantity, r.rate].forEach(function (v, i) {
            var td = document.createElement("td");
            if (i >= 2) td.className = "num";
            td.textContent = v;
            tr.appendChild(td);
          });
          tbody2.appendChild(tr);
        });
        previnfoDialog.querySelector("[data-previnfo-empty]").hidden = rows.length > 0;
        previnfoDialog.showModal();
      });
    });
    previnfoDialog.querySelectorAll("[data-previnfo-close]").forEach(function (btn) {
      btn.addEventListener("click", function () { previnfoDialog.close(); });
    });
  }

  /* --- Line grid ------------------------------------------------------------------ */

  function lineAmount(row) {
    var base = Number(row.quantity || 0) * Number(row.rate || 0);
    return base * (1 - Number(row.discount_percent || 0) / 100);
  }

  function computeTotals() {
    var amount = 0, gst = 0, discount = 0;
    formState.lines.forEach(function (row) {
      var base = Number(row.quantity || 0) * Number(row.rate || 0);
      var amt = lineAmount(row);
      amount += amt;
      discount += base - amt;
      gst += amt * Number(row.gst_percent || 0) / 100;
    });
    totalAmount.value = money(amount);
    totalGst.value = money(gst);
    totalDiscount.value = money(discount);
    totalNet.value = money(amount + gst);
  }

  function selectGridRow(index) {
    if (index < 0 || index >= formState.lines.length) index = -1;
    formState.selectedRow = index;
    gridBody.querySelectorAll("tr").forEach(function (tr, i) { tr.classList.toggle("is-selected", i === index); });
    if (index > -1) { var tr = gridBody.children[index]; if (tr) tr.focus(); }
  }

  function removeGridRow(index) {
    if (index < 0 || index >= formState.lines.length) return;
    formState.lines.splice(index, 1);
    if (formState.editingIndex === index) cancelEdit();
    else if (formState.editingIndex > index) formState.editingIndex -= 1;
    renderGrid();
    selectGridRow(Math.min(index, formState.lines.length - 1));
  }

  /* Load an existing grid row's values back into the entry fields above the grid so
     the user can edit them; clicking OK afterwards updates this row in place (by its
     index, not by part code/name -- several rows can share the same part) instead of
     appending a new one. */
  function loadRowForEdit(index) {
    if (formState.mode === "view" || index < 0 || index >= formState.lines.length) return;
    var row = formState.lines[index];
    formState.editingIndex = index;
    rowPartCode.value = row.part_code || "";
    rowPartSearch.value = row.part_name || "";
    rowMaterial.value = row.material || "";
    rowDespatch.value = window.DateMask.toDisplay(row.despatch_date || "");
    rowPoQty.value = row.po_qty || "";
    rowQty.value = row.quantity || "";
    rowUnit.value = row.unit || "";
    rowHsn.value = row.hsn_code || "";
    rowRate.value = row.rate || "";
    rowDiscount.value = row.discount_percent || "";
    rowSize.value = row.size || "";
    rowParticulars.value = row.particulars || "";
    formState.currentRef = { gst_percent: row.gst_percent || "0" };
    rowError.textContent = "";
    renderGrid();
    rowQty.focus();
    // Std Packing / Current Stock / Last Rate aren't stored on the line itself --
    // refresh them from the part reference without disturbing the fields above that
    // already carry this row's own saved values.
    var url = root.dataset.partReferenceUrl + "?code=" + encodeURIComponent(row.part_code) + "&vendor=" + encodeURIComponent(partyCode.value.trim());
    master.fetchJson(url).then(function (res) {
      if (!res.ok || formState.editingIndex !== index) return;
      var ref = res.body;
      rowPacking.value = ref.packing || 0;
      rowCurrentStock.value = ref.current_stock || "0.000";
      rowLastRate.value = ref.last_rate || "0.0000";
    });
  }

  function cancelEdit() {
    formState.editingIndex = -1;
    rowPartCode.value = ""; rowPartSearch.value = ""; rowMaterial.value = ""; rowDespatch.value = "";
    rowPoQty.value = ""; rowQty.value = ""; rowUnit.value = ""; rowHsn.value = ""; rowRate.value = "";
    rowDiscount.value = "";
    rowSize.value = ""; rowPacking.value = ""; rowLastRate.value = ""; rowCurrentStock.value = ""; rowParticulars.value = "";
    formState.currentRef = null;
    rowError.textContent = "";
    renderGrid();
  }

  function renderGrid() {
    gridBody.textContent = "";
    formState.lines.forEach(function (row, index) {
      var tr = document.createElement("tr");
      if (formState.mode !== "view") {
        tr.tabIndex = 0;
        tr.addEventListener("click", function () { selectGridRow(index); });
        tr.addEventListener("dblclick", function () { loadRowForEdit(index); });
        tr.addEventListener("keydown", function (e) {
          if (e.key === "ArrowDown") { e.preventDefault(); selectGridRow(index + 1); }
          else if (e.key === "ArrowUp") { e.preventDefault(); selectGridRow(index - 1); }
          else if (e.key === " " || e.key === "Spacebar") { e.preventDefault(); removeGridRow(index); }
          else if (e.key === "Enter") { e.preventDefault(); loadRowForEdit(index); }
        });
      }
      if (index === formState.editingIndex) tr.classList.add("is-editing");
      [
        [index + 1, "num"], [row.part_code], [row.part_name], [row.material],
        [master.dmy(row.despatch_date)], [qtyFmt(row.po_qty), "num"], [qtyFmt(row.quantity), "num"],
        [row.unit], [money(row.rate), "num"], [money(row.discount_percent), "num"], [money(lineAmount(row)), "num"],
      ].forEach(function (pair) {
        var td = document.createElement("td");
        if (pair[1]) td.className = pair[1];
        td.textContent = pair[0];
        tr.appendChild(td);
      });
      gridBody.appendChild(tr);
    });
    gridEmpty.hidden = formState.lines.length > 0;
    computeTotals();
  }

  function addRow() {
    rowError.textContent = "";
    var code = rowPartCode.value.trim().toUpperCase();
    var name = rowPartSearch.value.trim();
    var poQty = rowPoQty.value.trim().replace(/,/g, "");
    var qty = (rowQty.value.trim() || rowPoQty.value.trim()).replace(/,/g, "");
    if (!code) { rowError.textContent = "Select a part."; return; }
    if (!/^\d*\.?\d+$/.test(poQty) || Number(poQty) <= 0) { rowError.textContent = "Enter a P.O. quantity more than 0."; return; }
    if (formState.lines.some(function (r, i) { return r.part_code === code && i !== formState.editingIndex; })) {
      rowError.textContent = "Part " + code + " is already in the list.";
      return;
    }
    var line = {
      part_code: code, part_name: name || code, material: rowMaterial.value,
      despatch_date: window.DateMask.toIso(rowDespatch.value), po_qty: poQty, quantity: qty || poQty,
      unit: rowUnit.value, hsn_code: rowHsn.value, rate: rowRate.value.trim().replace(/,/g, "") || "0",
      discount_percent: rowDiscount.value.trim().replace(/,/g, "") || "0",
      size: rowSize.value, particulars: rowParticulars.value.trim(),
      gst_percent: formState.currentRef ? formState.currentRef.gst_percent : "0",
    };
    if (formState.editingIndex > -1) formState.lines[formState.editingIndex] = line;
    else formState.lines.push(line);
    formState.editingIndex = -1;
    renderGrid();
    rowPartCode.value = ""; rowPartSearch.value = ""; rowMaterial.value = ""; rowDespatch.value = "";
    rowPoQty.value = ""; rowQty.value = ""; rowUnit.value = ""; rowHsn.value = ""; rowRate.value = "";
    rowDiscount.value = "";
    rowSize.value = ""; rowPacking.value = ""; rowLastRate.value = ""; rowCurrentStock.value = ""; rowParticulars.value = "";
    formState.currentRef = null;
    rowPartSearch.focus();
  }
  var rowAddBtn = dialog.querySelector("[data-row-add]");
  rowAddBtn.addEventListener("click", addRow);
  rowPoQty.addEventListener("input", function () { if (!rowQty.value.trim()) rowQty.value = rowPoQty.value; });
  lineFieldset.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && formState.editingIndex > -1) { e.preventDefault(); cancelEdit(); }
  });

  /* --- Keyboard focus sequence (Enter advances field-by-field) -------------------- */

  /* Plain "Enter moves to the next field" wiring -- NOT used on fields that already
     have their own HelpLookup Enter handler (party search, part search), since those
     open a popup first and advance focus themselves via onSelect once a row is picked. */
  function onEnterGo(field, next) {
    field.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      e.preventDefault();
      var target = typeof next === "function" ? next() : next;
      if (target) { target.focus(); if (target.select) target.select(); }
    });
  }

  onEnterGo(orderDate, partySearch);
  onEnterGo(rowMaterial, rowDespatch);
  onEnterGo(rowDespatch, rowPoQty);
  onEnterGo(rowPoQty, function () {
    var poQty = rowPoQty.value.trim().replace(/,/g, "");
    if (!/^\d*\.?\d+$/.test(poQty) || Number(poQty) <= 0) {
      rowError.textContent = "Enter a P.O. quantity more than 0.";
      return null;
    }
    rowError.textContent = "";
    return rowQty;
  });
  onEnterGo(rowQty, rowSize);
  onEnterGo(rowSize, rowDiscount);
  onEnterGo(rowDiscount, rowRate);
  onEnterGo(rowRate, rowAddBtn);

  /* Fields intentionally left out of the Enter sequence (auto-filled / mouse-only) --
     just stop Enter there from submitting the form, same as every sequenced field. */
  [rowUnit, rowHsn, rowPacking, rowCurrentStock, rowLastRate, partyCode, poNo].forEach(function (field) {
    field.addEventListener("keydown", function (e) { if (e.key === "Enter") e.preventDefault(); });
  });

  /* --- Mode / open / save ---------------------------------------------------------- */

  function setMode(mode) {
    formState.mode = mode;
    dialog.dataset.mode = mode;
    dialog.querySelector("[data-mode-label]").textContent = mode === "add" ? "Add" : mode === "modify" ? "Modify" : "View";
    var readOnly = mode === "view";
    orderDate.readOnly = readOnly;
    partyCode.readOnly = readOnly;
    partySearch.readOnly = readOnly;
    remarks.readOnly = readOnly;
    payment.readOnly = readOnly;
    note.readOnly = readOnly;
    lineFieldset.hidden = readOnly;
    confirmBtn.hidden = readOnly;
  }

  function snapshot() {
    return JSON.stringify({ party_code: partyCode.value, order_date: orderDate.value, lines: formState.lines });
  }

  function open(mode, order) {
    formState.key = order ? [order.div, order.po_no] : null;
    formState.lines = [];
    formState.selectedRow = -1;
    formState.editingIndex = -1;
    formState.currentRef = null;
    clearErrors();
    confirmBox.hidden = true;
    setMode(mode);

    poNo.value = order ? order.po_no : "";
    orderDate.value = window.DateMask.toDisplay(order ? order.order_date : todayIso());
    partyCode.value = order ? order.party_code : "";
    partySearch.value = order ? (order.party_name || "") : "";
    setPartyName(order ? order.city : "");
    remarks.value = "";
    payment.value = "";
    note.value = "";
    rowPartCode.value = ""; rowPartSearch.value = ""; rowMaterial.value = ""; rowDespatch.value = "";
    rowPoQty.value = ""; rowQty.value = ""; rowUnit.value = ""; rowHsn.value = ""; rowRate.value = "";
    rowDiscount.value = "";
    rowSize.value = ""; rowPacking.value = ""; rowLastRate.value = ""; rowCurrentStock.value = ""; rowParticulars.value = "";
    rowError.textContent = "";

    var ready = !order
      ? Promise.resolve()
      : master.fetchJson(root.dataset.detailUrlTemplate.replace("__DIV__", encodeURIComponent(order.div)).replace("__PONO__", encodeURIComponent(order.po_no)))
        .then(function (res) {
          if (!res.ok) return;
          remarks.value = res.body.remarks || "";
          payment.value = res.body.payment || "";
          note.value = res.body.note || "";
          formState.lines = (res.body.lines || []).map(function (l) {
            return {
              part_code: l.part_code, part_name: l.part_name, material: l.material,
              despatch_date: l.despatch_date, po_qty: l.po_qty, quantity: l.quantity,
              unit: l.unit, hsn_code: l.hsn_code, rate: l.rate, discount_percent: l.discount_percent, size: l.size,
              particulars: l.particulars || "", gst_percent: l.gst_percent || "0",
            };
          });
        });

    ready.then(function () {
      renderGrid();
      formState.snapshot = snapshot();
      dialog.showModal();
      (mode === "add" ? orderDate : dialog.querySelector(".modal__footer [data-form-exit]")).focus();
    });
  }

  function isDirty() { return formState.mode !== "view" && snapshot() !== formState.snapshot; }

  function ask(text, onYes) {
    confirmText.textContent = text;
    confirmBox.hidden = false;
    formState.afterConfirm = onYes;
    confirmBox.querySelector("[data-confirm-no]").focus();
  }
  confirmBox.querySelector("[data-confirm-yes]").addEventListener("click", function () {
    confirmBox.hidden = true;
    if (formState.afterConfirm) formState.afterConfirm();
  });
  confirmBox.querySelector("[data-confirm-no]").addEventListener("click", function () { confirmBox.hidden = true; });

  function save() {
    var payload = {
      div: formState.key ? formState.key[0] : "SP",
      party_code: partyCode.value.trim().toUpperCase(),
      order_date: window.DateMask.toIso(orderDate.value),
      remarks: remarks.value,
      payment: payment.value,
      note: note.value,
      lines: formState.lines,
      key: formState.key ? formState.key.join("|") : "",
    };
    master.postJson(root.dataset.saveUrl, payload).then(function (res) {
      if (res.ok) {
        dialog.close();
        master.showToast(res.body.message);
        master.refresh(res.body.key);
      } else if (res.body.errors) {
        showErrors(res.body.errors);
      } else {
        showAlert(res.body.message || "Could not save (error " + res.status + ").");
      }
    }).catch(function () {
      showAlert("Could not reach the server. Nothing was saved.");
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    clearErrors();
    if (!partyCode.value.trim()) { showErrors({ party_code: "Select a party." }); return; }
    if (!formState.lines.length) { showAlert("Add at least one item."); return; }
    ask("Are you sure?", save);
  });

  function requestExit() { dialog.close(); }
  dialog.querySelectorAll("[data-form-exit]").forEach(function (btn) { btn.addEventListener("click", requestExit); });
  dialog.addEventListener("cancel", function (e) {
    e.preventDefault();
    if (!confirmBox.hidden) confirmBox.hidden = true;
    else requestExit();
  });

  window.SPPurchaseOrderForm = { open: open };
})();
