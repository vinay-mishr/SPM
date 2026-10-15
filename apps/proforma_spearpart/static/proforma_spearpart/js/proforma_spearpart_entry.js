/* Performa Invoice (Spearpart) (old VFP form gPER4): list, Add / Modify / View /
   Delete, item grid, GST(Y/N) toggle, Packing/Commissioning/Freight/Insurance
   charges -- same shape as apps.proforma_invoice's own screen. */
(function () {
  "use strict";

  var root = document.querySelector("[data-pfs]");
  if (!root) return;

  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var canEdit = root.dataset.canEdit === "1";
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var search = root.querySelector("[data-search]");
  var rows = root.querySelector("[data-rows]");
  var alertBox = root.querySelector("[data-alert]");
  var dialog = document.querySelector("[data-form]");
  var form = document.querySelector("[data-pfs-form]");
  var formAlert = document.querySelector("[data-form-alert]");
  var partySearch = document.querySelector("[data-party-search]");
  var itemSearch = document.querySelector("[data-item-search]");
  var itemRows = document.querySelector("[data-item-rows]");
  var itemError = document.querySelector("[data-item-error]");
  var deleteDialog = document.querySelector("[data-delete-dialog]");
  var state = { rows: [], selected: null, mode: "add", key: null, lines: [], item: null, editIndex: -1 };
  var alertTimer = null;

  function show(box, msg) {
    box.textContent = msg || "";
    box.hidden = !msg;
    if (box === alertBox && msg) {
      clearTimeout(alertTimer);
      alertTimer = setTimeout(function () { box.hidden = true; }, 5000);
    }
  }

  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (cls) td.className = cls;
    return td;
  }

  function dmy(iso) {
    var p = String(iso || "").split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : "";
  }

  function num(v) { return Number(v) || 0; }
  function f2(v) { return (Math.round(v * 100) / 100).toFixed(2); }
  function f3(v) { return (Math.round(v * 1000) / 1000).toFixed(3); }

  function post(url, data) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrf, "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(data || {}),
    }).then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); });
  }

  function getJson(url) {
    return fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); });
  }

  function selectedRow() { return state.rows.find(function (r) { return r.key === state.selected; }) || null; }

  function updateToolbar() {
    var has = Boolean(selectedRow());
    root.querySelectorAll('[data-action="modify"], [data-action="delete"], [data-action="view"], [data-action="print"]').forEach(function (b) {
      b.disabled = !has || (!canEdit && b.dataset.action !== "view" && b.dataset.action !== "print");
    });
  }

  function render() {
    rows.textContent = "";
    state.rows.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.dataset.key = r.key;
      tr.tabIndex = 0;
      if (r.key === state.selected) tr.classList.add("is-selected");
      tr.append(cell(r.bill_no, "gi-code"), cell(dmy(r.date)), cell(r.party), cell(r.city), cell(r.net_amount, "num"));
      tr.addEventListener("click", function () { state.selected = r.key; render(); });
      tr.addEventListener("dblclick", function () { state.selected = r.key; open("view"); });
      rows.appendChild(tr);
    });
    if (!state.rows.length) {
      var empty = document.createElement("tr");
      empty.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 5;
      td.textContent = "No Performa Invoices (Sparepart) in this date range.";
      empty.appendChild(td);
      rows.appendChild(empty);
    }
    updateToolbar();
  }

  function refresh() {
    var params = new URLSearchParams();
    params.set("start_date", window.DateMask.toIso(startDate.value));
    params.set("end_date", window.DateMask.toIso(endDate.value));
    params.set("search", search.value.trim());
    getJson(root.dataset.listUrl + "?" + params.toString()).then(function (res) {
      if (!res.ok) { show(alertBox, res.body.message || "Could not load Performa Invoices."); return; }
      state.rows = res.body.rows;
      if (!selectedRow()) state.selected = null;
      render();
    });
  }

  function field(name) { return form.querySelector('[data-field="' + name + '"]'); }
  function radio(name) { return form.querySelector('input[name="' + name + '"]:checked'); }
  function setRadio(name, value) {
    var el = form.querySelector('input[name="' + name + '"][value="' + value + '"]');
    if (el) el.checked = true;
  }

  function lineAmount(l) { return l.qty * l.rate; }

  function updateTotals() {
    var gstOn = field("gst_enabled").value !== "N";
    var amount = 0, gst = 0;
    state.lines.forEach(function (l) {
      var a = lineAmount(l);
      amount += a;
      if (gstOn) gst += a * l.gst / 100;
    });
    var charges = num(field("pack_ch").value) + num(field("commi").value) + num(field("freight").value) + num(field("insur").value);
    var assessable = amount + charges;
    var gross = gst + assessable;
    var adjNet = 0;
    [0, 1].forEach(function (i) {
      var amt = num(form.querySelector('[data-adj-amount="' + i + '"]').value);
      var sign = form.querySelector('[data-adj-sign="' + i + '"]').value;
      adjNet += sign === "A" ? amt : -amt;
    });
    form.querySelector("[data-total-amount]").value = f2(amount);
    form.querySelector("[data-assessable]").value = f2(assessable);
    form.querySelector("[data-gst-amount]").value = f2(gst);
    form.querySelector("[data-gross]").value = f2(gross);
    var net = gross + adjNet;
    form.querySelector("[data-net-amount]").value = f2(net);
    form.querySelector("[data-net-rounded]").value = Math.round(net);
  }

  function renderItems() {
    itemRows.textContent = "";
    if (!state.lines.length) {
      var tr = document.createElement("tr");
      tr.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 10;
      td.textContent = "No items added. Press Space on a row to remove it, double-click to edit.";
      tr.appendChild(td);
      itemRows.appendChild(tr);
    }
    var gstOn = field("gst_enabled").value !== "N";
    state.lines.forEach(function (l, i) {
      var tr = document.createElement("tr");
      tr.tabIndex = 0;
      tr.dataset.index = i;
      if (i === state.editIndex) tr.classList.add("is-editing");
      tr.append(cell(i + 1), cell(i + 1), cell(l.item_code), cell(l.item_name), cell(l.hsn_code), cell(l.unit),
        cell(f3(l.qty), "num"), cell(f2(l.rate), "num"), cell(f2(lineAmount(l)), "num"),
        cell(gstOn ? f2(l.gst) : "0.00", "num"));
      itemRows.appendChild(tr);
    });
    updateTotals();
  }

  function clearItemRow() {
    state.item = null;
    state.editIndex = -1;
    itemSearch.value = "";
    form.querySelector("[data-item-code]").value = "";
    form.querySelector("[data-item-unit]").value = "";
    form.querySelector("[data-item-hsn]").value = "";
    form.querySelector("[data-item-qty]").value = "1.000";
    form.querySelector("[data-item-rate]").value = "0.00";
    itemError.textContent = "";
  }

  function fillItem(code) {
    getJson(root.dataset.itemUrl + "?code=" + encodeURIComponent(code)).then(function (res) {
      if (!res.ok) { itemError.textContent = res.body.message || "Part not found."; return; }
      var p = res.body;
      state.item = { code: p.code, name: p.name, unit: p.unit, hsn: p.hsn, gst: num(p.gst_pct) };
      itemSearch.value = p.name;
      form.querySelector("[data-item-code]").value = p.code;
      form.querySelector("[data-item-unit]").value = p.unit;
      form.querySelector("[data-item-hsn]").value = p.hsn;
      form.querySelector("[data-item-rate]").value = p.rate;
      itemError.textContent = "";
      form.querySelector("[data-item-qty]").focus();
    });
  }

  function addItem() {
    itemError.textContent = "";
    if (!state.item) { itemError.textContent = "Select a part."; itemSearch.focus(); return; }
    var qty = num(form.querySelector("[data-item-qty]").value);
    var rate = num(form.querySelector("[data-item-rate]").value);
    if (!(qty > 0)) { itemError.textContent = "Quantity must be greater than zero."; return; }
    if (rate < 0) { itemError.textContent = "Rate can't be negative."; return; }
    var line = { item_code: state.item.code, item_name: state.item.name,
      hsn_code: form.querySelector("[data-item-hsn]").value.trim() || state.item.hsn,
      unit: form.querySelector("[data-item-unit]").value.trim() || state.item.unit,
      qty: qty, rate: rate, gst: state.item.gst };
    if (state.editIndex >= 0) state.lines[state.editIndex] = line; else state.lines.push(line);
    clearItemRow();
    renderItems();
    itemSearch.focus();
  }

  itemRows.addEventListener("dblclick", function (e) {
    var tr = e.target.closest("tr[data-index]");
    if (!tr || dialog.dataset.readonly === "1") return;
    var i = Number(tr.dataset.index), l = state.lines[i];
    state.editIndex = i;
    state.item = { code: l.item_code, name: l.item_name, unit: l.unit, hsn: l.hsn_code, gst: l.gst };
    itemSearch.value = l.item_name;
    form.querySelector("[data-item-code]").value = l.item_code;
    form.querySelector("[data-item-unit]").value = l.unit;
    form.querySelector("[data-item-hsn]").value = l.hsn_code;
    form.querySelector("[data-item-qty]").value = l.qty;
    form.querySelector("[data-item-rate]").value = l.rate;
    renderItems();
    form.querySelector("[data-item-qty]").focus();
  });

  itemRows.addEventListener("keydown", function (e) {
    var tr = e.target.closest("tr[data-index]");
    if (!tr || dialog.dataset.readonly === "1") return;
    if (e.key === " ") {
      e.preventDefault();
      state.lines.splice(Number(tr.dataset.index), 1);
      state.editIndex = -1;
      renderItems();
    }
  });

  window.HelpLookup.attach(itemSearch, {
    endpoint: root.dataset.itemsUrl, resultsKey: "items", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "unit", label: "Unit" },
      { key: "gst", label: "GST %" }],
    title: "Part",
    onSelect: function (row) { fillItem(row.code); },
  });

  window.HelpLookup.attach(partySearch, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Party",
    onSelect: function (row) { fillParty(row.code); },
  });

  function fillParty(code) {
    getJson(root.dataset.partyUrl + "?code=" + encodeURIComponent(code)).then(function (res) {
      if (!res.ok) return;
      var p = res.body;
      field("party_code").value = p.code;
      partySearch.value = p.name;
      field("gst_no").value = p.gst_no;
      setRadio("pfs-supply", p.supply_type === "I" ? "I" : "W");
    });
  }

  field("gst_enabled").addEventListener("change", renderItems);
  ["pack_ch", "commi", "freight", "insur"].forEach(function (name) {
    field(name).addEventListener("input", updateTotals);
  });

  function setReadonly(on) {
    dialog.dataset.readonly = on ? "1" : "0";
    form.querySelectorAll("input:not([type=hidden]):not([type=radio]), select").forEach(function (el) { el.readOnly = on; el.disabled = on && (el.type === "radio" || el.tagName === "SELECT"); });
    form.querySelectorAll('input[type=radio]').forEach(function (el) { el.disabled = on; });
    form.querySelector("[data-confirm]").hidden = on;
    form.querySelector("[data-item-add]").hidden = on;
  }

  function resetAdjustments() {
    [0, 1].forEach(function (i) {
      form.querySelector('[data-adj-sign="' + i + '"]').value = "A";
      form.querySelector('[data-adj-code="' + i + '"]').value = "";
      form.querySelector('[data-adj-amount="' + i + '"]').value = "0.00";
    });
  }

  function open(mode) {
    var row = selectedRow();
    if (mode !== "add" && !row) return;
    state.mode = mode;
    state.key = mode === "add" ? null : row.key;
    show(formAlert, "");
    form.reset();
    clearItemRow();
    resetAdjustments();
    state.lines = [];
    document.querySelector("[data-mode-label]").textContent = mode === "add" ? "Add" : mode === "modify" ? "Modify" : "View";
    if (mode === "add") {
      getJson(root.dataset.nextNoUrl).then(function (res) { field("bill_no").value = res.body.bill_no; });
      var now = new Date();
      var pad = function (n) { return String(n).padStart(2, "0"); };
      var today = pad(now.getDate()) + "/" + pad(now.getMonth() + 1) + "/" + now.getFullYear();
      field("date").value = today;
      partySearch.value = "";
      field("gst_enabled").value = "Y";
      setRadio("pfs-supply", "W");
      setReadonly(false);
      renderItems();
      dialog.showModal();
      field("date").focus();
      return;
    }
    getJson(root.dataset.detailUrlTemplate.replace("__NO__", encodeURIComponent(row.key))).then(function (res) {
      if (!res.ok) { show(alertBox, res.body.message || "Could not open the Performa Invoice."); return; }
      var d = res.body;
      field("bill_no").value = d.bill_no;
      field("date").value = dmy(d.date);
      field("gst_enabled").value = d.gst_enabled === "N" ? "N" : "Y";
      setRadio("pfs-supply", d.supply_type);
      partySearch.value = d.party_name;
      field("party_code").value = d.party_code;
      field("gst_no").value = d.gst_no;
      field("order_no").value = d.order_no;
      field("order_date").value = dmy(d.order_date);
      field("pl_no").value = d.pl_no;
      field("pl_date").value = dmy(d.pl_date);
      field("others").value = d.others;
      field("remarks").value = d.remarks;
      field("pack_ch").value = d.pack_ch;
      field("commi").value = d.commi;
      field("freight").value = d.freight;
      field("insur").value = d.insur;
      (d.adjustments || []).forEach(function (a, i) {
        if (i > 1) return;
        form.querySelector('[data-adj-sign="' + i + '"]').value = a.sign;
        form.querySelector('[data-adj-code="' + i + '"]').value = a.code;
        form.querySelector('[data-adj-amount="' + i + '"]').value = a.amount;
      });
      state.lines = d.items.map(function (i) {
        return { item_code: i.item_code, item_name: i.item_name, hsn_code: i.hsn_code, unit: i.unit,
          qty: num(i.qty), rate: num(i.rate), gst: num(i.gst_pct) };
      });
      renderItems();
      setReadonly(mode === "view");
      dialog.showModal();
    });
  }

  function save() {
    show(formAlert, "");
    if (!state.lines.length) { show(formAlert, "Add at least one item."); return; }
    var payload = {
      key: state.mode === "modify" ? state.key : null,
      date: window.DateMask.toIso(field("date").value),
      gst_enabled: field("gst_enabled").value,
      supply_type: radio("pfs-supply").value,
      party_code: field("party_code").value.trim(),
      gst_no: field("gst_no").value.trim(),
      order_no: field("order_no").value.trim(),
      order_date: window.DateMask.toIso(field("order_date").value),
      pl_no: field("pl_no").value.trim(),
      pl_date: window.DateMask.toIso(field("pl_date").value),
      others: field("others").value.trim(),
      remarks: field("remarks").value.trim(),
      pack_ch: field("pack_ch").value,
      commi: field("commi").value,
      freight: field("freight").value,
      insur: field("insur").value,
      adjustments: [0, 1].map(function (i) {
        return {
          sign: form.querySelector('[data-adj-sign="' + i + '"]').value,
          code: form.querySelector('[data-adj-code="' + i + '"]').value.trim(),
          amount: form.querySelector('[data-adj-amount="' + i + '"]').value,
        };
      }),
      items: state.lines.map(function (l) {
        return { item_code: l.item_code, hsn_code: l.hsn_code, unit: l.unit, qty: l.qty, rate: l.rate };
      }),
    };
    post(root.dataset.saveUrl, payload).then(function (res) {
      if (!res.ok) {
        show(formAlert, res.body.message || "Could not save the Performa Invoice.");
        var first = Object.keys(res.body.errors || {})[0];
        if (first && field(first)) field(first).focus();
        return;
      }
      dialog.close();
      show(alertBox, res.body.message);
      refresh();
    });
  }

  function askConfirm(message, onYes) {
    if (window.confirm(message)) onYes();
  }

  form.querySelector("[data-item-add]").addEventListener("click", addItem);
  [0, 1].forEach(function (i) {
    form.querySelector('[data-adj-sign="' + i + '"]').addEventListener("change", updateTotals);
    form.querySelector('[data-adj-amount="' + i + '"]').addEventListener("input", updateTotals);
  });

  form.querySelector("[data-confirm]").addEventListener("click", function () {
    askConfirm("Are You Sure?", save);
  });
  form.querySelectorAll("[data-form-exit]").forEach(function (b) { b.addEventListener("click", function () { dialog.close(); }); });
  dialog.addEventListener("keydown", function (e) { if (e.key === "Escape" && dialog.open) { e.preventDefault(); dialog.close(); } });

  form.querySelector("[data-new-party]").href = root.dataset.newPartyUrl;

  root.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var a = btn.dataset.action;
      if (a === "add") open("add");
      else if (a === "modify") open("modify");
      else if (a === "view") open("view");
      else if (a === "delete") { if (selectedRow()) deleteDialog.showModal(); }
      else if (a === "print") { var row = selectedRow(); if (row) window.open(root.dataset.printUrlTemplate.replace("__NO__", encodeURIComponent(row.key)), "_blank"); }
      else if (a === "refresh") refresh();
      else if (a === "exit") window.location.href = root.dataset.exitUrl;
    });
  });

  deleteDialog.querySelector("[data-delete-yes]").addEventListener("click", function () {
    var row = selectedRow();
    deleteDialog.close();
    if (!row) return;
    post(root.dataset.deleteUrl, { bill_no: row.key }).then(function (res) {
      show(alertBox, res.body.message || "");
      state.selected = null;
      refresh();
    });
  });
  deleteDialog.querySelector("[data-delete-no]").addEventListener("click", function () { deleteDialog.close(); });

  startDate.value = window.DateMask.toDisplay(new Date().toISOString().slice(0, 10));
  endDate.value = window.DateMask.toDisplay(new Date().toISOString().slice(0, 10));
  search.addEventListener("input", function () { clearTimeout(search._t); search._t = setTimeout(refresh, 250); });
  startDate.addEventListener("change", refresh);
  endDate.addEventListener("change", refresh);
  refresh();
})();
