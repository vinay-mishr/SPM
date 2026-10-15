/* GST Credit Note Entry (item-based): list, Add / Modify / View / Delete / Print, item grid and totals. */
(function () {
  "use strict";

  var root = document.querySelector("[data-ie]");
  if (!root) return;

  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var canEdit = root.dataset.canEdit === "1";
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var search = root.querySelector("[data-search]");
  var rows = root.querySelector("[data-rows]");
  var alertBox = root.querySelector("[data-alert]");
  var dialog = document.querySelector("[data-form]");
  var form = document.querySelector("[data-ie-form]");
  var formAlert = document.querySelector("[data-form-alert]");
  var partySearch = document.querySelector("[data-party-search]");
  var itemSearch = document.querySelector("[data-item-search]");
  var itemRows = document.querySelector("[data-item-rows]");
  var itemError = document.querySelector("[data-item-error]");
  var deleteDialog = document.querySelector("[data-delete-dialog]");
  var state = { rows: [], selected: null, mode: "add", key: null, lines: [], item: null, editIndex: -1, selectedIndex: -1 };
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
    root.querySelectorAll('[data-action="modify"], [data-action="delete"], [data-action="view"]').forEach(function (b) {
      b.disabled = !has || (!canEdit && b.dataset.action !== "view");
    });
    root.querySelectorAll('[data-action="print"]').forEach(function (b) { b.disabled = !has; });
  }

  function render() {
    rows.textContent = "";
    state.rows.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.dataset.key = r.key;
      tr.tabIndex = 0;
      if (r.key === state.selected) tr.classList.add("is-selected");
      tr.append(cell(r.cn_no, "cn-code"), cell(dmy(r.date)), cell(r.party), cell(r.city), cell(r.net, "num"));
      tr.addEventListener("click", function () { state.selected = r.key; render(); });
      tr.addEventListener("dblclick", function () { state.selected = r.key; open("view"); });
      rows.appendChild(tr);
    });
    if (!state.rows.length) {
      var empty = document.createElement("tr");
      empty.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 5;
      td.textContent = "No credit notes in this date range.";
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
      if (!res.ok) { show(alertBox, res.body.message || "Could not load credit notes."); return; }
      state.rows = res.body.rows;
      if (!selectedRow()) state.selected = null;
      render();
    });
  }

  function field(name) { return form.querySelector('[data-field="' + name + '"]'); }

  function updateTotals() {
    var amount = 0;
    state.lines.forEach(function (l) {
      if (l.held) return;
      var base = l.qty * l.rate;
      var d = base * l.dis / 100;
      amount += base - d;
    });
    var gstPct = num(field("gst_pct").value);
    var gst = amount * gstPct / 100;
    var freight = num(field("freight").value);
    var fg = freight * num(field("freight_gst_pct").value) / 100;
    var adj1 = num(field("adj_amt1").value);
    var adj2 = num(field("adj_amt2").value);
    form.querySelector("[data-total-amount]").value = f2(amount);
    form.querySelector("[data-gst-amount]").value = f2(gst);
    form.querySelector("[data-freight-gst]").value = f2(fg);
    var net = amount + gst + freight + fg + adj1 + adj2;
    form.querySelector("[data-net-amount]").value = f2(net);
    form.querySelector("[data-net-rounded]").value = Math.round(net);
  }

  function renderItems(focusIndex) {
    itemRows.textContent = "";
    if (!state.lines.length) {
      var tr = document.createElement("tr");
      tr.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 10;
      td.textContent = "No items added. Press Space on a row to hold/restore it, double-click to edit.";
      tr.appendChild(td);
      itemRows.appendChild(tr);
    }
    state.lines.forEach(function (l, i) {
      var tr = document.createElement("tr");
      tr.tabIndex = 0;
      tr.dataset.index = i;
      var classes = [];
      if (i === state.editIndex) classes.push("is-editing");
      if (i === state.selectedIndex) classes.push("is-selected");
      if (l.held) classes.push("is-held");
      tr.className = classes.join(" ");
      var base = l.qty * l.rate;
      var amount = base - base * l.dis / 100;
      tr.append(cell(i + 1), cell(i + 1), cell(l.item_code), cell(l.item_name), cell(l.hsn_code), cell(l.unit),
        cell(f2(l.dis), "num"), cell(f3(l.qty), "num"), cell(f2(l.rate), "num"), cell(f2(amount), "num"));
      tr.addEventListener("click", function () {
        state.selectedIndex = i;
        itemRows.querySelectorAll("tr.is-selected").forEach(function (el) { el.classList.remove("is-selected"); });
        tr.classList.add("is-selected");
      });
      itemRows.appendChild(tr);
    });
    if (focusIndex != null) {
      var toFocus = itemRows.querySelector('tr[data-index="' + focusIndex + '"]');
      if (toFocus) toFocus.focus();
    }
    updateTotals();
  }

  function toggleHeld(index) {
    var l = state.lines[index];
    if (!l) return;
    l.held = !l.held;
    if (l.held && state.editIndex === index) { clearItemRow(); }
    renderItems(index);
  }

  function clearItemRow() {
    state.item = null;
    state.editIndex = -1;
    itemSearch.value = "";
    form.querySelector("[data-item-code]").value = "";
    form.querySelector("[data-item-hsn]").value = "";
    form.querySelector("[data-item-unit]").value = "";
    form.querySelector("[data-item-dis]").value = "0.00";
    form.querySelector("[data-item-qty]").value = "1.000";
    form.querySelector("[data-item-rate]").value = "0.00";
    itemError.textContent = "";
    form.querySelector("[data-item-cancel]").hidden = true;
    form.querySelector("[data-item-add]").textContent = "OK";
  }

  function fillItem(code) {
    getJson(root.dataset.partUrl + "?code=" + encodeURIComponent(code)).then(function (res) {
      if (!res.ok) { itemError.textContent = res.body.message || "Item not found."; return; }
      var p = res.body;
      state.item = { code: p.code, name: p.name, hsn: p.hsn, unit: p.unit, gst_pct: p.gst_pct };
      itemSearch.value = p.name;
      form.querySelector("[data-item-code]").value = p.code;
      form.querySelector("[data-item-hsn]").value = p.hsn;
      form.querySelector("[data-item-unit]").value = p.unit;
      form.querySelector("[data-item-rate]").value = p.rate;
      // GST % is one rate for the whole credit note (it isn't tracked per line), so only
      // suggest it from the first item picked -- never overwrite a value already entered.
      if (num(field("gst_pct").value) === 0 && num(p.gst_pct) > 0) { field("gst_pct").value = p.gst_pct; updateTotals(); }
      itemError.textContent = "";
      form.querySelector("[data-item-qty]").focus();
    });
  }

  function addItem() {
    itemError.textContent = "";
    if (!state.item) { itemError.textContent = "Select an item."; itemSearch.focus(); return; }
    var qty = num(form.querySelector("[data-item-qty]").value);
    var rate = num(form.querySelector("[data-item-rate]").value);
    var dis = num(form.querySelector("[data-item-dis]").value);
    if (!(qty > 0)) { itemError.textContent = "Quantity must be greater than zero."; return; }
    if (rate < 0) { itemError.textContent = "Rate can't be negative."; return; }
    var line = { item_code: state.item.code, item_name: state.item.name, hsn_code: state.item.hsn, unit: state.item.unit,
      qty: qty, rate: rate, dis: dis };
    if (state.editIndex >= 0) state.lines[state.editIndex] = line; else state.lines.push(line);
    clearItemRow();
    renderItems();
    itemSearch.focus();
  }

  itemRows.addEventListener("dblclick", function (e) {
    var tr = e.target.closest("tr[data-index]");
    if (!tr || dialog.dataset.readonly === "1") return;
    var i = Number(tr.dataset.index), l = state.lines[i];
    if (l.held) return;
    state.editIndex = i;
    state.selectedIndex = i;
    state.item = { code: l.item_code, name: l.item_name, hsn: l.hsn_code, unit: l.unit };
    itemSearch.value = l.item_name;
    form.querySelector("[data-item-code]").value = l.item_code;
    form.querySelector("[data-item-hsn]").value = l.hsn_code;
    form.querySelector("[data-item-unit]").value = l.unit;
    form.querySelector("[data-item-dis]").value = l.dis;
    form.querySelector("[data-item-qty]").value = l.qty;
    form.querySelector("[data-item-rate]").value = l.rate;
    form.querySelector("[data-item-cancel]").hidden = false;
    renderItems();
    form.querySelector("[data-item-qty]").focus();
  });

  form.querySelector("[data-item-cancel]").addEventListener("click", function () {
    clearItemRow();
    renderItems();
  });

  itemRows.addEventListener("keydown", function (e) {
    if (e.key !== " " && e.key !== "Spacebar") return;
    var tr = e.target.closest("tr[data-index]");
    if (!tr || dialog.dataset.readonly === "1") return;
    var tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable) return;
    e.preventDefault();
    toggleHeld(Number(tr.dataset.index));
  });

  window.HelpLookup.attach(itemSearch, {
    endpoint: root.dataset.itemsUrl, resultsKey: "items", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "unit", label: "Unit" }],
    title: "Item",
    onSelect: function (row) { fillItem(row.code); },
  });

  window.HelpLookup.attach(partySearch, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Party",
    onSelect: function (row) { field("party_code").value = row.code; partySearch.value = row.name; field("city").value = row.city || ""; field("gr_no").focus(); },
  });

  function setReadonly(on) {
    dialog.dataset.readonly = on ? "1" : "0";
    form.querySelectorAll("input:not([type=hidden]), textarea").forEach(function (el) { el.readOnly = on; });
    form.querySelector("[data-confirm]").hidden = on;
    form.querySelector("[data-item-add]").hidden = on;
    if (on) form.querySelector("[data-item-cancel]").hidden = true;
  }

  function open(mode) {
    var row = selectedRow();
    if (mode !== "add" && !row) return;
    state.mode = mode;
    state.key = mode === "add" ? null : row.key;
    show(formAlert, "");
    form.reset();
    clearItemRow();
    state.lines = [];
    state.selectedIndex = -1;
    document.querySelector("[data-mode-label]").textContent = mode === "add" ? "Add" : mode === "modify" ? "Modify" : "View";
    if (mode === "add") {
      getJson(root.dataset.nextNoUrl).then(function (res) { field("cn_no").value = res.body.cn_no; });
      var now = new Date();
      var pad = function (n) { return String(n).padStart(2, "0"); };
      var today = pad(now.getDate()) + "/" + pad(now.getMonth() + 1) + "/" + now.getFullYear();
      field("cn_date").value = today;
      partySearch.value = "";
      field("city").value = "";
      setReadonly(false);
      renderItems();
      dialog.showModal();
      field("gst_bill_no").focus();
      return;
    }
    getJson(root.dataset.detailUrlTemplate.replace("__NO__", encodeURIComponent(row.key))).then(function (res) {
      if (!res.ok) { show(alertBox, res.body.message || "Could not open the credit note."); return; }
      var d = res.body;
      field("cn_no").value = d.cn_no;
      field("cn_date").value = dmy(d.cn_date);
      field("gr_no").value = d.gr_no;
      field("gr_date").value = dmy(d.gr_date);
      field("gst_bill_no").value = d.gst_bill_no;
      field("gst_bill_date").value = dmy(d.gst_bill_date);
      field("transport").value = d.transport;
      field("remarks").value = d.remarks;
      partySearch.value = d.party_name;
      field("party_code").value = d.party_code;
      field("city").value = d.city || "";
      field("gst_pct").value = d.gst_pct;
      field("freight").value = d.freight;
      field("freight_gst_pct").value = d.freight_gst_pct;
      field("adj_nar1").value = d.adj_nar1;
      field("adj_amt1").value = d.adj_amt1;
      field("adj_nar2").value = d.adj_nar2;
      field("adj_amt2").value = d.adj_amt2;
      state.lines = d.items.map(function (i) {
        return { item_code: i.item_code, item_name: i.item_name, hsn_code: i.hsn_code, unit: i.unit,
          qty: num(i.qty), rate: num(i.rate), dis: num(i.dis_pct), held: false };
      });
      renderItems();
      setReadonly(mode === "view");
      dialog.showModal();
    });
  }

  function save() {
    show(formAlert, "");
    if (!state.lines.some(function (l) { return !l.held; })) { show(formAlert, "Add at least one active (non-held) item."); return; }
    var payload = {
      key: state.mode === "modify" ? state.key : null,
      cn_no: field("cn_no").value.trim(),
      cn_date: window.DateMask.toIso(field("cn_date").value),
      gr_no: field("gr_no").value.trim(),
      gr_date: window.DateMask.toIso(field("gr_date").value),
      gst_bill_no: field("gst_bill_no").value.trim(),
      gst_bill_date: window.DateMask.toIso(field("gst_bill_date").value),
      transport: field("transport").value.trim(),
      remarks: field("remarks").value.trim(),
      party_code: field("party_code").value.trim(),
      gst_pct: field("gst_pct").value,
      freight: field("freight").value,
      freight_gst_pct: field("freight_gst_pct").value,
      adj_nar1: field("adj_nar1").value.trim(),
      adj_amt1: field("adj_amt1").value,
      adj_nar2: field("adj_nar2").value.trim(),
      adj_amt2: field("adj_amt2").value,
      items: state.lines.filter(function (l) { return !l.held; }).map(function (l) {
        return { item_code: l.item_code, qty: l.qty, rate: l.rate, dis_pct: l.dis };
      }),
    };
    post(root.dataset.saveUrl, payload).then(function (res) {
      if (!res.ok) {
        show(formAlert, res.body.message || "Could not save the credit note.");
        var first = Object.keys(res.body.errors || {})[0];
        if (first && field(first)) field(first).focus();
        return;
      }
      dialog.close();
      show(alertBox, res.body.message);
      refresh();
    });
  }

  form.querySelector("[data-item-add]").addEventListener("click", addItem);
  // Tab from OK loops back to Part No / Description so the next item can be entered
  // immediately, instead of tabbing into the items grid / remarks / totals.
  form.querySelector("[data-item-add]").addEventListener("keydown", function (e) {
    if (e.key === "Tab" && !e.shiftKey) {
      e.preventDefault();
      itemSearch.focus();
    }
  });
  var focusOrder = [
    field("gst_bill_no"), field("gst_bill_date"), partySearch, field("gr_no"), field("gr_date"), field("transport"),
    itemSearch, form.querySelector("[data-item-dis]"), form.querySelector("[data-item-qty]"), form.querySelector("[data-item-rate]"),
    form.querySelector("[data-item-add]")
  ];

  form.addEventListener("keydown", function (e) {
    if (e.key !== "Enter") return;
    if (e.target === partySearch || e.target === itemSearch) return;
    var idx = focusOrder.indexOf(e.target);
    if (idx === -1) return;
    e.preventDefault();
    if (e.target === form.querySelector("[data-item-add]")) { addItem(); return; }
    var next = focusOrder[idx + (e.shiftKey ? -1 : 1)];
    if (next) next.focus();
  });

  [form.querySelector("[data-item-rate]"), form.querySelector("[data-item-dis]")].forEach(function (el) {
    el.addEventListener("focus", function () { if (el.value === "0.00") el.value = ""; });
    el.addEventListener("blur", function () { if (el.value.trim() === "") el.value = "0.00"; });
  });
  ["gst_pct", "freight", "freight_gst_pct", "adj_amt1", "adj_amt2"].forEach(function (name) {
    field(name).addEventListener("input", updateTotals);
  });

  // Mirrors the legacy form's "BILL NO ALREADY EXIST" check: when typing a C.N. no. by
  // hand (Add mode only -- it's fixed once a credit note exists), warn as soon as the
  // user leaves the field if that number is already taken.
  field("cn_no").addEventListener("blur", function () {
    var no = field("cn_no").value.trim();
    show(formAlert, "");
    if (state.mode !== "add" || !no) return;
    getJson(root.dataset.detailUrlTemplate.replace("__NO__", encodeURIComponent(no))).then(function (res) {
      if (field("cn_no").value.trim() !== no) return; // the user already moved on / changed it
      if (res.ok) {
        show(formAlert, "C.N. no. " + no + " already exists.");
        field("cn_no").focus();
        field("cn_no").select();
      }
    });
  });

  form.querySelector("[data-confirm]").addEventListener("click", function () {
    askConfirm("Are You Sure?", save);
  });
  form.querySelectorAll("[data-form-exit]").forEach(function (b) { b.addEventListener("click", function () { dialog.close(); }); });

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
    post(root.dataset.deleteUrl, { cn_no: row.key }).then(function (res) {
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
