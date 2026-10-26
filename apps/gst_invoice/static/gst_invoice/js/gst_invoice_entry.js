/* GST Invoice (old VFP form INVOICE / list GST INVOICE): list, Add / Modify / View / Delete,
   item grid, GST totals (CGST+SGST within state, IGST interstate). */
(function () {
  "use strict";

  var root = document.querySelector("[data-gi]");
  if (!root) return;

  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var canEdit = root.dataset.canEdit === "1";
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var search = root.querySelector("[data-search]");
  var rows = root.querySelector("[data-rows]");
  var alertBox = root.querySelector("[data-alert]");
  var dialog = document.querySelector("[data-form]");
  var form = document.querySelector("[data-gi-form]");
  var formAlert = document.querySelector("[data-form-alert]");
  var partySearch = document.querySelector("[data-party-search]");
  var itemSearch = document.querySelector("[data-item-search]");
  var itemRows = document.querySelector("[data-item-rows]");
  var itemError = document.querySelector("[data-item-error]");
  var cashRows = document.querySelectorAll("[data-cash-row]");
  var state = { rows: [], selected: null, mode: "add", key: null, lines: [], item: null, editIndex: -1 };
  var alertTimer = null;

  /* Keyboard focus order (per spec):
     Header: Date -> CA/CR -> Chk Order -> Supply -> Party -> GST No -> Consignee Name
       -> Consignee Address -> Phone No -> G.R.No -> G.R.Date -> Vehicle No -> Transport
       -> Order No -> Order Date -> Date of Supply -> Time of Supply -> Place of Supply
       -> Item. Item entry: Item -> Unit -> HSN -> Ord.No/Dt -> Dis % -> Qty -> Rate -> OK
       (then back to Item for the next item). This already matches the existing DOM
       order field-for-field, so plain Tab / Shift+Tab already visits everything in the
       right order; only Enter needs wiring. */
  function onEnterFocus(el, next) {
    el.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      e.preventDefault();
      if (!next) return;
      next.focus();
      if (next.select) next.select();
    });
  }

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
      td.textContent = "No GST invoices in this date range.";
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
      if (!res.ok) { show(alertBox, res.body.message || "Could not load GST invoices."); return; }
      state.rows = res.body.rows;
      if (!selectedRow()) state.selected = null;
      render();
    });
  }

  function field(name) { return form.querySelector('[data-field="' + name + '"]'); }

  function lineAmount(l) { return l.qty * l.rate * (1 - l.dis / 100); }

  function updateTotals() {
    var amount = 0, gst = 0;
    state.lines.forEach(function (l) {
      var a = lineAmount(l);
      amount += a; gst += a * l.gst / 100;
    });
    var freight = num(field("freight").value);
    var fg = freight * num(field("freight_gst_pct").value) / 100;
    var adjNet = 0;
    // ADD/LESS Rate % is taken on Total Amount + GST + Freight + GST on Freight.
    var adjBase = amount + gst + freight + fg;
    [0, 1].forEach(function (i) {
      // A Rate % keeps its Amt in step with that base (e.g. items added later).
      var rate = num(form.querySelector('[data-adj-rate="' + i + '"]').value);
      var amtInput = form.querySelector('[data-adj-amount="' + i + '"]');
      if (rate) amtInput.value = f2(adjBase * rate / 100);
      var amt = num(amtInput.value);
      var sign = form.querySelector('[data-adj-sign="' + i + '"]').value;
      adjNet += sign === "A" ? amt : -amt;
    });
    form.querySelector("[data-total-amount]").value = f2(amount);
    form.querySelector("[data-gst-amount]").value = f2(gst);
    form.querySelector("[data-freight-gst]").value = f2(fg);
    var net = amount + gst + freight + fg + adjNet;
    form.querySelector("[data-net-amount]").value = f2(net);
    form.querySelector("[data-net-rounded]").value = Math.round(net);
  }

  function renderItems() {
    itemRows.textContent = "";
    if (!state.lines.length) {
      var tr = document.createElement("tr");
      tr.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 11;
      td.textContent = "No items added. Press Space on a row to remove it, double-click to edit.";
      tr.appendChild(td);
      itemRows.appendChild(tr);
    }
    state.lines.forEach(function (l, i) {
      var tr = document.createElement("tr");
      tr.tabIndex = 0;
      tr.dataset.index = i;
      if (i === state.editIndex) tr.classList.add("is-editing");
      tr.append(cell(i + 1), cell(l.item_code), cell(l.item_name), cell(l.hsn_code), cell(l.unit),
        cell(l.order_no), cell(String(Math.round(num(l.qty))), "num"), cell(f2(l.rate), "num"), cell(f2(l.dis), "num"),
        cell(f2(lineAmount(l)), "num"), cell(f2(l.gst), "num"));
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
    form.querySelector("[data-item-order]").value = "";
    form.querySelector("[data-item-dis]").value = "0.00";
    form.querySelector("[data-item-qty]").value = "1";
    form.querySelector("[data-item-rate]").value = "0.00";
    itemError.textContent = "";
  }

  function fillItem(code) {
    getJson(root.dataset.itemUrl + "?code=" + encodeURIComponent(code)).then(function (res) {
      if (!res.ok) { itemError.textContent = res.body.message || "Item not found."; return; }
      var p = res.body;
      state.item = { code: p.code, name: p.name, unit: p.unit, hsn: p.hsn, gst: num(p.gst_pct) };
      itemSearch.value = p.name;
      form.querySelector("[data-item-code]").value = p.code;
      form.querySelector("[data-item-unit]").value = p.unit;
      form.querySelector("[data-item-hsn]").value = p.hsn;
      form.querySelector("[data-item-rate]").value = p.rate;
      itemError.textContent = "";
      // HelpLookup's own focusNext() runs right after this callback and --
      // since Unit and HSN are both readonly, excluded from its generic "next
      // focusable field" search -- would land on Ord.No/Dt instead. Override
      // to Dis %, the real start of the item-entry Enter chain wired below.
      setTimeout(function () { form.querySelector("[data-item-dis]").focus(); form.querySelector("[data-item-dis]").select(); }, 0);
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
    var line = { item_code: state.item.code, item_name: state.item.name, hsn_code: state.item.hsn,
      unit: state.item.unit, order_no: form.querySelector("[data-item-order]").value.trim(),
      qty: qty, rate: rate, dis: dis, gst: state.item.gst };
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
    form.querySelector("[data-item-order]").value = l.order_no;
    form.querySelector("[data-item-qty]").value = l.qty;
    form.querySelector("[data-item-rate]").value = l.rate;
    form.querySelector("[data-item-dis]").value = l.dis;
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
    title: "Item",
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
      field("phone").value = p.phone;
      field("city").value = p.city;
      form.querySelector("[data-supply-type]").value = p.supply_type === "I" ? "I" : "W";
      // Same HelpLookup focusNext() override as fillItem() below -- without this,
      // focusNext() would land on GST No (the next non-readonly field in DOM
      // order). Override to Phone, the real next step in the header's Enter
      // chain wired below.
      setTimeout(function () { field("phone").focus(); }, 0);
    });
  }

  function applyCashMode() {
    var cash = form.querySelector('[data-ca-cr]').value === "CA";
    cashRows.forEach(function (el) { el.hidden = !cash; });
    partySearch.closest("label").hidden = cash;
    form.querySelector('[data-field="gst_no"]').closest("label").hidden = cash;
    form.querySelector('[data-field="phone"]').closest("label").hidden = cash;
    form.querySelector("[data-party-city-row]").hidden = cash;
  }
  form.querySelector('[data-ca-cr]').addEventListener("change", applyCashMode);

  function setReadonly(on) {
    dialog.dataset.readonly = on ? "1" : "0";
    form.querySelectorAll("input:not([type=hidden]):not([type=radio]), select").forEach(function (el) { el.readOnly = on; el.disabled = on && el.type === "radio"; });
    form.querySelectorAll('input[type=radio]').forEach(function (el) { el.disabled = on; });
    form.querySelector("[data-confirm]").hidden = on;
    form.querySelector("[data-item-add]").hidden = on;
  }

  function resetAdjustments() {
    [0, 1].forEach(function (i) {
      form.querySelector('[data-adj-sign="' + i + '"]').value = "A";
      setAdjLedger(i, "", "");
      var rateInput = form.querySelector('[data-adj-rate="' + i + '"]');
      rateInput.value = "";
      rateInput.disabled = true;
      var amountInput = form.querySelector('[data-adj-amount="' + i + '"]');
      amountInput.value = "";
      amountInput.disabled = true;
    });
  }

  // ADD/LESS ledger: the visible box shows the ledger NAME, the 4-char code
  // lives in the hidden [data-adj-code] (that's what gets saved) and is echoed
  // in the CODE pill next to it.
  function setAdjLedger(i, code, name) {
    form.querySelector('[data-adj-code="' + i + '"]').value = code;
    var ledgerInput = form.querySelector('[data-adj-ledger="' + i + '"]');
    ledgerInput.value = name;
    ledgerInput.title = name || "Type to search the ledger master, or press Enter";
    form.querySelector('[data-adj-code-badge="' + i + '"]').textContent = code || "CODE";
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
      form.querySelector('[data-ca-cr]').value = "CR";
      form.querySelector('[data-chk-order]').value = "N";
      form.querySelector("[data-supply-type]").value = "W";
      form.querySelector("[data-reverse-charge]").value = "N";
      applyCashMode();
      setReadonly(false);
      renderItems();
      dialog.showModal();
      field("bill_no").focus();
      return;
    }
    getJson(root.dataset.detailUrlTemplate.replace("__NO__", encodeURIComponent(row.key))).then(function (res) {
      if (!res.ok) { show(alertBox, res.body.message || "Could not open the GST invoice."); return; }
      var d = res.body;
      field("bill_no").value = d.bill_no;
      field("date").value = dmy(d.date);
      form.querySelector('[data-ca-cr]').value = d.ca_cr;
      form.querySelector('[data-chk-order]').value = d.chk_order;
      form.querySelector("[data-supply-type]").value = d.supply_type === "I" ? "I" : "W";
      form.querySelector("[data-reverse-charge]").value = d.reverse_charge ? "Y" : "N";
      applyCashMode();
      partySearch.value = d.party_name;
      field("party_code").value = d.party_code;
      field("cash_party_name").value = d.cash_party_name;
      field("cash_party_city").value = d.cash_party_city;
      field("gst_no").value = d.gst_no;
      field("phone").value = d.phone;
      field("city").value = d.city;
      field("consignee_name").value = d.consignee_name;
      field("consignee_address").value = d.consignee_address;
      field("order_no").value = d.order_no;
      field("order_date").value = dmy(d.order_date);
      field("gr_no").value = d.gr_no;
      field("gr_date").value = dmy(d.gr_date);
      field("vehicle_no").value = d.vehicle_no;
      field("transport").value = d.transport;
      field("date_of_supply").value = dmy(d.date_of_supply);
      field("time_of_supply").value = d.time_of_supply;
      field("place_of_supply").value = d.place_of_supply;
      field("eway_no").value = d.eway_no;
      field("eway_date").value = dmy(d.eway_date);
      field("remarks").value = d.remarks;
      field("freight").value = d.freight;
      field("freight_gst_pct").value = d.freight_rate;
      (d.adjustments || []).slice(0, 2).forEach(function (a, i) {
        form.querySelector('[data-adj-sign="' + i + '"]').value = a.sign === "S" ? "S" : "A";
        setAdjLedger(i, a.code, a.name);
        form.querySelector('[data-adj-rate="' + i + '"]').disabled = false;
        var amountInput = form.querySelector('[data-adj-amount="' + i + '"]');
        amountInput.value = a.amount;
        amountInput.disabled = false;
      });
      state.lines = d.items.map(function (i) {
        return { item_code: i.item_code, item_name: i.item_name, hsn_code: i.hsn_code, unit: i.unit,
          order_no: i.order_no, qty: num(i.qty), rate: num(i.rate), dis: 0, gst: num(i.gst_pct) };
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
      ca_cr: form.querySelector('[data-ca-cr]').value,
      chk_order: form.querySelector('[data-chk-order]').value,
      supply_type: form.querySelector("[data-supply-type]").value,
      party_code: field("party_code").value.trim(),
      cash_party_name: field("cash_party_name").value.trim(),
      cash_party_city: field("cash_party_city").value.trim(),
      gst_no: field("gst_no").value.trim(),
      phone: field("phone").value.trim(),
      consignee_name: field("consignee_name").value.trim(),
      consignee_address: field("consignee_address").value.trim(),
      order_no: field("order_no").value.trim(),
      order_date: window.DateMask.toIso(field("order_date").value),
      gr_no: field("gr_no").value.trim(),
      gr_date: window.DateMask.toIso(field("gr_date").value),
      vehicle_no: field("vehicle_no").value.trim(),
      transport: field("transport").value.trim(),
      date_of_supply: window.DateMask.toIso(field("date_of_supply").value),
      time_of_supply: field("time_of_supply").value.trim(),
      place_of_supply: field("place_of_supply").value.trim(),
      eway_no: field("eway_no").value.trim(),
      eway_date: window.DateMask.toIso(field("eway_date").value),
      reverse_charge: form.querySelector("[data-reverse-charge]").value === "Y",
      remarks: field("remarks").value.trim(),
      freight: field("freight").value,
      freight_gst_pct: field("freight_gst_pct").value,
      adjustments: [0, 1].map(function (i) {
        return {
          sign: form.querySelector('[data-adj-sign="' + i + '"]').value,
          code: form.querySelector('[data-adj-code="' + i + '"]').value.trim(),
          amount: form.querySelector('[data-adj-amount="' + i + '"]').value,
        };
      }),
      items: state.lines.map(function (l) {
        return { item_code: l.item_code, order_no: l.order_no, qty: l.qty, rate: l.rate, dis_pct: l.dis };
      }),
    };
    post(root.dataset.saveUrl, payload).then(function (res) {
      if (!res.ok) {
        show(formAlert, res.body.message || "Could not save the GST invoice.");
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
    window.askConfirm(message, onYes);
  }

  /* Header focus chain: Bill No -> Date -> CA/CR -> Chk Order -> Party -> Phone
     -> Consignee Name -> Consignee Address -> Order No -> Order Date -> G.R.No
     -> G.R.Date -> Vehicle No -> Transport -> Date of Supply -> Time of Supply
     -> Place of Supply -> Item. City, GST No, Cash Party and Supply are
     reachable by Tab/click but deliberately not part of this Enter chain.
     Party -> Phone is wired via fillParty() above instead (that's where the
     party gets filled in, same as Item -> Dis % below). */
  onEnterFocus(field("bill_no"), field("date"));
  onEnterFocus(field("date"), form.querySelector('[data-ca-cr]'));
  onEnterFocus(form.querySelector('[data-ca-cr]'), form.querySelector('[data-chk-order]'));
  onEnterFocus(form.querySelector('[data-chk-order]'), partySearch);
  onEnterFocus(field("phone"), field("consignee_name"));
  onEnterFocus(field("consignee_name"), field("consignee_address"));
  onEnterFocus(field("consignee_address"), field("order_no"));
  onEnterFocus(field("order_no"), field("order_date"));
  onEnterFocus(field("order_date"), field("gr_no"));
  onEnterFocus(field("gr_no"), field("gr_date"));
  onEnterFocus(field("gr_date"), field("vehicle_no"));
  onEnterFocus(field("vehicle_no"), field("transport"));
  onEnterFocus(field("transport"), field("date_of_supply"));
  onEnterFocus(field("date_of_supply"), field("time_of_supply"));
  onEnterFocus(field("time_of_supply"), field("place_of_supply"));
  onEnterFocus(field("place_of_supply"), itemSearch);

  var itemAddBtn = form.querySelector("[data-item-add]");
  itemAddBtn.addEventListener("click", addItem);
  // Item-entry focus chain: Item (via fillItem(), above) -> Dis % -> Qty -> Rate
  // -> OK, then back to Item (addItem(), above) for the next line. Unit/HSN/
  // Ord.No-Dt are reachable by Tab/click but not part of this Enter chain.
  // Only Rate's Enter actually adds the row (via the button's own native
  // Enter-triggers-click behavior once it's focused).
  form.querySelector("[data-item-dis]").addEventListener("focus", function () { this.select(); });
  onEnterFocus(form.querySelector("[data-item-dis]"), form.querySelector("[data-item-qty]"));
  onEnterFocus(form.querySelector("[data-item-qty]"), form.querySelector("[data-item-rate]"));
  onEnterFocus(form.querySelector("[data-item-rate]"), itemAddBtn);

  field("freight").addEventListener("input", updateTotals);
  field("freight_gst_pct").addEventListener("input", updateTotals);
  [0, 1].forEach(function (i) {
    var ledgerInput = form.querySelector('[data-adj-ledger="' + i + '"]');
    var codeInput = form.querySelector('[data-adj-code="' + i + '"]');
    var rateInput = form.querySelector('[data-adj-rate="' + i + '"]');
    var amountInput = form.querySelector('[data-adj-amount="' + i + '"]');

    function syncAdjAmountEnabled() {
      var hasLedger = codeInput.value.trim() !== "";
      rateInput.disabled = !hasLedger;
      amountInput.disabled = !hasLedger;
      if (!hasLedger) { rateInput.value = ""; amountInput.value = ""; }
      updateTotals();
    }

    // Typing in the name box drops the previously selected ledger -- a code
    // is only set by picking a row from the lookup.
    ledgerInput.addEventListener("input", function () {
      ledgerInput.value = ledgerInput.value.toUpperCase();
      if (codeInput.value) {
        codeInput.value = "";
        form.querySelector('[data-adj-code-badge="' + i + '"]').textContent = "CODE";
        ledgerInput.title = "Type to search the ledger master, or press Enter";
      }
      syncAdjAmountEnabled();
    });
    ledgerInput.addEventListener("blur", syncAdjAmountEnabled);

    if (window.HelpLookup && root.dataset.ledgersUrl) {
      window.HelpLookup.attach(ledgerInput, {
        endpoint: root.dataset.ledgersUrl, resultsKey: "ledgers", valueField: "name",
        displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Ledger" }],
        title: "Ledger",
        onSelect: function (row) {
          setAdjLedger(i, row.code, row.name || row.code);
          syncAdjAmountEnabled();
          rateInput.focus();
        },
      });
    }

    // Rate is a %: Amt = (Total + GST + Freight + GST on Freight) x Rate / 100
    // (worked out in updateTotals()). Amt stays editable -- typing one directly clears the Rate --
    // and Amt is the value that's saved / added to the net.
    rateInput.addEventListener("focus", function () { this.select(); });
    rateInput.addEventListener("input", function () {
      if (!num(rateInput.value)) amountInput.value = "";
      updateTotals();
    });
    amountInput.addEventListener("input", function () { rateInput.value = ""; });
    onEnterFocus(rateInput, amountInput);

    form.querySelector('[data-adj-sign="' + i + '"]').addEventListener("change", updateTotals);
    amountInput.addEventListener("input", updateTotals);
  });

  form.querySelector("[data-confirm]").addEventListener("click", function () {
    askConfirm("Are You Sure?", save);
  });
  form.querySelectorAll("[data-form-exit]").forEach(function (b) { b.addEventListener("click", function () { dialog.close(); }); });
  dialog.addEventListener("keydown", function (e) { if (e.key === "Escape" && dialog.open) { e.preventDefault(); dialog.close(); } });

  root.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var a = btn.dataset.action;
      if (a === "add") open("add");
      else if (a === "modify") open("modify");
      else if (a === "view") open("view");
      else if (a === "delete") {
        if (!selectedRow()) return;
        askConfirm("Are You Sure?", function () {
          var row = selectedRow();
          if (!row) return;
          post(root.dataset.deleteUrl, { bill_no: row.key }).then(function (res) {
            show(alertBox, res.body.message || "");
            state.selected = null;
            refresh();
          });
        });
      }
      else if (a === "print") {
        var row = selectedRow();
        if (!row) return;
        printOptionsDialog.querySelector("[data-print-bill-no]").value = row.bill_no;
        printOptionsDialog.querySelector("[data-print-net-amount]").value = row.net_amount;
        printOptionsDialog.showModal();
      }
      else if (a === "refresh") refresh();
      else if (a === "exit") window.location.href = root.dataset.exitUrl;
    });
  });

  /* --- Print options dialog (VIEW / PRINT / PRINT PDF / WHATSAPP / EXIT) --------
     Same popup, same interaction pattern as apps.purchase_orders' own
     print-options dialog (purchase_order_master.js). */
  var printOptionsDialog = document.getElementById("gi-print-options-dialog");
  var copyCheckboxes = printOptionsDialog.querySelectorAll('input[name="gi-copy-type"]');
  copyCheckboxes.forEach(function (box) {
    box.addEventListener("change", function () {
      if (box.checked) copyCheckboxes.forEach(function (other) { if (other !== box) other.checked = false; });
      else box.checked = true; // always exactly one selected, never zero
    });
  });
  function copyType() {
    var checked = Array.prototype.find.call(copyCheckboxes, function (b) { return b.checked; });
    return checked ? checked.value : "";
  }

  function printUrl(row, preview) {
    var url = root.dataset.printUrlTemplate.replace("__NO__", encodeURIComponent(row.key));
    var params = new URLSearchParams();
    if (preview) params.set("preview", "1");
    params.set("copy", copyType());
    return url + "?" + params.toString();
  }

  function pdfUrl(row) {
    var url = root.dataset.pdfUrlTemplate.replace("__NO__", encodeURIComponent(row.key));
    return url + "?copy=" + encodeURIComponent(copyType());
  }

  var whatsappDialog = document.getElementById("gi-whatsapp-dialog");
  var whatsappParty = whatsappDialog.querySelector("[data-whatsapp-party]");
  var whatsappMobile = whatsappDialog.querySelector("[data-whatsapp-mobile]");
  var whatsappAlert = whatsappDialog.querySelector("[data-whatsapp-alert]");
  var whatsappRow = null;

  function normalizeMobile(raw) {
    var digits = (raw || "").replace(/\D/g, "");
    if (digits.length === 10) return "91" + digits;
    if (digits.length === 12 && digits.startsWith("91")) return digits;
    return null;
  }

  function openWhatsAppDialog() {
    var row = selectedRow();
    if (!row) return;
    whatsappAlert.hidden = true;
    whatsappParty.value = row.party || "";
    whatsappMobile.value = "";
    whatsappRow = row;
    var url = root.dataset.detailUrlTemplate.replace("__NO__", encodeURIComponent(row.key));
    getJson(url).then(function (res) {
      if (res.ok && whatsappRow === row) whatsappMobile.value = res.body.phone || "";
    });
    whatsappDialog.showModal();
    whatsappMobile.focus();
  }

  whatsappDialog.querySelector("[data-whatsapp-send]").addEventListener("click", function () {
    var mobile = normalizeMobile(whatsappMobile.value);
    if (!mobile) {
      whatsappAlert.textContent = "Enter a valid 10-digit mobile number.";
      whatsappAlert.hidden = false;
      return;
    }
    var row = whatsappRow;
    var shareUrl = root.dataset.shareUrlTemplate.replace("__NO__", encodeURIComponent(row.key));
    var sendBtn = whatsappDialog.querySelector("[data-whatsapp-send]");
    sendBtn.disabled = true;
    // Open the tab NOW, synchronously, inside the click -- popup blockers only
    // allow window.open() during the click itself.
    var waTab = window.open("", "_blank");
    post(shareUrl, {}).then(function (res) {
      sendBtn.disabled = false;
      if (!res.ok) {
        if (waTab) waTab.close();
        whatsappAlert.textContent = res.body.message || "Could not create a share link for this invoice.";
        whatsappAlert.hidden = false;
        return;
      }
      var message = "Dear " + (whatsappParty.value || "Sir/Madam") + ",\n" +
        "Please find your tax invoice below.\n" +
        "Invoice No: " + row.bill_no + "\n" +
        "Download Invoice PDF:\n" + res.body.url + "\n" +
        "Thank you.\nSP MACHINES";
      whatsappDialog.close();
      var waUrl = "https://wa.me/" + mobile + "?text=" + encodeURIComponent(message);
      if (waTab) waTab.location.href = waUrl; else window.open(waUrl, "_blank");
    }).catch(function () {
      sendBtn.disabled = false;
      if (waTab) waTab.close();
      whatsappAlert.textContent = "Could not reach the server.";
      whatsappAlert.hidden = false;
    });
  });
  whatsappDialog.querySelector("[data-whatsapp-back]").addEventListener("click", function () { whatsappDialog.close(); });

  printOptionsDialog.querySelectorAll("[data-print-action]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var action = btn.dataset.printAction;
      if (action === "exit") { printOptionsDialog.close(); return; }
      var row = selectedRow();
      if (!row) return;
      printOptionsDialog.close();
      if (action === "whatsapp") openWhatsAppDialog();
      else if (action === "pdf") window.open(pdfUrl(row), "_blank");
      else window.open(printUrl(row, action === "preview"), "_blank");
    });
  });

  startDate.value = window.DateMask.toDisplay(new Date().toISOString().slice(0, 10));
  endDate.value = window.DateMask.toDisplay(new Date().toISOString().slice(0, 10));
  search.addEventListener("input", function () { clearTimeout(search._t); search._t = setTimeout(refresh, 250); });
  startDate.addEventListener("change", refresh);
  endDate.addEventListener("change", refresh);
  applyCashMode();
  refresh();
})();
