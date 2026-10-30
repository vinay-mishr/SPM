/* Sale Order Entry -- VFP SALE ORDER FORM: list, ADD / MODIFY / DELETE / VIEW and the order grid. */
(function () {
  "use strict";

  var root = document.querySelector("[data-so]");
  if (!root) return;

  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var canEdit = root.dataset.canEdit === "1";
  var initial = JSON.parse(document.getElementById("so-initial-data").textContent);
  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var search = root.querySelector("[data-search]");
  var toast = document.querySelector("[data-toast]");
  var dialog = document.querySelector("[data-form]");
  var form = dialog.querySelector("[data-so-form]");
  var formAlert = dialog.querySelector("[data-form-alert]");
  var gridRows = dialog.querySelector("[data-grid-rows]");
  var partySearch = form.querySelector("[data-party-search]");
  var itemSearch = form.querySelector("[data-item-search]");
  var itemCode = form.querySelector("[data-item-code]");
  var itemError = form.querySelector("[data-item-error]");
  var confirmBtn = form.querySelector("[data-confirm]");
  var deleteConfirmBtn = form.querySelector("[data-delete-confirm]");

  var state = { rows: [], selected: null, mode: "add", lines: [], editIndex: -1, item: null };
  var MODES = { add: "Add", modify: "Modify", view: "View", delete: "Delete" };

  function num(v) { return Number(v) || 0; }
  function f2(v) { return (Math.round(v * 100) / 100).toFixed(2); }
  function fQty(v) { return String(Math.round(v)); }
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

  /* --- List ----------------------------------------------------------------------- */

  function selectedRow() { return state.rows.find(function (r) { return r.order_no === state.selected; }) || null; }

  function updateToolbar() {
    var on = !!state.selected;
    root.querySelectorAll('[data-action="modify"], [data-action="delete"], [data-action="view"], [data-action="print"]').forEach(function (b) {
      b.disabled = !on || (b.dataset.action !== "view" && !canEdit);
    });
  }

  function renderList() {
    tbody.textContent = "";
    state.rows.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.dataset.id = r.order_no;
      if (r.order_no === state.selected) tr.classList.add("is-selected");
      tr.append(cell(r.div), cell(r.order_no, "master-table__code"), cell(dmy(r.date)), cell(r.party_name),
        cell(r.city), cell(r.net_amount, "num"));
      tr.addEventListener("click", function () { state.selected = r.order_no; renderList(); updateToolbar(); });
      tr.addEventListener("dblclick", function () { state.selected = r.order_no; openForm("view"); });
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

  /* --- Totals (mirrors the server rules) -------------------------------------------- */

  function lineValues(l) {
    var amount = Math.round(l.qty * l.rate * 100) / 100;
    var disAmt = Math.round(amount * l.dis / 100 * 100) / 100;
    var addAmt = Math.round((amount - disAmt) * l.addDis / 100 * 100) / 100;
    return { amount: amount, disAmt: disAmt, addAmt: addAmt, net: amount - disAmt - addAmt };
  }

  function updateTotals() {
    var t = { amount: 0, disAmt: 0, addAmt: 0, net: 0 };
    state.lines.forEach(function (l) {
      var v = lineValues(l);
      t.amount += v.amount; t.disAmt += v.disAmt; t.addAmt += v.addAmt; t.net += v.net;
    });
    form.querySelector("[data-total]").value = f2(t.amount);
    form.querySelector("[data-discount]").value = f2(t.disAmt);
    form.querySelector("[data-add-discount]").value = f2(t.addAmt);
    form.querySelector("[data-net]").value = f2(t.net);
  }

  function renderGrid() {
    gridRows.textContent = "";
    state.lines.forEach(function (l, i) {
      var v = lineValues(l);
      var tr = document.createElement("tr");
      tr.tabIndex = 0;
      tr.append(cell(i + 1), cell(l.code, "master-table__code"), cell(l.name), cell(f2(l.dis), "num"),
        cell(f2(l.addDis), "num"), cell(fQty(l.qty), "num"), cell(f2(l.rate), "num"), cell(f2(v.amount), "num"));
      tr.addEventListener("dblclick", function () { editLine(i); });
      tr.addEventListener("keydown", function (e) {
        if (e.key === "Delete") {
          window.askConfirm("Delete this row?", function () {
            state.lines.splice(i, 1);
            renderGrid();
            updateTotals();
          });
        }
      });
      gridRows.appendChild(tr);
    });
    updateTotals();
  }

  /* --- Item line -------------------------------------------------------------------- */

  function clearItemRow() {
    state.item = null;
    state.editIndex = -1;
    itemSearch.value = "";
    itemCode.value = "";
    form.querySelector("[data-item-dis]").value = "0.00";
    form.querySelector("[data-item-add-dis]").value = "0.00";
    form.querySelector("[data-item-qty]").value = "0";
    form.querySelector("[data-item-rate]").value = "0.00";
    form.querySelector("[data-item-srate]").value = "0.00";
    itemError.textContent = "";
  }

  /* S.RATE -- the per-unit rate after DIS% and ADDL.DIS% are taken off RATE,
     matching lineValues()'s own amount -> disAmt -> addAmt chain (just per unit
     instead of for the whole line). Kept live so it always reflects whatever is
     currently typed in RATE / DIS% / ADDL.DIS%, even before OK is pressed. */
  function updateSRate() {
    var rate = num(form.querySelector("[data-item-rate]").value);
    var dis = num(form.querySelector("[data-item-dis]").value);
    var addDis = num(form.querySelector("[data-item-add-dis]").value);
    var afterDis = rate - rate * dis / 100;
    var sRate = afterDis - afterDis * addDis / 100;
    form.querySelector("[data-item-srate]").value = f2(sRate);
  }
  [["data-item-rate"], ["data-item-dis"], ["data-item-add-dis"]].forEach(function (sel) {
    form.querySelector("[" + sel[0] + "]").addEventListener("input", updateSRate);
  });

  function fillItem(code) {
    getJson(root.dataset.itemUrl + "?code=" + encodeURIComponent(code)).then(function (res) {
      if (!res.ok) { itemError.textContent = res.body.message || "Item not found."; return; }
      var p = res.body;
      state.item = { code: p.code, name: p.name };
      itemSearch.value = p.name;
      itemCode.value = p.code;
      form.querySelector("[data-item-rate]").value = p.rate;
      itemError.textContent = "";
      updateSRate();
      form.querySelector("[data-item-dis]").focus();
    });
  }

  function editLine(i) {
    var l = state.lines[i];
    state.editIndex = i;
    state.item = { code: l.code, name: l.name };
    itemSearch.value = l.name;
    itemCode.value = l.code;
    form.querySelector("[data-item-dis]").value = f2(l.dis);
    form.querySelector("[data-item-add-dis]").value = f2(l.addDis);
    form.querySelector("[data-item-qty]").value = fQty(l.qty);
    form.querySelector("[data-item-rate]").value = f2(l.rate);
    form.querySelector("[data-item-srate]").value = f2(l.sRate);
    state.lines.splice(i, 1);
    renderGrid();
    var qtyField = form.querySelector("[data-item-qty]");
    qtyField.focus();
    qtyField.select();
  }

  function addItem() {
    itemError.textContent = "";
    if (!state.item) { itemError.textContent = "Select an item."; itemSearch.focus(); return; }
    var qty = num(form.querySelector("[data-item-qty]").value);
    var rate = num(form.querySelector("[data-item-rate]").value);
    if (!(qty > 0)) { itemError.textContent = "Quantity must be greater than zero."; return; }
    if (qty !== Math.round(qty)) { itemError.textContent = "Quantity must be a whole number."; return; }
    if (rate < 0) { itemError.textContent = "Rate can't be negative."; return; }
    if (state.lines.some(function (l) { return l.code === state.item.code; })) {
      itemError.textContent = "Entry Already Exists....";
      return;
    }
    var line = {
      code: state.item.code, name: state.item.name,
      dis: num(form.querySelector("[data-item-dis]").value),
      addDis: num(form.querySelector("[data-item-add-dis]").value),
      qty: qty, rate: rate, sRate: num(form.querySelector("[data-item-srate]").value),
    };
    state.lines.push(line);
    clearItemRow();
    renderGrid();
    itemSearch.focus();
  }

  /* --- Form ----------------------------------------------------------------------- */

  function setMode(mode) {
    state.mode = mode;
    dialog.dataset.mode = mode;
    dialog.querySelector("[data-mode-label]").textContent = MODES[mode];
    var readOnly = mode === "view" || mode === "delete";
    form.querySelectorAll("input:not([type=hidden]):not([readonly])").forEach(function (el) { el.readOnly = readOnly; });
    partySearch.readOnly = readOnly;
    itemSearch.readOnly = readOnly;
    field("order_no").readOnly = mode !== "add";
    field("currency").disabled = readOnly;
    confirmBtn.hidden = readOnly;
    deleteConfirmBtn.hidden = mode !== "delete";
    form.querySelector("[data-item-ok]").hidden = readOnly;
  }

  function fillHeader(d) {
    field("order_no").value = d.order_no;
    field("order_date").value = dmy(d.order_date);
    field("party_code").value = d.party_code;
    partySearch.value = d.party_name;
    field("city").value = d.city;
    field("po_no").value = d.po_no;
    field("po_date").value = dmy(d.po_date);
    field("rep_code").value = d.rep_code;
    field("rep_name").value = d.rep_name;
    field("del_days").value = d.del_days;
    field("del_period").value = d.del_period;
    field("cr_days").value = d.cr_days;
    ensureCurrency(d.currency);
  }

  function openForm(mode) {
    var row = selectedRow();
    if (mode !== "add" && !row) return;
    showFormAlert("");
    clearItemRow();
    form.reset();
    state.lines = [];
    if (mode === "add") {
      getJson(root.dataset.nextNoUrl).then(function (res) {
        field("order_no").value = res.body.order_no;
      });
      field("order_date").value = dmy(new Date().toISOString().slice(0, 10));
      partySearch.value = "";
      field("party_code").value = "";
      field("del_days").value = "0";
      field("cr_days").value = "0";
      ensureCurrency("RS.");
      setMode("add");
      renderGrid();
      dialog.showModal();
      partySearch.focus();
      return;
    }
    getJson(root.dataset.detailUrlTemplate.replace("__NO__", encodeURIComponent(row.order_no))).then(function (res) {
      if (!res.ok) { showToast(res.body.message || "Could not load the order.", "error"); return; }
      fillHeader(res.body);
      state.lines = res.body.lines.map(function (l) {
        return { code: l.code, name: l.name, dis: num(l.dis), addDis: num(l.add_dis), qty: num(l.qty),
          rate: num(l.rate), sRate: num(l.s_rate) };
      });
      setMode(mode);
      renderGrid();
      dialog.showModal();
    });
  }

  function closeForm() {
    if (dialog.open) dialog.close();
  }

  function payload() {
    return {
      mode: state.mode,
      order_no: field("order_no").value.trim(),
      order_date: window.DateMask.toIso(field("order_date").value),
      party_code: field("party_code").value.trim(),
      po_no: field("po_no").value.trim(),
      po_date: window.DateMask.toIso(field("po_date").value),
      del_days: field("del_days").value,
      del_period: field("del_period").value.trim(),
      cr_days: field("cr_days").value,
      currency: field("currency").value.trim(),
      lines: state.lines.map(function (l) {
        return { code: l.code, dis: l.dis, add_dis: l.addDis, qty: l.qty, rate: l.rate, s_rate: l.sRate };
      }),
    };
  }

  function confirm() {
    showFormAlert("");
    if (!state.lines.length) { showFormAlert("Add at least one item."); return; }
    window.askConfirm("Are You Sure?", function () {
      post(payload()).then(function (res) {
        if (!res.ok) {
          showFormAlert(res.body.message || "Could not save the sale order.");
          var first = Object.keys(res.body.errors || {})[0];
          if (first && field(first)) field(first).focus();
          return;
        }
        showToast(res.body.message);
        closeForm();
        state.selected = res.body.order_no;
        refresh();
      });
    });
  }

  function confirmDelete() {
    var orderNo = field("order_no").value.trim();
    if (!orderNo) return;
    window.askConfirm("Delete sale order " + orderNo + "?", function () {
      post({ mode: "delete", order_no: orderNo }).then(function (res) {
        if (!res.ok) { showFormAlert(res.body.message || "Could not delete."); return; }
        showToast(res.body.message);
        closeForm();
        state.selected = null;
        refresh();
      });
    });
  }

  /* --- Help lookups ----------------------------------------------------------------- */

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
        field("cr_days").value = res.body.cr_days;
        form.querySelector("[data-item-dis]").value = f2(res.body.dis);
        form.querySelector("[data-item-add-dis]").value = f2(res.body.add_dis);
        field("order_date").focus();
      });
    },
  });

  window.HelpLookup.attach(itemSearch, {
    endpoint: root.dataset.itemsUrl, resultsKey: "items", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "unit", label: "Unit" }],
    title: "Item",
    onSelect: function (row) { fillItem(row.code); },
  });

  /* --- Wiring ----------------------------------------------------------------------- */

  form.querySelector("[data-item-ok]").addEventListener("click", addItem);

  /* Keyboard focus order (per spec): O.R.S.NO -> PARTY -> DATE -> P.O.NO -> P.O.DATE
     -> ITEM DESCRIPTION/CODE -> DIS% -> ADDL.DIS% -> QTY -> RATE -> S.RATE -> OK
     (adds the item, then returns focus to ITEM DESCRIPTION/CODE).
     PARTY and ITEM DESCRIPTION/CODE keep their existing Enter-opens-Help-popup
     behavior (wired via HelpLookup.attach above); their onSelect callbacks already
     carry focus on to DATE / DIS% respectively, so they need no handler here. */
  function onEnterFocus(el, next) {
    el.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); next.focus(); if (next.select) next.select(); }
    });
  }
  onEnterFocus(field("order_no"), partySearch);
  onEnterFocus(field("order_date"), field("po_no"));
  onEnterFocus(field("po_no"), field("po_date"));
  onEnterFocus(field("po_date"), itemSearch);
  onEnterFocus(form.querySelector("[data-item-dis]"), form.querySelector("[data-item-add-dis]"));
  onEnterFocus(form.querySelector("[data-item-add-dis]"), form.querySelector("[data-item-qty]"));
  onEnterFocus(form.querySelector("[data-item-qty]"), form.querySelector("[data-item-rate]"));
  onEnterFocus(form.querySelector("[data-item-rate]"), form.querySelector("[data-item-srate]"));
  form.querySelector("[data-item-srate]").addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); addItem(); }
  });
  confirmBtn.addEventListener("click", confirm);
  deleteConfirmBtn.addEventListener("click", confirmDelete);
  dialog.querySelectorAll("[data-cancel]").forEach(function (b) { b.addEventListener("click", closeForm); });

  root.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var action = btn.dataset.action;
      if (action === "add") openForm("add");
      else if (action === "modify") openForm("modify");
      else if (action === "view") openForm("view");
      else if (action === "delete") openForm("delete");
      else if (action === "print") window.open(root.dataset.printUrlTemplate.replace("__NO__", encodeURIComponent(selectedRow().order_no)), "_blank");
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
