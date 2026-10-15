/* GST Returnable Challan form: Add / Modify / View. Old VFP: chl7.SCT (rpldata, caltotal). */
(function () {
  "use strict";

  var root = document.querySelector("[data-challan-entry]");
  var dialog = document.getElementById("ch-form-dialog");
  if (!root || !dialog) return;

  var form = dialog.querySelector("[data-ch-form]");
  var alertBox = dialog.querySelector("[data-form-alert]");
  var modeLabel = dialog.querySelector("[data-mode-label]");
  var gridBody = dialog.querySelector("[data-grid-rows]");
  var amountField = document.getElementById("ch-amount");
  var gstAmtField = document.getElementById("ch-gst-amt");
  var netField = document.getElementById("ch-net");
  var netRoundedField = document.getElementById("ch-net-rounded");
  var partySearch = dialog.querySelector("[data-party-search]");
  var partyName = dialog.querySelector("[data-party-name]");
  var confirmBox = dialog.querySelector("[data-confirm-box]");
  var confirmText = dialog.querySelector("[data-confirm-text]");
  var rowPart = dialog.querySelector("[data-row-part-search]");
  var rowHsn = dialog.querySelector("[data-row-hsn]");
  var rowUnit = dialog.querySelector("[data-row-unit]");
  var rowQty = dialog.querySelector("[data-row-qty]");
  var rowRate = dialog.querySelector("[data-row-rate]");
  var rowParticular = dialog.querySelector("[data-row-particular]");
  var rowError = dialog.querySelector("[data-row-error]");
  var cityInput = dialog.querySelector("[data-party-city]");
  var phoneInput = field("phone");
  var chlDateInput = field("chl_date");

  /* Keyboard focus order (per spec): Date -> Party Name -> City -> Phone No. ->
     Item Name -> HSN Code -> Unit -> Qty -> Rate -> OK (then back to Item Name).
     Matches the existing DOM order already, so plain Tab / Shift+Tab already visits
     every field in this order; only Enter needs wiring to advance the same way. */
  function onEnterFocus(el, next) {
    el.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      e.preventDefault();
      if (!next) return;
      next.focus();
      if (next.select) next.select();
    });
  }

  var state = { mode: "add", key: null, items: [], editIndex: -1, readOnly: false, pendingAction: null };

  function field(name) { return form.querySelector('[data-field="' + name + '"]'); }
  function iso(value) { return window.DateMask.toIso(value || ""); }
  function display(value) { return window.DateMask.toDisplay(value || ""); }

  function setAlert(message) {
    alertBox.textContent = message || "";
    alertBox.hidden = !message;
  }

  function money(n) { return (Math.round((Number(n) || 0) * 100) / 100).toFixed(2); }

  function rowAmount(qty, rate) { return money((Number(qty) || 0) * (Number(rate) || 0)); }

  function lineGst(it) { return (Number(it.amount) || 0) * (Number(it.gst_percent) || 0) / 100; }

  function totals() {
    var amount = 0, gst = 0;
    state.items.forEach(function (it) { amount += Number(it.amount) || 0; gst += lineGst(it); });
    return { amount: amount, gst: gst, net: amount + gst };
  }

  function renderGrid() {
    gridBody.textContent = "";
    if (!state.items.length) {
      var tr = document.createElement("tr");
      tr.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 9;
      td.textContent = "No items added yet.";
      tr.appendChild(td);
      gridBody.appendChild(tr);
    }
    state.items.forEach(function (it, index) {
      var tr = document.createElement("tr");
      tr.tabIndex = state.readOnly ? -1 : 0;
      tr.dataset.index = index;
      if (index === state.editIndex) tr.classList.add("is-editing");
      var values = [index + 1, it.part_code, it.part_name, it.hsn_code, Number(it.qty).toFixed(3), it.unit,
        money(it.rate), money(it.amount), money(it.gst_percent)];
      values.forEach(function (v, i) {
        var cellEl = document.createElement("td");
        cellEl.textContent = v == null ? "" : v;
        if (i === 4 || i === 6 || i === 7 || i === 8) cellEl.className = "num";
        tr.appendChild(cellEl);
      });
      gridBody.appendChild(tr);
    });
    var t = totals();
    amountField.value = money(t.amount);
    gstAmtField.value = money(t.gst);
    netField.value = money(t.net);
    netRoundedField.value = Math.round(t.net);
  }

  function clearRow() {
    rowPart.value = "";
    rowHsn.value = "";
    rowUnit.value = "";
    rowQty.value = "";
    rowRate.value = "";
    rowParticular.value = "";
    rowError.textContent = "";
    state.editIndex = -1;
    rowPart.dataset.code = "";
  }

  function fillRowFromPart(code) {
    return window.SPChallanEntry.fetchJson(root.dataset.partReferenceUrl + "?code=" + encodeURIComponent(code))
      .then(function (res) {
        if (!res.ok) { rowError.textContent = res.body.message || "Item not found."; return; }
        rowPart.dataset.code = res.body.part_code;
        rowPart.dataset.gst = res.body.gst_percent || "0";
        rowPart.value = res.body.description || res.body.part_code;
        rowHsn.value = res.body.hsn_code || "";
        rowUnit.value = res.body.unit || "";
        rowRate.value = res.body.rate || "";
        rowError.textContent = "";
        rowHsn.focus();
      });
  }

  function addRow() {
    var code = rowPart.dataset.code || "";
    var qty = Number(rowQty.value);
    var rate = Number(rowRate.value || 0);
    if (!code) { rowError.textContent = "Select an item."; return; }
    if (!(qty > 0)) { rowError.textContent = "Qty must be greater than zero."; return; }
    if (rate < 0) { rowError.textContent = "Rate cannot be negative."; return; }
    var item = {
      part_code: code, part_name: rowPart.value, hsn_code: rowHsn.value.trim(),
      unit: rowUnit.value, qty: qty.toFixed(3), rate: rate.toFixed(2),
      amount: rowAmount(qty, rate), gst_percent: rowPart.dataset.gst || "0",
      particular: rowParticular.value.trim(),
    };
    if (state.editIndex >= 0) state.items[state.editIndex] = item;
    else state.items.push(item);
    clearRow();
    renderGrid();
    rowPart.focus();
  }

  dialog.querySelector("[data-row-add]").addEventListener("click", addRow);
  // HSN -> Unit -> Qty -> Rate -> OK; only Rate's Enter (and Particular's, kept as
  // the pre-existing shortcut) actually adds the row -- the others just advance.
  onEnterFocus(rowHsn, rowUnit);
  onEnterFocus(rowUnit, rowQty);
  onEnterFocus(rowQty, rowRate);
  [rowRate, rowParticular].forEach(function (el) {
    el.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); addRow(); } });
  });

  window.HelpLookup.attach(rowPart, {
    endpoint: root.dataset.partsUrl, resultsKey: "parts", valueField: "code",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "unit", label: "Unit" }],
    title: "Item",
    onSelect: function (row) { fillRowFromPart(row.code); },
  });

  window.HelpLookup.attach(partySearch, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Party",
    onSelect: function (row) {
      field("party_code").value = row.code;
      partyName.value = row.name;
      cityInput.value = row.city || "";
      if (row.mobile && !field("phone").value) field("phone").value = row.mobile;
      cityInput.focus();
    },
  });

  onEnterFocus(chlDateInput, partySearch);
  onEnterFocus(cityInput, phoneInput);
  onEnterFocus(phoneInput, rowPart);

  gridBody.addEventListener("dblclick", function (e) {
    var tr = e.target.closest("tr[data-index]");
    if (!tr || state.readOnly) return;
    var it = state.items[Number(tr.dataset.index)];
    state.editIndex = Number(tr.dataset.index);
    rowPart.dataset.code = it.part_code;
    rowPart.dataset.gst = it.gst_percent || "0";
    rowPart.value = it.part_name;
    rowHsn.value = it.hsn_code;
    rowUnit.value = it.unit;
    rowQty.value = it.qty;
    rowRate.value = it.rate;
    rowParticular.value = it.particular;
    renderGrid();
    rowQty.focus();
  });

  gridBody.addEventListener("keydown", function (e) {
    var tr = e.target.closest("tr[data-index]");
    if (!tr || state.readOnly) return;
    if (e.key === " " || e.key === "Delete") {
      e.preventDefault();
      state.items.splice(Number(tr.dataset.index), 1);
      state.editIndex = -1;
      renderGrid();
    }
  });

  function resetForm() {
    form.reset();
    setAlert("");
    state.items = [];
    state.editIndex = -1;
    clearRow();
    renderGrid();
    partyName.value = "";
    partySearch.value = "";
    field("party_code").value = "";
    dialog.querySelectorAll("[data-form-save], [data-form-confirm]").forEach(function (b) { b.hidden = false; });
    form.querySelectorAll("input, textarea").forEach(function (el) { el.readOnly = false; });
    state.readOnly = false;
    rowPart.readOnly = false;
  }

  function fillForm(data) {
    field("chl_no").value = data.chl_no || "";
    field("chl_date").value = display(data.chl_date);
    field("ord_no").value = data.ord_no || "";
    field("ord_date").value = display(data.ord_date);
    field("party_code").value = data.party_code || "";
    partyName.value = data.party_name || "";
    field("phone").value = data.phone || "";
    field("mode").value = data.mode || "";
    field("check_order").value = data.check_order === "Y" ? "Y" : "N";
    field("vehicle_no").value = data.vehicle_no || "";
    field("supply_date").value = display(data.supply_date);
    field("supply_time").value = data.supply_time || "";
    field("place_of_supply").value = data.place_of_supply || "";
    field("remarks").value = data.particulars || "";
    state.items = (data.items || []).map(function (it) {
      return { part_code: it.part_code, part_name: it.part_name, hsn_code: it.hsn_code, unit: it.unit,
        qty: it.qty, rate: it.rate, amount: it.amount, gst_percent: it.gst_percent, particular: it.particular };
    });
    renderGrid();
  }

  function setReadOnly(on) {
    state.readOnly = on;
    form.querySelectorAll("input, textarea").forEach(function (el) {
      if (el.id === "ch-net") return;
      el.readOnly = on;
    });
    rowPart.readOnly = on;
    dialog.querySelectorAll("[data-form-save], [data-form-confirm], [data-row-add]").forEach(function (b) { b.hidden = on; });
  }

  function open(mode, row) {
    resetForm();
    state.mode = mode;
    state.key = row ? row.key : null;
    modeLabel.textContent = mode === "add" ? "Add" : mode === "modify" ? "Modify" : "View";
    if (mode === "add") {
      window.SPChallanEntry.fetchJson(root.dataset.nextNoUrl).then(function (res) {
        var now = new Date();
        var pad = function (n) { return String(n).padStart(2, "0"); };
        field("chl_no").value = res.body.chl_no || "";
        field("chl_date").value = pad(now.getDate()) + "/" + pad(now.getMonth() + 1) + "/" + now.getFullYear();
      });
      dialog.showModal();
      field("chl_date").focus();
      return;
    }
    window.SPChallanEntry.fetchJson(root.dataset.detailUrlTemplate.replace("__CHLNO__", encodeURIComponent(row.key)))
      .then(function (res) {
        if (!res.ok) { window.SPChallanEntry.showToast(res.body.message || "Could not open challan.", "error"); return; }
        fillForm(res.body);
        setReadOnly(mode === "view");
        dialog.showModal();
      });
  }

  function payload() {
    return {
      key: state.mode === "modify" ? state.key : null,
      chl_no: field("chl_no").value.trim(),
      chl_date: iso(field("chl_date").value),
      ord_no: field("ord_no").value.trim(),
      ord_date: iso(field("ord_date").value),
      party_code: field("party_code").value.trim(),
      phone: field("phone").value.trim(),
      mode: field("mode").value.trim(),
      check_order: field("check_order").value,
      vehicle_no: field("vehicle_no").value.trim(),
      supply_date: iso(field("supply_date").value),
      supply_time: field("supply_time").value.trim(),
      place_of_supply: field("place_of_supply").value.trim(),
      particulars: field("remarks").value.trim(),
      items: state.items.map(function (it) {
        return { part_code: it.part_code, hsn_code: it.hsn_code, qty: it.qty, rate: it.rate, particular: it.particular };
      }),
    };
  }

  function save() {
    if (!state.items.length) { setAlert("Add at least one item."); return; }
    setAlert("");
    window.SPChallanEntry.postJson(root.dataset.saveUrl, payload()).then(function (res) {
      if (!res.ok) {
        var errs = res.body.errors || {};
        var first = Object.keys(errs)[0];
        setAlert(res.body.message || "Could not save.");
        if (first && field(first)) field(first).focus();
        return;
      }
      dialog.close();
      window.SPChallanEntry.showToast(res.body.message || "Saved.");
      window.SPChallanEntry.refresh(res.body.chl_no);
    });
  }

  function askConfirm(text, onYes) {
    confirmText.textContent = text;
    confirmBox.hidden = false;
    state.pendingAction = onYes;
    confirmBox.querySelector("[data-confirm-yes]").focus();
  }

  confirmBox.querySelector("[data-confirm-yes]").addEventListener("click", function () {
    confirmBox.hidden = true;
    var fn = state.pendingAction;
    state.pendingAction = null;
    if (fn) fn();
  });
  confirmBox.querySelector("[data-confirm-no]").addEventListener("click", function () {
    confirmBox.hidden = true;
    state.pendingAction = null;
  });

  dialog.querySelector("[data-form-confirm]").addEventListener("click", function () { askConfirm("Confirm and save this challan?", save); });
  dialog.querySelectorAll("[data-form-exit]").forEach(function (b) { b.addEventListener("click", function () { dialog.close(); }); });

  dialog.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !confirmBox.hidden) { e.preventDefault(); confirmBox.hidden = true; }
  });

  window.SPChallanForm = { open: open };
})();
