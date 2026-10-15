/* Spare Part Invoice (old VFP form gstbill7, bill_type='P'): list, Add / Modify /
   View / Delete, item grid, GST totals -- same shape as apps.gst_invoice's own
   screen (see that app's JS for the pattern this mirrors). */
(function () {
  "use strict";

  var root = document.querySelector("[data-si]");
  if (!root) return;

  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var canEdit = root.dataset.canEdit === "1";
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var search = root.querySelector("[data-search]");
  var rows = root.querySelector("[data-rows]");
  var alertBox = root.querySelector("[data-alert]");
  var dialog = document.querySelector("[data-form]");
  var form = document.querySelector("[data-si-form]");
  var formAlert = document.querySelector("[data-form-alert]");
  var partySearch = document.querySelector("[data-party-search]");
  var itemSearch = document.querySelector("[data-item-search]");
  var itemRows = document.querySelector("[data-item-rows]");
  var itemError = document.querySelector("[data-item-error]");
  var deleteDialog = document.querySelector("[data-delete-dialog]");
  var confirmDialog = document.querySelector("[data-confirm-dialog]");
  var challanDialog = document.querySelector("[data-challan-dialog]");
  var challanAlert = document.querySelector("[data-challan-alert]");
  var challanRows = document.querySelector("[data-challan-rows]");
  var cashRows = document.querySelectorAll("[data-cash-row]");
  var state = { rows: [], selected: null, mode: "add", key: null, keyDiv: null, keyVouNo: null, lines: [], item: null, editIndex: -1 };
  var alertTimer = null;

  /* Keyboard focus order (per spec):
     Header: Date -> CA/CR -> Chk Order -> Supply -> Party -> GST No -> Consignee Name
       -> Consignee Address -> Phone No -> G.R.No -> G.R.Date -> Vehicle No -> Transport
       -> Order No -> Order Date -> Date of Supply -> Time of Supply -> Place of Supply
     Item entry: Part -> Unit -> HSN -> Ord.No -> Dis % -> Qty -> Rate -> OK (then back
       to Part for the next item).
     This already matches the existing DOM order field-for-field, so plain Tab /
     Shift+Tab already visits everything in the right order; only Enter needs wiring. */
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
      td.textContent = "No Spare Part invoices in this date range.";
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
      if (!res.ok) { show(alertBox, res.body.message || "Could not load Spare Part invoices."); return; }
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
      if (l.active === false) return; // deselected items don't contribute to totals
      var a = lineAmount(l);
      amount += a; gst += a * l.gst / 100;
    });
    var freight = num(field("freight").value);
    var fg = freight * num(field("freight_gst_pct").value) / 100;
    var adjNet = 0;
    [0, 1].forEach(function (i) {
      var amt = num(form.querySelector('[data-adj-amount="' + i + '"]').value);
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
    state.lines.forEach(function (l, i) {
      var tr = document.createElement("tr");
      tr.tabIndex = 0;
      tr.dataset.index = i;
      if (l.active === false) tr.classList.add("is-inactive");
      if (i === state.editIndex) tr.classList.add("is-editing");
      // Particulars is kept on the line (l.particular) and loaded back into the entry
      // field when this row is double-clicked for editing -- not shown in the grid.
      tr.append(cell(i + 1), cell(l.item_code), cell(l.item_name), cell(l.hsn_code), cell(l.unit),
        cell(l.order_no), cell(f3(l.qty), "num"), cell(f2(l.rate), "num"), cell(f2(lineAmount(l)), "num"));
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
    form.querySelector("[data-item-qty]").value = "1.000";
    form.querySelector("[data-item-rate]").value = "0.00";
    form.querySelector("[data-item-stock]").value = "";
    form.querySelector("[data-item-particular]").value = "";
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
      form.querySelector("[data-item-stock]").value = p.stock;
      itemError.textContent = "";
      form.querySelector("[data-item-unit]").focus();
    });
  }

  function addItem() {
    itemError.textContent = "";
    if (!state.item) { itemError.textContent = "Select a part."; itemSearch.focus(); return; }
    var qty = num(form.querySelector("[data-item-qty]").value);
    var rate = num(form.querySelector("[data-item-rate]").value);
    var dis = num(form.querySelector("[data-item-dis]").value);
    if (!(qty > 0)) { itemError.textContent = "Quantity must be greater than zero."; return; }
    if (rate < 0) { itemError.textContent = "Rate can't be negative."; return; }
    var line = { item_code: state.item.code, item_name: state.item.name, hsn_code: state.item.hsn,
      unit: state.item.unit, order_no: form.querySelector("[data-item-order]").value.trim(),
      qty: qty, rate: rate, dis: dis, gst: state.item.gst, active: true,
      particular: form.querySelector("[data-item-particular]").value.trim(),
      // Carried over from the row being edited (if it came from ADD CHALLAN) so
      // save() still re-assigns the original challan row instead of treating an
      // edited import as a brand-new line -- see the dblclick handler below.
      source_chl_no: state.item.sourceChlNo, source_sno: state.item.sourceSno };
    if (state.editIndex >= 0) state.lines[state.editIndex] = line; else state.lines.push(line);
    clearItemRow();
    renderItems();
    itemSearch.focus();
  }

  // --- ADD CHALLAN: import a pending Returnable Challan's items for the currently
  // selected party into the grid (apps.returnable_challan owns the data; these are
  // its own read-only endpoints, reused as-is -- see that app's services.py for the
  // "all-or-nothing per line, billed only on Confirm" rules). -----------------------
  function openChallanPicker() {
    var partyCode = field("party_code").value.trim();
    if (!partyCode) { show(formAlert, "Select a party first."); return; }
    challanAlert.hidden = true;
    challanRows.textContent = "";
    getJson(root.dataset.challansForPartyUrl + "?party_code=" + encodeURIComponent(partyCode)).then(function (res) {
      var list = (res.ok && res.body.challans) || [];
      if (!list.length) {
        var tr = document.createElement("tr");
        tr.className = "empty";
        var td = document.createElement("td");
        td.colSpan = 3;
        td.textContent = "No pending challans for this party.";
        tr.appendChild(td);
        challanRows.appendChild(tr);
      } else {
        list.forEach(function (c) {
          var tr = document.createElement("tr");
          tr.append(cell(c.chl_no), cell(dmy(c.chl_date)), cell(c.item_count, "num"));
          tr.addEventListener("click", function () { importChallan(c.chl_no, partyCode); });
          challanRows.appendChild(tr);
        });
      }
      challanDialog.showModal();
    });
  }

  function importChallan(chlNo, partyCode) {
    if (state.lines.length) {
      askConfirm("This invoice already has items. Append the challan's items to them?", function () { doImportChallan(chlNo, partyCode); });
    } else {
      doImportChallan(chlNo, partyCode);
    }
  }

  function doImportChallan(chlNo, partyCode) {
    getJson(root.dataset.challanItemsUrlTemplate.replace("__CHLNO__", encodeURIComponent(chlNo)) + "?party_code=" + encodeURIComponent(partyCode))
      .then(function (res) {
        if (!res.ok) { challanAlert.textContent = res.body.message || "Could not load that challan."; challanAlert.hidden = false; return; }
        res.body.items.forEach(function (it) {
          state.lines.push({
            item_code: it.item_code, item_name: it.item_name, hsn_code: it.hsn_code, unit: it.unit,
            order_no: it.order_no, qty: num(it.qty), rate: num(it.rate), dis: 0, gst: num(it.gst_pct),
            active: true, particular: it.particular || "",
            source_chl_no: chlNo, source_sno: it.sno, // only present on challan-sourced lines -- see save()
          });
        });
        challanDialog.close();
        renderItems();
      });
  }

  document.querySelector("[data-add-challan]").addEventListener("click", openChallanPicker);
  document.querySelector("[data-challan-close]").addEventListener("click", function () { challanDialog.close(); });

  // Double-click loads a line back into the entry fields for editing (same as before).
  itemRows.addEventListener("dblclick", function (e) {
    var tr = e.target.closest("tr[data-index]");
    if (!tr || dialog.dataset.readonly === "1") return;
    var i = Number(tr.dataset.index), l = state.lines[i];
    state.editIndex = i;
    state.item = { code: l.item_code, name: l.item_name, unit: l.unit, hsn: l.hsn_code, gst: l.gst,
      sourceChlNo: l.source_chl_no, sourceSno: l.source_sno };
    itemSearch.value = l.item_name;
    form.querySelector("[data-item-code]").value = l.item_code;
    form.querySelector("[data-item-unit]").value = l.unit;
    form.querySelector("[data-item-hsn]").value = l.hsn_code;
    form.querySelector("[data-item-order]").value = l.order_no;
    form.querySelector("[data-item-qty]").value = l.qty;
    form.querySelector("[data-item-rate]").value = l.rate;
    form.querySelector("[data-item-dis]").value = l.dis;
    form.querySelector("[data-item-particular]").value = l.particular || "";
    renderItems();
    form.querySelector("[data-item-qty]").focus();
  });

  // Space toggles a line between active and inactive (struck through, dimmed,
  // excluded from totals) instead of deleting it outright. The item stays in
  // state.lines either way, so it's still there (with its active flag) when saved.
  itemRows.addEventListener("keydown", function (e) {
    var tr = e.target.closest("tr[data-index]");
    if (!tr || dialog.dataset.readonly === "1") return;
    if (e.key === " ") {
      e.preventDefault();
      var l = state.lines[Number(tr.dataset.index)];
      l.active = l.active === false; // flip: undefined/true -> false, false -> true
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
      field("phone").value = p.phone;
      form.querySelector("[data-supply-type]").value = p.supply_type === "I" ? "I" : "W";
      field("gst_no").focus();
    });
  }

  function applyCashMode() {
    var cash = form.querySelector('[data-ca-cr]').value === "CA";
    cashRows.forEach(function (el) { el.hidden = !cash; });
    partySearch.closest("label").hidden = cash;
    form.querySelector('[data-field="gst_no"]').closest("label").hidden = cash;
    form.querySelector('[data-field="phone"]').closest("label").hidden = cash;
  }
  form.querySelector('[data-ca-cr]').addEventListener("change", applyCashMode);

  // Header focus chain (Date through Place of Supply -- see the onEnterFocus comment
  // near the top of this file for the full sequence). Party -> GST No is wired via
  // fillParty() above instead, since that's where the party gets filled in.
  onEnterFocus(field("date"), form.querySelector('[data-ca-cr]'));
  onEnterFocus(form.querySelector('[data-ca-cr]'), form.querySelector('[data-chk-order]'));
  onEnterFocus(form.querySelector('[data-chk-order]'), form.querySelector('[data-supply-type]'));
  onEnterFocus(form.querySelector('[data-supply-type]'), partySearch);
  onEnterFocus(field("gst_no"), field("consignee_name"));
  onEnterFocus(field("consignee_name"), field("consignee_address"));
  onEnterFocus(field("consignee_address"), field("phone"));
  onEnterFocus(field("phone"), field("gr_no"));
  onEnterFocus(field("gr_no"), field("gr_date"));
  onEnterFocus(field("gr_date"), field("vehicle_no"));
  onEnterFocus(field("vehicle_no"), field("transport"));
  onEnterFocus(field("transport"), field("order_no"));
  onEnterFocus(field("order_no"), field("order_date"));
  onEnterFocus(field("order_date"), field("date_of_supply"));
  onEnterFocus(field("date_of_supply"), field("time_of_supply"));
  onEnterFocus(field("time_of_supply"), field("place_of_supply"));
  onEnterFocus(field("place_of_supply"), itemSearch);

  function setReadonly(on) {
    dialog.dataset.readonly = on ? "1" : "0";
    form.querySelectorAll("input:not([type=hidden]), select").forEach(function (el) { el.readOnly = on; });
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
    state.key = mode === "add" ? null : row.bill_no;
    state.keyDiv = mode === "add" ? null : row.div;
    state.keyVouNo = mode === "add" ? null : row.vou_no;
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
      field("due_balance").value = "0.00";
      form.querySelector("[data-supply-type]").value = "W";
      form.querySelector("[data-reverse-charge]").value = "N";
      applyCashMode();
      setReadonly(false);
      renderItems();
      dialog.showModal();
      field("date").focus();
      return;
    }
    var detailUrl = root.dataset.detailUrlTemplate.replace("__NO__", encodeURIComponent(row.bill_no));
    detailUrl += "?div=" + encodeURIComponent(row.div) + "&vou_no=" + encodeURIComponent(row.vou_no);
    getJson(detailUrl).then(function (res) {
      if (!res.ok) { show(alertBox, res.body.message || "Could not open the Spare Part invoice."); return; }
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
      field("due_balance").value = d.due_balance;
      state.lines = d.items.map(function (i) {
        return { item_code: i.item_code, item_name: i.item_name, hsn_code: i.hsn_code, unit: i.unit,
          order_no: i.order_no, qty: num(i.qty), rate: num(i.rate), dis: 0, gst: num(i.gst_pct),
          active: i.active !== false, particular: i.particular || "" };
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
      key_div: state.mode === "modify" ? state.keyDiv : null,
      key_vou_no: state.mode === "modify" ? state.keyVouNo : null,
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
        return { item_code: l.item_code, order_no: l.order_no, qty: l.qty, rate: l.rate, dis_pct: l.dis,
          active: l.active !== false, particular: l.particular || "",
          source_chl_no: l.source_chl_no || "", source_sno: l.source_sno };
      }),
    };
    post(root.dataset.saveUrl, payload).then(function (res) {
      if (!res.ok) {
        show(formAlert, res.body.message || "Could not save the Spare Part invoice.");
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
    confirmDialog.querySelector("[data-confirm-message]").textContent = message;
    confirmDialog.showModal();
    var yesBtn = confirmDialog.querySelector("[data-confirm-yes]");
    var noBtn = confirmDialog.querySelector("[data-confirm-no]");
    function cleanup() {
      yesBtn.removeEventListener("click", onYesClick);
      noBtn.removeEventListener("click", onNoClick);
    }
    function onYesClick() { cleanup(); confirmDialog.close(); onYes(); }
    function onNoClick() { cleanup(); confirmDialog.close(); }
    yesBtn.addEventListener("click", onYesClick);
    noBtn.addEventListener("click", onNoClick);
  }

  form.querySelector("[data-item-add]").addEventListener("click", addItem);
  // Item-entry focus chain: Part (via fillItem(), above) -> Unit -> HSN -> Ord.No ->
  // Dis % -> Qty -> Rate -> OK. Only Rate's Enter actually adds the row.
  onEnterFocus(form.querySelector("[data-item-unit]"), form.querySelector("[data-item-hsn]"));
  onEnterFocus(form.querySelector("[data-item-hsn]"), form.querySelector("[data-item-order]"));
  onEnterFocus(form.querySelector("[data-item-order]"), form.querySelector("[data-item-dis]"));
  onEnterFocus(form.querySelector("[data-item-dis]"), form.querySelector("[data-item-qty]"));
  onEnterFocus(form.querySelector("[data-item-qty]"), form.querySelector("[data-item-rate]"));
  form.querySelector("[data-item-rate]").addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); addItem(); }
  });
  field("freight").addEventListener("input", updateTotals);
  field("freight_gst_pct").addEventListener("input", updateTotals);
  [0, 1].forEach(function (i) {
    form.querySelector('[data-adj-sign="' + i + '"]').addEventListener("change", updateTotals);
    form.querySelector('[data-adj-amount="' + i + '"]').addEventListener("input", updateTotals);
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
      else if (a === "delete") { if (selectedRow()) deleteDialog.showModal(); }
      else if (a === "print") {
        var row = selectedRow();
        if (row) {
          var url = root.dataset.printUrlTemplate.replace("__NO__", encodeURIComponent(row.bill_no));
          url += "?div=" + encodeURIComponent(row.div) + "&vou_no=" + encodeURIComponent(row.vou_no);
          window.open(url, "_blank");
        }
      }
      else if (a === "refresh") refresh();
      else if (a === "exit") window.location.href = root.dataset.exitUrl;
    });
  });

  deleteDialog.querySelector("[data-delete-yes]").addEventListener("click", function () {
    var row = selectedRow();
    deleteDialog.close();
    if (!row) return;
    post(root.dataset.deleteUrl, { bill_no: row.bill_no, div: row.div, vou_no: row.vou_no }).then(function (res) {
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
  applyCashMode();
  refresh();
})();
