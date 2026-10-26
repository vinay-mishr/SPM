/* MRN Entry — shared Add / Modify / View form, matching the supplied reference
   layout and calculations. Exposes window.SPMrnForm.open(mode, row). */
(function () {
  "use strict";

  var root = document.querySelector("[data-mrn-entry]");
  if (!root) return;

  var dialog = document.getElementById("mrn-form-dialog");
  var form = dialog.querySelector("[data-mrn-form]");
  var alertBox = dialog.querySelector("[data-form-alert]");
  var confirmBox = dialog.querySelector("[data-confirm-box]");
  var confirmText = dialog.querySelector("[data-confirm-text]");

  var mrnNo = dialog.querySelector("#mrn-mrn_no");
  var mrnDate = dialog.querySelector("#mrn-mrn_date");
  var partyCode = dialog.querySelector('[data-field="party_code"]');
  var partyName = dialog.querySelector("#mrn-party_name");
  var partySearch = dialog.querySelector("#mrn-party_search");
  var challanNo = dialog.querySelector("#mrn-challan_no");
  var challanDate = dialog.querySelector("#mrn-challan_date");
  var billNo = dialog.querySelector("#mrn-bill_no");
  var billDate = dialog.querySelector("#mrn-bill_date");
  var grNo = dialog.querySelector("#mrn-gr_no");
  var grDate = dialog.querySelector("#mrn-gr_date");
  var transport = dialog.querySelector("#mrn-transport");
  var checkPo = dialog.querySelector("#mrn-check_po");
  var remarks = dialog.querySelector("#mrn-remarks");
  var lastRate = dialog.querySelector("#mrn-last-rate");
  var oc1 = dialog.querySelector("#mrn-oc1");
  var oc2 = dialog.querySelector("#mrn-oc2");

  var rowPartSearch = dialog.querySelector("[data-row-part-search]");
  var rowPoNo = dialog.querySelector("[data-row-po-no]");
  var rowUnit = dialog.querySelector("[data-row-unit]");
  var rowInvoiceQty = dialog.querySelector("[data-row-invoice-qty]");
  var rowQtyAccepted = dialog.querySelector("[data-row-qty-accepted]");
  var rowRate = dialog.querySelector("[data-row-rate]");
  var rowDiscount = dialog.querySelector("[data-row-discount]");
  var rowDisAmt = dialog.querySelector("[data-row-dis-amt]");
  var rowGst = dialog.querySelector("[data-row-gst]");
  var rowSize = dialog.querySelector("[data-row-size]");
  var rowPartCode = dialog.querySelector("[data-row-part-code]");
  var rowPoDate = dialog.querySelector("[data-row-po-date]");
  var rowQtyReceived = dialog.querySelector("[data-row-qty-received]");
  var rowQtyRejected = dialog.querySelector("[data-row-qty-rejected]");
  var rowPendingQty = dialog.querySelector("[data-row-pending-qty]");
  var rowError = dialog.querySelector("[data-row-error]");
  var lineFieldset = dialog.querySelector("[data-line-fieldset]");
  var partCode = ""; // resolved from the part-search HelpLookup selection, not a visible field
  // Mirrors partCode into the no-label code span above SIZE, since the Item
  // Description box itself only shows the part's name.
  function setPartCode(code) { partCode = code; rowPartCode.value = code || ""; }
  var partName = ""; // the picked part's name, kept apart from the "NAME (CODE)" shown in the box

  var gridBody = dialog.querySelector("[data-grid-rows]");
  var totalAmount = dialog.querySelector("#mrn-total-amount");
  var totalDiscount = dialog.querySelector("#mrn-total-discount");
  var totalGst = dialog.querySelector("#mrn-total-gst");
  var totalNet = dialog.querySelector("#mrn-total-net");

  var entry = window.SPMrnEntry;
  var formState = { mode: "add", key: null, lines: [], poMatched: null, snapshot: "", editingIndex: -1 };

  function n(v) { return parseFloat(v) || 0; }
  function money(v) { return n(v).toFixed(2); }
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

  /* --- Party / Part help lookups --------------------------------------------------- */

  if (window.HelpLookup) {
    window.HelpLookup.attach(partySearch, {
      endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
      displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
      title: "Party",
      onSelect: function (row) {
        partyCode.value = row.code;
        partyName.value = row.city || "";
        // Per the form's Enter sequence, PARTY is followed by CHALLAN NO, not
        // straight into the item row (there is no City/State field on this
        // form to fill in -- Party Name and Code are the only party details shown).
        setTimeout(function () { focusField(challanNo); }, 0);
      },
    });
    window.HelpLookup.attach(rowPartSearch, {
      endpoint: root.dataset.partsUrl, resultsKey: "parts", valueField: "name",
      displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "material", label: "Material" }, { key: "gst_percent", label: "GST %" }],
      title: "Part",
      onSelect: function (row) {
        setPartCode(row.code);
        partName = row.name;
        rowPartSearch.value = partDisplayText(row.name, row.code);
        fillPartReference(row.code);
      },
    });
  }

  /* --- Pending-PO check ("Check PO Y/N") ------------------------------------------- */

  function applyPendingMatch(pending) {
    formState.poMatched = pending;
    if (pending) {
      rowPoNo.value = pending.po_no;
      rowPoDate.value = window.DateMask.toDisplay(pending.po_date);
      rowPendingQty.value = pending.pending_qty;
      rowSize.value = pending.size;
      rowRate.value = pending.rate;
      rowRate.readOnly = true;
      rowDiscount.value = pending.discount_percent;
      // Dis Amt is Qty x Rate x Disc% -- with no quantity typed yet it's correctly
      // 0 no matter the discount, which reads as a bug ("10% discount but Dis Amt
      // shows 0"). Default Inv Qty to the full pending quantity, same as Rate/Disc%
      // being pre-filled -- the user can still lower it for a partial receipt.
      if (!rowInvoiceQty.value) rowInvoiceQty.value = pending.pending_qty;
      updateDisAmt();
    } else {
      rowPoNo.value = ""; rowPoDate.value = ""; rowPendingQty.value = ""; rowRate.readOnly = false;
      rowDiscount.readOnly = false;
    }
  }

  function checkPendingOrder(partyCodeValue, partCodeValue) {
    if (checkPo.value !== "Y") { applyPendingMatch(null); return; }
    var url = root.dataset.pendingPoUrl + "?party_code=" + encodeURIComponent(partyCodeValue) + "&part_code=" + encodeURIComponent(partCodeValue);
    entry.fetchJson(url).then(function (res) {
      var pending = res.ok ? res.body.pending : null;
      if (pending) { applyPendingMatch(pending); return; }
      applyPendingMatch(null);
      // Native confirm() is unreliable (or outright suppressed, silently
      // returning false) when called from inside an already-open <dialog> in
      // some browsers/embeddings -- that would wipe the item the user just
      // picked right back out without ever actually asking them. This form
      // already has its own Yes/No confirm box (used by the Save button); use
      // that instead so the prompt reliably shows and "Continue Anyway" reliably keeps the item.
      ask("No Order for this Item, Continue Anyway?", function () {}, function () {
        rowPartSearch.value = ""; setPartCode(""); partName = "";
      });
    });
  }

  // "NAME (CODE)" in the Item Description box once a part is picked, so the
  // code stays visible (it otherwise lives only in the hidden partCode).
  function partDisplayText(name, code) {
    name = (name || "").trim();
    code = (code || "").trim();
    if (!name) return code;
    return code ? name + " (" + code + ")" : name;
  }

  function fillPartReference(code) {
    var url = root.dataset.partReferenceUrl + "?code=" + encodeURIComponent(code);
    entry.fetchJson(url).then(function (res) {
      if (!res.ok) return;
      var ref = res.body;
      rowUnit.value = ref.unit || "";
      rowGst.value = ref.gst_percent || "0.00";
      lastRate.value = money(ref.last_rate || 0);
      if (!formState.poMatched) rowRate.value = ref.rate || "0.00";
      if (!rowSize.value) rowSize.value = ref.size || "";
      checkPendingOrder(partyCode.value.trim(), code);
    });
  }

  /* --- Live calculations: Dis Amt, Qty Rej, grand totals ---------------------------- */

  // Dis Amt is the per-unit discount (Rate x Disc% / 100) -- e.g. Rate 200 at
  // 10% shows Dis Amt 20, and the line Amount comes out to (Rate - Dis Amt) x Qty.
  function updateDisAmt() {
    rowDisAmt.value = money(n(rowRate.value) * n(rowDiscount.value) / 100);
  }
  [rowRate, rowDiscount].forEach(function (el) {
    el.addEventListener("input", updateDisAmt);
  });
  // Dis Amt can also be typed directly -- back-calculate Disc % from it (per unit,
  // same basis as updateDisAmt), so the two stay consistent either way.
  rowDisAmt.addEventListener("input", function () {
    var rate = n(rowRate.value);
    rowDiscount.value = rate ? money(n(rowDisAmt.value) / rate * 100) : "0.00";
  });

  // Qty Acpt always follows Qty Recd: typing Qty Recd sets Qty Acpt to match it
  // (full acceptance assumed), overriding whatever Qty Acpt held before. Typing
  // Qty Rej after that reduces Qty Acpt by that amount, so Qty Recd stays fixed
  // at what was typed while Qty Acpt = Qty Recd - Qty Rej.
  rowQtyReceived.addEventListener("input", function () {
    rowQtyAccepted.value = rowQtyReceived.value;
    rowQtyRejected.value = "";
  });
  rowQtyRejected.addEventListener("input", function () {
    var v = n(rowQtyReceived.value) - n(rowQtyRejected.value);
    rowQtyAccepted.value = v > 0 ? v.toFixed(3) : "0.000";
  });

  function lineAmount(row) {
    var gross = n(row.qty_accepted || row.invoice_qty) * n(row.rate);
    return gross - n(row.discount_amount);
  }

  function computeTotals() {
    var total = 0, discount = 0, gst = 0;
    formState.lines.forEach(function (row) {
      var amt = lineAmount(row);
      total += amt + n(row.discount_amount);
      discount += n(row.discount_amount);
      gst += amt * n(row.gst_percent) / 100;
    });
    totalAmount.value = money(total);
    totalDiscount.value = money(discount);
    totalGst.value = money(gst);
    totalNet.value = money(total - discount + gst + n(oc1.value) + n(oc2.value));
  }
  [oc1, oc2].forEach(function (el) { el.addEventListener("input", computeTotals); });

  /* --- Grid ------------------------------------------------------------------------ */

  function renderGrid() {
    gridBody.textContent = "";
    if (!formState.lines.length) {
      gridBody.innerHTML = '<tr class="empty" data-grid-empty><td colspan="12">No items added yet. Press Space on a row to remove it, double-click to edit.</td></tr>';
      computeTotals();
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
        [index + 1], [row.part_code], [row.part_name], [row.po_no],
        [qtyFmt(row.invoice_qty), "num"], [qtyFmt(row.qty_received), "num"], [qtyFmt(row.qty_accepted), "num"],
        [qtyFmt(row.qty_rejected), "num"], [money(row.rate), "num"], [money(row.discount_percent), "num"],
        [money(row.discount_amount), "num"], [money(lineAmount(row)), "num"],
      ].forEach(function (pair) {
        var td = document.createElement("td");
        if (pair[1]) td.className = pair[1];
        td.textContent = pair[0];
        tr.appendChild(td);
      });
      gridBody.appendChild(tr);
    });
    computeTotals();
  }

  function removeGridRow(index) {
    formState.lines.splice(index, 1);
    if (formState.editingIndex === index) cancelEdit(); else renderGrid();
  }

  function loadRowForEdit(index) {
    if (formState.mode === "view") return;
    var row = formState.lines[index];
    formState.editingIndex = index;
    setPartCode(row.part_code);
    partName = row.part_name;
    rowPartSearch.value = partDisplayText(row.part_name, row.part_code);
    rowPoNo.value = row.po_no; rowPoDate.value = window.DateMask.toDisplay(row.po_date);
    rowSize.value = row.size; rowUnit.value = row.unit;
    rowInvoiceQty.value = row.invoice_qty; rowQtyReceived.value = row.qty_received;
    rowQtyAccepted.value = row.qty_accepted; rowQtyRejected.value = row.qty_rejected;
    rowRate.value = row.rate; rowDiscount.value = row.discount_percent; rowGst.value = row.gst_percent;
    updateDisAmt();
    renderGrid();
    rowPartSearch.focus();
  }

  function cancelEdit() {
    formState.editingIndex = -1;
    setPartCode(""); partName = "";
    rowPartSearch.value = ""; rowPoNo.value = ""; rowPoDate.value = ""; rowPendingQty.value = "";
    rowSize.value = ""; rowUnit.value = ""; rowInvoiceQty.value = ""; rowQtyReceived.value = "";
    rowQtyAccepted.value = ""; rowQtyRejected.value = ""; rowRate.value = ""; rowRate.readOnly = false;
    rowDiscount.value = ""; rowDisAmt.value = ""; rowGst.value = ""; lastRate.value = "0.00";
    formState.poMatched = null;
    rowError.textContent = "";
    renderGrid();
  }

  dialog.querySelector("[data-row-add]").addEventListener("click", function () {
    rowError.textContent = "";
    if (!partCode) { rowError.textContent = "Select an item."; return; }
    var qtyAccepted = rowQtyAccepted.value.trim() || rowQtyReceived.value.trim() || "0";
    if (n(qtyAccepted) <= 0 && n(rowQtyReceived.value) <= 0) {
      rowError.textContent = "Enter a received or accepted quantity more than 0.";
      return;
    }
    var line = {
      part_code: partCode, part_name: partName || partCode,
      po_div: formState.poMatched ? formState.poMatched.div : "",
      po_no: rowPoNo.value.trim(), po_date: formState.poMatched ? formState.poMatched.po_date : null,
      size: rowSize.value.trim(), unit: rowUnit.value.trim(),
      invoice_qty: rowInvoiceQty.value.trim() || "0", qty_received: rowQtyReceived.value.trim() || "0",
      qty_accepted: qtyAccepted, qty_rejected: rowQtyRejected.value.trim() || "0",
      rate: rowRate.value.trim() || "0", discount_percent: rowDiscount.value.trim() || "0",
      // rowDisAmt shows the PER-UNIT discount; the line/total math (lineAmount(),
      // computeTotals()) and the server both expect the TOTAL discount amount.
      discount_amount: money(n(rowDisAmt.value) * n(qtyAccepted)), gst_percent: rowGst.value.trim() || "0",
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

  /* --- Enter-key focus sequence ------------------------------------------------------
   * One centralized handler (not per-field listeners) walks these two explicit orders --
   * matching the legacy form's own field order exactly, which is not the same as the
   * DOM/tab order (e.g. QTY RECD and QTY REJ sit visually below RATE/DISC%/DIS AMT in
   * the markup, but come right after INV QTY in the required sequence).
   *
   * PARTY and ITEM DESCRIPTION both have HelpLookup attached, which intercepts Enter on
   * those two fields itself (and calls stopPropagation()) to open its popup instead of
   * just advancing focus -- see help_lookup.js's attach(). After a selection, HelpLookup
   * runs its own generic "next focusable field in DOM order" (focusNext()): for PARTY
   * that's overridden by the onSelect above to go to CHALLAN NO instead; for ITEM
   * DESCRIPTION, UNIT is the very next focusable, non-readonly field in the markup too,
   * so the generic behavior already lands in the right place with no override needed. */
  var HEADER_ORDER = [mrnNo, mrnDate, partySearch, challanNo, challanDate, billNo, billDate, grNo, grDate, transport, checkPo];
  var ITEM_ORDER = [rowPartSearch, rowUnit, rowInvoiceQty, rowQtyReceived, rowQtyAccepted, rowQtyRejected, rowRate, rowDiscount, rowDisAmt];

  function focusField(el) {
    el.focus();
    if (el.select) el.select();
  }

  function handleEnter(event) {
    var tag = event.target.tagName;
    if (event.key !== "Enter" || (tag !== "INPUT" && tag !== "SELECT")) return;
    event.preventDefault(); // never submit the form by accident

    var fromHeader = HEADER_ORDER.indexOf(event.target);
    if (fromHeader > -1) {
      if (fromHeader < HEADER_ORDER.length - 1) focusField(HEADER_ORDER[fromHeader + 1]);
      else if (!lineFieldset.hidden) focusField(rowPartSearch); // CHECK PO Y/N -> ITEM DESCRIPTION
      return;
    }

    var fromItem = ITEM_ORDER.indexOf(event.target);
    if (fromItem > -1) {
      if (fromItem < ITEM_ORDER.length - 1) focusField(ITEM_ORDER[fromItem + 1]);
      else dialog.querySelector("[data-row-add]").focus(); // DIS AMT -> OK
    }
  }
  form.addEventListener("keydown", handleEnter);

  /* --- Mode / open / save ----------------------------------------------------------- */

  function setMode(mode) {
    formState.mode = mode;
    dialog.dataset.mode = mode;
    dialog.querySelector("[data-mode-label]").textContent = mode.toUpperCase();
    var readOnly = mode === "view";
    [mrnDate, partySearch, checkPo, remarks, oc1, oc2].forEach(function (el) { el.disabled = readOnly; });
    lineFieldset.hidden = readOnly;
    dialog.querySelector("[data-form-confirm]").hidden = readOnly;
  }

  function snapshot() { return JSON.stringify({ party_code: partyCode.value, lines: formState.lines }); }

  function open(mode, row) {
    formState.key = row ? [row.div, row.mrn_no] : null;
    formState.lines = []; formState.editingIndex = -1; formState.poMatched = null;
    clearErrors();
    confirmBox.hidden = true;
    setMode(mode);

    mrnDate.value = window.DateMask.toDisplay(row ? row.mrn_date : new Date().toISOString().slice(0, 10));
    partyCode.value = row ? row.party_code : "";
    partySearch.value = row ? (row.party_name || "") : "";
    partyName.value = row ? (row.city || "") : "";
    checkPo.value = "Y";
    remarks.value = ""; oc1.value = "0.00"; oc2.value = "0.00";
    cancelEdit();

    var ready = !row
      ? entry.fetchJson(root.dataset.nextNoUrl).then(function (res) { mrnNo.value = res.ok ? res.body.mrn_no : "Auto"; })
      : entry.fetchJson(root.dataset.detailUrlTemplate.replace("__DIV__", encodeURIComponent(row.div)).replace("__MRNNO__", encodeURIComponent(row.mrn_no)))
        .then(function (res) {
          if (!res.ok) return;
          mrnNo.value = res.body.mrn_no;
          remarks.value = res.body.remarks || "";
          checkPo.value = res.body.check_po || "Y";
          oc1.value = res.body.other_charge_1 || "0.00";
          oc2.value = res.body.other_charge_2 || "0.00";
          formState.lines = res.body.items || [];
        });

    ready.then(function () {
      renderGrid();
      formState.snapshot = snapshot();
      dialog.showModal();
      focusField(mrnNo); // always the form's starting point, in every mode
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
      div: formState.key ? formState.key[0] : "SP",
      party_code: partyCode.value.trim().toUpperCase(),
      mrn_date: window.DateMask.toIso(mrnDate.value),
      check_po: checkPo.value,
      remarks: remarks.value,
      other_charge_1: oc1.value || "0",
      other_charge_2: oc2.value || "0",
      items: formState.lines,
      key: formState.key ? formState.key.join("|") : "",
    };
    entry.postJson(root.dataset.saveUrl, payload).then(function (res) {
      if (res.ok) {
        dialog.close();
        entry.showToast(res.body.message);
        entry.refresh(res.body.key);
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

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    clearErrors();
    if (!partyCode.value.trim()) { showErrors({ party_code: "Select a party." }); return; }
    if (!formState.lines.length) { alertBox.textContent = "Add at least one item."; alertBox.hidden = false; return; }
    ask("Are you sure?", save);
  });

  dialog.querySelectorAll("[data-form-exit]").forEach(function (btn) { btn.addEventListener("click", function () { dialog.close(); }); });
  dialog.addEventListener("cancel", function (e) {
    e.preventDefault();
    if (!confirmBox.hidden) confirmBox.hidden = true; else dialog.close();
  });

  window.SPMrnForm = { open: open };
})();
