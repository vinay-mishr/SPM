/* Spare Sale Order > Entry: list, ADD / MODIFY / DELETE / VIEW and the order grid. */
(function () {
  "use strict";

  var root = document.querySelector("[data-spare]");
  if (!root) return;

  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var canEdit = root.dataset.canEdit === "1";
  var initial = JSON.parse(document.getElementById("sp-initial-data").textContent);
  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var search = root.querySelector("[data-search]");
  var toast = document.querySelector("[data-toast]");
  var dialog = document.querySelector("[data-form]");
  var form = dialog.querySelector("[data-spare-form]");
  var formAlert = dialog.querySelector("[data-form-alert]");
  var gridRows = dialog.querySelector("[data-grid-rows]");
  var partySearch = form.querySelector("[data-party-search]");
  var itemSearch = form.querySelector("[data-item-search]");
  var itemCode = form.querySelector("[data-item-code]");
  var itemError = form.querySelector("[data-item-error]");
  var confirmBtn = form.querySelector("[data-confirm]");

  var state = { rows: [], selected: null, mode: "add", lines: [], item: null };
  var MODES = { add: "Add", modify: "Modify", view: "View" };

  function num(v) { return Number(v) || 0; }
  function f2(v) { return (Math.round(v * 100) / 100).toFixed(2); }
  function f3(v) { return (Math.round(v * 1000) / 1000).toFixed(3); }
  function field(name) { return form.querySelector('[data-field="' + name + '"]'); }
  function ensureCurrency(code) {
    code = (code || "RS.").trim().toUpperCase();
    var sel = field("currency");
    var exists = Array.prototype.some.call(sel.options, function (o) { return o.value === code; });
    if (!exists) {
      var opt = document.createElement("option");
      opt.value = code;
      opt.textContent = code;
      sel.appendChild(opt);
    }
    sel.value = code;
  }
  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (cls) td.className = cls;
    return td;
  }
  function dmy(iso) {
    if (!iso) return "";
    var p = String(iso).split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : iso;
  }
  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }
  function showFormAlert(msg) {
    formAlert.textContent = msg || "";
    formAlert.hidden = !msg;
  }
  function getJson(url) {
    return fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); });
  }
  function post(data) {
    return fetch(root.dataset.saveUrl, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrf, "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(data),
    }).then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); });
  }

  function selectedRow() { return state.rows.find(function (r) { return r.key === state.selected; }) || null; }

  function updateToolbar() {
    root.querySelectorAll('[data-action="modify"], [data-action="delete"], [data-action="view"], [data-action="print"]').forEach(function (b) {
      b.disabled = !state.selected || (b.dataset.action !== "view" && b.dataset.action !== "print" && !canEdit);
    });
  }

  function renderList() {
    tbody.textContent = "";
    state.rows.forEach(function (r) {
      var tr = document.createElement("tr");
      if (r.key === state.selected) tr.classList.add("is-selected");
      tr.append(cell(r.order_no, "master-table__code"), cell(dmy(r.date)), cell(r.party_name), cell(r.city), cell(r.amount, "num"));
      tr.addEventListener("click", function () { state.selected = r.key; renderList(); updateToolbar(); });
      tr.addEventListener("dblclick", function () { state.selected = r.key; openForm("view"); });
      tbody.appendChild(tr);
    });
    emptyNote.hidden = state.rows.length > 0;
    updateToolbar();
  }

  function refresh() {
    var params = new URLSearchParams();
    params.set("start_date", window.DateMask.toIso(startDate.value));
    params.set("end_date", window.DateMask.toIso(endDate.value));
    params.set("search", search.value.trim());
    getJson(root.dataset.listUrl + "?" + params.toString()).then(function (res) {
      if (!res.ok) { showToast(res.body.message || "Could not load the orders.", "error"); return; }
      state.rows = res.body.rows;
      if (!selectedRow()) state.selected = null;
      renderList();
    });
  }

  function lineAmount(l) { return Math.round(l.qty * l.rate * 100) / 100; }
  function lineDisAmt(l) { return Math.round(lineAmount(l) * l.dis) / 100; }

  function updateTotals() {
    var gross = 0, lineDis = 0;
    state.lines.forEach(function (l) { gross += lineAmount(l); lineDis += lineDisAmt(l); });
    var subtotal = gross - lineDis;
    var addlPct = num(form.querySelector("[data-addl-dis-pct]").value);
    var addlAmt = Math.round(subtotal * addlPct) / 100;
    var net = subtotal - addlAmt;
    form.querySelector("[data-total]").value = f2(gross);
    form.querySelector("[data-discount]").value = f2(lineDis);
    form.querySelector("[data-add-discount]").value = f2(addlAmt);
    form.querySelector("[data-net]").value = f2(net);
  }
  form.querySelector("[data-addl-dis-pct]").addEventListener("input", renderGrid);

  function renderGrid() {
    gridRows.textContent = "";
    // ADDL. DIS is order-wide (one %, applied once to the order subtotal -- see
    // updateTotals), not stored per item; shown on every row purely for reference,
    // same current value each time, not an independently editable per-line figure.
    var addlPct = num(form.querySelector("[data-addl-dis-pct]").value);
    state.lines.forEach(function (l, i) {
      var tr = document.createElement("tr");
      tr.tabIndex = 0;
      tr.append(cell(i + 1), cell(l.code, "master-table__code"), cell(l.name), cell(f2(l.dis), "num"),
        cell(f2(addlPct), "num"), cell(f3(l.qty), "num"), cell(f2(l.rate), "num"), cell(f2(lineAmount(l)), "num"));
      tr.addEventListener("dblclick", function () { editLine(i); });
      tr.addEventListener("keydown", function (e) {
        if (e.key === "Delete") {
          window.askConfirm("Delete this row?", function () {
            state.lines.splice(i, 1);
            renderGrid();
          });
        }
      });
      gridRows.appendChild(tr);
    });
    updateTotals();
  }

  function clearItemRow() {
    state.item = null;
    itemSearch.value = "";
    itemCode.value = "";
    form.querySelector("[data-item-dis]").value = "0.00";
    form.querySelector("[data-item-qty]").value = "0.000";
    form.querySelector("[data-item-rate]").value = "0.00";
    form.querySelector("[data-item-srate]").value = "0.00";
    itemError.textContent = "";
  }

  function updateSRate() {
    var rate = num(form.querySelector("[data-item-rate]").value);
    var dis = num(form.querySelector("[data-item-dis]").value);
    form.querySelector("[data-item-srate]").value = f2(rate - rate * dis / 100);
  }
  [["data-item-rate"], ["data-item-dis"]].forEach(function (sel) {
    form.querySelector("[" + sel[0] + "]").addEventListener("input", updateSRate);
  });

  function fillItem(code) {
    getJson(root.dataset.itemUrl + "?code=" + encodeURIComponent(code)).then(function (res) {
      if (!res.ok) { itemError.textContent = res.body.message || "Item not found."; return; }
      state.item = { code: res.body.code, name: res.body.name };
      itemSearch.value = res.body.name;
      itemCode.value = res.body.code;
      form.querySelector("[data-item-rate]").value = res.body.rate;
      itemError.textContent = "";
      updateSRate();
      var disField = form.querySelector("[data-item-dis]");
      disField.focus();
      disField.select();
    });
  }

  function editLine(i) {
    var l = state.lines[i];
    state.item = { code: l.code, name: l.name };
    itemSearch.value = l.name;
    itemCode.value = l.code;
    form.querySelector("[data-item-dis]").value = f2(l.dis);
    form.querySelector("[data-item-qty]").value = f3(l.qty);
    form.querySelector("[data-item-rate]").value = f2(l.rate);
    updateSRate();
    state.lines.splice(i, 1);
    renderGrid();
    var qtyField = form.querySelector("[data-item-qty]");
    qtyField.focus();
    qtyField.select();
  }

  function addItem() {
    itemError.textContent = "";
    if (!state.item) { itemError.textContent = "Select an item."; itemSearch.focus(); return; }
    var dis = num(form.querySelector("[data-item-dis]").value);
    var qty = num(form.querySelector("[data-item-qty]").value);
    var rate = num(form.querySelector("[data-item-rate]").value);
    if (!(qty > 0)) { itemError.textContent = "Quantity must be greater than zero."; return; }
    if (rate < 0) { itemError.textContent = "Rate can't be negative."; return; }
    if (dis < 0 || dis > 100) { itemError.textContent = "Discount % must be between 0 and 100."; return; }
    if (state.lines.some(function (l) { return l.code === state.item.code; })) {
      itemError.textContent = "Entry Already Exists....";
      return;
    }
    state.lines.push({ code: state.item.code, name: state.item.name, qty: qty, rate: rate, dis: dis });
    clearItemRow();
    renderGrid();
    itemSearch.focus();
  }

  function setMode(mode) {
    state.mode = mode;
    dialog.dataset.mode = mode;
    dialog.querySelector("[data-mode-label]").textContent = MODES[mode];
    var readOnly = mode === "view";
    form.querySelectorAll("input:not([type=hidden]):not([readonly])").forEach(function (el) { el.readOnly = readOnly; });
    field("order_no").readOnly = mode !== "add";
    field("currency").disabled = readOnly;
    confirmBtn.hidden = readOnly;
    form.querySelector("[data-item-ok]").hidden = readOnly;
  }

  function fillHeader(d) {
    field("order_no").value = d.order_no;
    field("order_date").value = dmy(d.order_date);
    field("party_code").value = d.party_code;
    partySearch.value = d.party_name;
    field("city").value = d.city;
    field("rep_code").value = d.rep_code;
    field("rep_name").value = d.rep_name;
    field("po_no").value = d.po_no;
    field("po_date").value = dmy(d.po_date);
    field("remarks").value = d.remarks;
    field("remarks1").value = d.remarks1;
    ensureCurrency(d.currency);
    // ord_mst1 only stores the resulting ADD. DISCOUNT amount, not the % that
    // produced it, so the % input can't be restored on reload -- left at 0.
    form.querySelector("[data-addl-dis-pct]").value = "0.00";
  }

  function openForm(mode) {
    var row = selectedRow();
    if (mode !== "add" && !row) return;
    showFormAlert("");
    clearItemRow();
    form.reset();
    state.lines = [];
    if (mode === "add") {
      getJson(root.dataset.nextNoUrl).then(function (res) { field("order_no").value = res.body.order_no; });
      var now = new Date();
      var pad = function (n) { return String(n).padStart(2, "0"); };
      field("order_date").value = pad(now.getDate()) + "/" + pad(now.getMonth() + 1) + "/" + now.getFullYear();
      partySearch.value = "";
      field("party_code").value = "";
      ensureCurrency("RS.");
      setMode("add");
      renderGrid();
      dialog.showModal();
      partySearch.focus();
      return;
    }
    var detailUrl = root.dataset.detailUrlTemplate.replace("__NO__", encodeURIComponent(row.order_no));
    detailUrl += "?div=" + encodeURIComponent(row.div);
    getJson(detailUrl).then(function (res) {
      if (!res.ok) { showToast(res.body.message || "Could not load the order.", "error"); return; }
      fillHeader(res.body);
      state.lines = res.body.lines.map(function (l) { return { code: l.code, name: l.name, qty: num(l.qty), rate: num(l.rate), dis: num(l.dis) }; });
      setMode(mode);
      renderGrid();
      dialog.showModal();
    });
  }

  function payload() {
    return {
      mode: state.mode,
      order_no: field("order_no").value.trim(),
      order_date: window.DateMask.toIso(field("order_date").value),
      party_code: field("party_code").value.trim(),
      po_no: field("po_no").value.trim(),
      po_date: window.DateMask.toIso(field("po_date").value),
      remarks: field("remarks").value.trim(),
      remarks1: field("remarks1").value.trim(),
      currency: field("currency").value.trim(),
      addl_dis_pct: form.querySelector("[data-addl-dis-pct]").value,
      lines: state.lines.map(function (l) { return { code: l.code, qty: l.qty, rate: l.rate, dis: l.dis }; }),
    };
  }

  function confirm() {
    showFormAlert("");
    if (!state.lines.length) { showFormAlert("Add at least one item."); return; }
    window.askConfirm("Are You Sure?", function () {
      post(payload()).then(function (res) {
        if (!res.ok) {
          showFormAlert(res.body.message || "Could not save the spare sale order.");
          var first = Object.keys(res.body.errors || {})[0];
          if (first && field(first)) field(first).focus();
          return;
        }
        showToast(res.body.message);
        dialog.close();
        // Every save (add or modify) is always against div='SP' server-side
        // (see spare_save()), matching the list's own composite key shape.
        state.selected = res.body.order_no + "|SP";
        refresh();
      });
    });
  }

  function deleteOrder() {
    var row = selectedRow();
    if (!row) return;
    window.askConfirm("Delete spare sale order " + row.order_no + "?", function () {
      post({ mode: "delete", order_no: row.order_no }).then(function (res) {
        if (!res.ok) { showToast(res.body.message || "Could not delete.", "error"); return; }
        showToast(res.body.message);
        state.selected = null;
        refresh();
      });
    });
  }

  window.HelpLookup.attach(partySearch, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Party",
    onSelect: function (p) {
      getJson(root.dataset.partyUrl + "?code=" + encodeURIComponent(p.code)).then(function (res) {
        if (!res.ok) { showFormAlert(res.body.message); return; }
        field("party_code").value = res.body.code;
        partySearch.value = res.body.name;
        field("city").value = res.body.city;
        field("rep_code").value = res.body.rep_code;
        field("rep_name").value = res.body.rep_name;
        form.querySelector("[data-addl-dis-pct]").value = f2(num(res.body.add_dis));
        updateTotals();
        itemSearch.focus();
      });
    },
  });

  window.HelpLookup.attach(itemSearch, {
    endpoint: root.dataset.partsUrl, resultsKey: "parts", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }],
    title: "Item",
    onSelect: function (row) { fillItem(row.code); },
  });

  form.querySelector("[data-item-ok]").addEventListener("click", addItem);

  /* Item row focus order: Item -> Dis% -> Addl.Dis% -> Qty -> Rate -> S.Rate -> OK
     (which adds the line and returns focus to Item, see addItem() above). */
  function onEnterFocus(el, next) {
    el.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      e.preventDefault();
      next.focus();
      if (next.select) next.select();
    });
  }
  onEnterFocus(form.querySelector("[data-item-dis]"), form.querySelector("[data-addl-dis-pct]"));
  onEnterFocus(form.querySelector("[data-addl-dis-pct]"), form.querySelector("[data-item-qty]"));
  onEnterFocus(form.querySelector("[data-item-qty]"), form.querySelector("[data-item-rate]"));
  onEnterFocus(form.querySelector("[data-item-rate]"), form.querySelector("[data-item-srate]"));
  form.querySelector("[data-item-srate]").addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); addItem(); }
  });
  confirmBtn.addEventListener("click", confirm);
  dialog.querySelectorAll("[data-cancel]").forEach(function (b) {
    b.addEventListener("click", function () { if (dialog.open) dialog.close(); });
  });

  root.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var action = btn.dataset.action;
      if (action === "add") openForm("add");
      else if (action === "modify") openForm("modify");
      else if (action === "view") openForm("view");
      else if (action === "delete") deleteOrder();
      else if (action === "print") {
        var row = selectedRow();
        window.open(root.dataset.printUrlTemplate.replace("__NO__", encodeURIComponent(row.order_no)) + "?div=" + encodeURIComponent(row.div), "_blank");
      }
      else if (action === "refresh") refresh();
      else if (action === "exit") window.location.href = root.dataset.exitUrl;
    });
  });

  startDate.value = window.DateMask.toDisplay(initial.start_date);
  endDate.value = window.DateMask.toDisplay(initial.end_date);
  startDate.addEventListener("change", refresh);
  endDate.addEventListener("change", refresh);
  search.addEventListener("input", function () { clearTimeout(search._t); search._t = setTimeout(refresh, 250); });
  refresh();
})();
