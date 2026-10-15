(function () {
  var root = document.querySelector("[data-mr]");
  if (!root) return;
  var canEdit = root.dataset.canEdit === "1";

  var rows = root.querySelector("[data-rows]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var search = root.querySelector("[data-search]");
  var alertBox = root.querySelector("[data-alert]");

  var dialog = document.querySelector("[data-form]");
  var form = dialog.querySelector("[data-mr-form]");
  var formAlert = form.querySelector("[data-form-alert]");
  var deleteDialog = document.querySelector("[data-delete-dialog]");
  var confirmDialog = document.querySelector("[data-confirm-dialog]");
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

  var billRows = form.querySelector("[data-bill-rows]");
  var partySearch = form.querySelector("[data-party-search]");
  var partyCodeDisplay = form.querySelector("[data-party-code-display]");
  var bankSearch = form.querySelector("[data-bank-search]");
  var modeSelect = form.querySelector("[data-mode]");

  var allocCashDis = form.querySelector("[data-alloc-cash-dis]");
  var allocTds = form.querySelector("[data-alloc-tds]");
  var allocAmtAdj = form.querySelector("[data-alloc-amt-adj]");
  var allocOkBtn = form.querySelector("[data-alloc-ok]");

  var state = { rows: [], selected: null, mode: "add", bills: [], selectedBillIndex: -1 };

  function field(name) { return form.querySelector('[data-field="' + name + '"]'); }
  function num(v) { var n = parseFloat(v); return isNaN(n) ? 0 : n; }
  function f2(n) { return (Math.round(n * 100) / 100).toFixed(2); }
  function show(el, msg) { el.textContent = msg; el.hidden = !msg; }
  // This screen's own date fields display dd-mm-yyyy (hyphens, matching the
  // real VFP form and this module's own placeholder text) -- distinct from
  // the shared window.DateMask utility used elsewhere in the app, which is
  // slash-separated (dd/mm/yyyy). isoToDmy/dmyToIso/attachHyphenMask are this
  // module's own local equivalents so typing and display actually agree with
  // what the placeholder promises.
  function dmy(iso) {
    if (!iso) return "";
    var p = iso.split("-");
    return p.length === 3 ? p[2] + "-" + p[1] + "-" + p[0] : iso;
  }
  function dmyToIso(d) {
    var p = String(d || "").split("-");
    return p.length === 3 ? p[2] + "-" + p[1] + "-" + p[0] : d;
  }
  function todayDmy() {
    var now = new Date();
    var pad = function (n) { return String(n).padStart(2, "0"); };
    return pad(now.getDate()) + "-" + pad(now.getMonth() + 1) + "-" + now.getFullYear();
  }
  function attachHyphenMask(input) {
    input.addEventListener("input", function () {
      var digits = input.value.replace(/\D/g, "").slice(0, 8);
      var out = digits.slice(0, 2);
      if (digits.length > 2) out += "-" + digits.slice(2, 4);
      if (digits.length > 4) out += "-" + digits.slice(4, 8);
      input.value = out;
    });
  }
  form.querySelectorAll("[data-date-mask]").forEach(attachHyphenMask);
  function onEnterFocus(el, getNext) {
    if (!el) return;
    el.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      e.preventDefault();
      var next = typeof getNext === "function" ? getNext() : getNext;
      if (!next || next.disabled || next.hidden || next.closest("[hidden]")) return;
      next.focus();
      if (next.select) next.select();
    });
  }
  function cell(text, cls) { var td = document.createElement("td"); if (cls) td.className = cls; td.textContent = text == null ? "" : text; return td; }

  function post(url, body) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]").value },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); });
  }
  function getJson(url) {
    return fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); });
  }

  function selectedRow() { return state.rows.find(function (r) { return r.key === state.selected; }) || null; }

  function updateToolbar() {
    var has = Boolean(selectedRow());
    root.querySelectorAll('[data-action="delete"], [data-action="view"]').forEach(function (b) {
      b.disabled = !has || (!canEdit && b.dataset.action !== "view");
    });
  }

  function render() {
    rows.textContent = "";
    state.rows.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.dataset.key = r.key;
      tr.tabIndex = 0;
      if (r.key === state.selected) tr.classList.add("is-selected");
      tr.append(cell(dmy(r.date)), cell(r.party), cell(r.city), cell(r.chq_no), cell(r.total_amount, "num"));
      tr.addEventListener("click", function () { state.selected = r.key; render(); });
      tr.addEventListener("dblclick", function () { state.selected = r.key; open("view"); });
      rows.appendChild(tr);
    });
    if (!state.rows.length) {
      var empty = document.createElement("tr");
      empty.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 5;
      td.textContent = "No Money Receipts in this date range.";
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
      if (!res.ok) { show(alertBox, res.body.message || "Could not load Money Receipts."); return; }
      state.rows = res.body.rows;
      if (!selectedRow()) state.selected = null;
      render();
    });
  }

  // --- mode (CASH/CHEQUE/RTGS) field-layout swap ---------------------------
  function applyModeLayout() {
    var mode = modeSelect.value;
    var chqDateRow = form.querySelector("[data-chq-date-row]");
    var chqNoLabel = form.querySelector("[data-chq-no-label]");
    var dateLabel = form.querySelector("[data-receipt-date-label]");
    // BANK stays visible in every mode (matches the real form's own layout)
    // -- only disabled/cleared for CASH, where there's no bank to record.
    if (mode === "CA") {
      bankSearch.value = "";
      field("bank_code").value = "";
      bankSearch.disabled = true;
      chqDateRow.hidden = true;
      chqNoLabel.firstChild.textContent = "RECEIPT NO ";
      dateLabel.firstChild.textContent = "RECEIPT DATE ";
    } else if (mode === "CH") {
      bankSearch.disabled = false;
      chqDateRow.hidden = false;
      chqNoLabel.firstChild.textContent = "CHEQUE NO. ";
      dateLabel.firstChild.textContent = "CHEQUE DATE ";
    } else {
      bankSearch.disabled = false;
      chqDateRow.hidden = false;
      chqNoLabel.firstChild.textContent = "RTGS NO. ";
      dateLabel.firstChild.textContent = "RTGS DATE ";
    }
  }
  function applyModeDefaults() {
    applyModeLayout();
    field("chq_no").value = "";
    if (modeSelect.value === "CA") {
      // Never stomp a date the user already typed (req: don't overwrite
      // on an unrelated field switch) -- only fill it in when blank.
      if (!field("slip_date").value) field("slip_date").value = todayDmy();
      if (state.mode === "add") {
        getJson(root.dataset.nextCashNoUrl).then(function (res) { field("chq_no").value = res.body.chq_no; });
      }
    } else if (!field("chq_dt").value) {
      field("chq_dt").value = todayDmy();
    }
  }
  modeSelect.addEventListener("change", applyModeDefaults);

  // --- bill grid rendering + allocation (VFP dkgrid / cmdok / caltotal) ----
  function renderBillRows() {
    billRows.textContent = "";
    if (!state.bills.length) {
      var tr = document.createElement("tr");
      tr.className = "empty";
      tr.appendChild(cell("Select a party to load pending bills.", null));
      tr.firstChild.colSpan = 9;
      billRows.appendChild(tr);
      return;
    }
    var shown = 0;
    state.bills.forEach(function (b, i) {
      // Fully adjusted -- amount_adjusted covers the row's entire balance --
      // drops out of the visible list entirely (it's done), rather than
      // lingering greyed out. It's still kept in state.bills so save() still
      // submits it.
      if (b.locked && num(b.amount_adjusted) >= num(b.balance_amt)) return;
      shown += 1;
      var tr = document.createElement("tr");
      tr.dataset.index = i;
      if (b.locked) tr.classList.add("is-locked");
      if (i === state.selectedBillIndex) tr.classList.add("is-selected");
      tr.append(
        cell(shown), cell(b.div), cell(b.bill_no), cell(dmy(b.bill_date)),
        cell(b.inv_amount, "num"), cell(b.locked ? f2(num(b.display_balance)) : b.balance_amt, "num"),
        cell(b.locked ? f2(num(b.cash_discount)) : "", "num"),
        cell(b.locked ? f2(num(b.amount_adjusted)) : "", "num"),
        cell(b.locked ? f2(num(b.running_balance)) : "", "num")
      );
      tr.addEventListener("click", function () { selectBillRow(i); });
      billRows.appendChild(tr);
    });
    if (!shown) {
      var tr = document.createElement("tr");
      tr.className = "empty";
      tr.appendChild(cell("All bills fully adjusted.", null));
      tr.firstChild.colSpan = 9;
      billRows.appendChild(tr);
    }
  }

  function amountReceived() { return num(field("amount_received").value); }

  function remainingBalance() { return num(form.querySelector("[data-balance-amt]").value); }

  // VFP caltotal: cascades remaining-after-allocation balance down the grid,
  // only through rows that have actually been locked in (amount_adjusted>0).
  function caltotal() {
    var mbalance = amountReceived();
    state.bills.forEach(function (b) {
      if (b.locked && num(b.amount_adjusted) > 0) {
        mbalance -= num(b.amount_adjusted);
        b.running_balance = f2(mbalance);
      } else {
        b.running_balance = "";
      }
    });
    form.querySelector("[data-balance-amt]").value = f2(mbalance);
    renderBillRows();
  }

  function selectBillRow(i) {
    var b = state.bills[i];
    state.selectedBillIndex = i;
    renderBillRows();
    if (b.locked) { disableAlloc(); return; }
    if (remainingBalance() > 0) {
      allocCashDis.disabled = false;
      allocTds.disabled = false;
      allocOkBtn.disabled = false;
      allocCashDis.value = "0.00";
      allocTds.value = "0.00";
      // Default to fully settling this row (its whole balance, capped at what's
      // left of the receipt) -- the common case is no discount/TDS at all, so
      // clicking OK right away without touching those fields must still adjust
      // the full amount, not leave it at 0.
      allocAmtAdj.value = f2(Math.min(num(b.balance_amt), remainingBalance()));
      allocCashDis.focus();
    }
  }

  function disableAlloc() {
    allocCashDis.value = "0.00";
    allocTds.value = "0.00";
    allocAmtAdj.value = "0.00";
    allocCashDis.disabled = true;
    allocTds.disabled = true;
    allocOkBtn.disabled = true;
  }

  // Each field's own Valid independently recomputes amount_adj from the row's
  // full balance (not net of the other field) -- ports the real VFP TC_DIS.Valid
  // / TI_AMOUNT.Valid behaviour exactly, quirk included (see services.py docstring).
  function recomputeAmountAdjusted(fieldValue) {
    var b = state.bills[state.selectedBillIndex];
    if (!b) return;
    var balance = num(b.balance_amt);
    if (fieldValue > balance) {
      window.alert("Invalid Amount <<Check Again>>");
      return false;
    }
    var adj = balance - fieldValue;
    if (adj > remainingBalance()) adj = remainingBalance();
    allocAmtAdj.value = f2(adj);
    return true;
  }
  allocCashDis.addEventListener("change", function () {
    if (!recomputeAmountAdjusted(num(allocCashDis.value))) allocCashDis.value = "0.00";
  });
  allocTds.addEventListener("change", function () {
    if (!recomputeAmountAdjusted(num(allocTds.value))) allocTds.value = "0.00";
  });

  allocOkBtn.addEventListener("click", function () {
    var b = state.bills[state.selectedBillIndex];
    if (!b) return;
    b.cash_discount = f2(num(allocCashDis.value));
    b.tds_amt = f2(num(allocTds.value));
    b.amount_adjusted = f2(num(allocAmtAdj.value));
    // What's still due on THIS bill after a partial payment -- balance_amt
    // itself stays the original figure (needed for the fully-adjusted check
    // and for save()'s total-outstanding validation); this is purely what
    // the row displays once locked.
    b.display_balance = f2(Math.max(0, num(b.balance_amt) - num(b.amount_adjusted)));
    b.locked = true;
    disableAlloc();
    caltotal();
  });

  // Space un-locks a committed row and clears its allocation, same convention
  // other modules in this project use for toggling a grid row's state.
  billRows.addEventListener("keydown", function (e) {
    var tr = e.target.closest("tr[data-index]");
    if (!tr || e.key !== " ") return;
    e.preventDefault();
    var b = state.bills[Number(tr.dataset.index)];
    if (b.locked) {
      b.locked = false;
      b.cash_discount = b.tds_amt = b.amount_adjusted = "0.00";
      caltotal();
    }
  });

  // --- party select ----------------------------------------------------------
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
      partyCodeDisplay.value = p.code;
      field("prev_adv").value = f2(num(p.previous_advance));
      form.querySelector("[data-ledger-balance]").value = f2(num(p.ledger_balance));
      var totalOut = (p.pending_bills || []).reduce(function (s, r) { return s + num(r.balance_amt); }, 0);
      form.querySelector("[data-total-outstanding]").value = f2(totalOut);
      state.bills = (p.pending_bills || []).map(function (r) {
        return { div: r.div, bill_no: r.bill_no, bill_date: r.bill_date, inv_amount: r.inv_amount,
          balance_amt: r.balance_amt, bill_type: r.bill_type, locked: false,
          cash_discount: "0.00", tds_amt: "0.00", amount_adjusted: "0.00", running_balance: "" };
      });
      state.selectedBillIndex = -1;
      caltotal();
      renderHistoryRows(p.history_rows || []);
      if (modeSelect.value !== "CA") bankSearch.focus(); else focusFirstBillRow();
    });
  }

  window.HelpLookup.attach(bankSearch, {
    endpoint: root.dataset.ledgersUrl, resultsKey: "ledgers", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }],
    title: "Bank Ledger",
    onSelect: function (row) { field("bank_code").value = row.code; bankSearch.value = row.name; focusFirstBillRow(); },
  });

  // Lands on the first still-pending row's allocation fields -- the closest
  // equivalent to "focus the invoice allocation table" for a dynamically
  // built grid (there's no single static input to tab into otherwise).
  function focusFirstBillRow() {
    var idx = state.bills.findIndex(function (b) { return !b.locked; });
    if (idx >= 0) selectBillRow(idx);
  }

  // --- keyboard chain: RT/CASH/CHEQUE -> Receipt/Cheque Date -> Cheque No ->
  // Amount Received -> Party -> Bank -> grid -> Cash Dis./TDS -> OK. Hidden/
  // disabled fields (Cheque Date in CASH mode, Bank in CASH mode) are skipped
  // automatically since onEnterFocus re-checks at Enter time, not bind time.
  // Party's own Enter (autocomplete select) and Confirm are deliberately left
  // alone so Enter never accidentally submits the form early.
  onEnterFocus(modeSelect, function () { return field("slip_date"); });
  onEnterFocus(field("slip_date"), function () {
    return form.querySelector("[data-chq-date-row]").hidden ? field("chq_no") : field("chq_dt");
  });
  onEnterFocus(field("chq_dt"), function () { return field("chq_no"); });
  onEnterFocus(field("chq_no"), function () { return field("amount_received"); });
  onEnterFocus(field("amount_received"), function () { return partySearch; });
  onEnterFocus(allocCashDis, function () { return allocTds.disabled ? allocOkBtn : allocTds; });
  onEnterFocus(allocTds, function () { return allocOkBtn; });

  // Money Receipt History grid was removed from this form -- kept as a no-op
  // so the open()/fillParty() call sites that feed it data don't need to
  // change too (the API still returns history_rows, just unused here).
  function renderHistoryRows(list) {
  }

  field("amount_received").addEventListener("input", function () {
    form.querySelector("[data-total-amount]").value = f2(amountReceived());
    caltotal();
  });

  // --- open / save / delete ---------------------------------------------------
  function resetForm() {
    form.reset();
    partySearch.value = "";
    partyCodeDisplay.value = "";
    bankSearch.value = "";
    state.bills = [];
    state.selectedBillIndex = -1;
    renderBillRows();
    renderHistoryRows([]);
    form.querySelector("[data-total-amount]").value = "0.00";
    form.querySelector("[data-total-outstanding]").value = "0.00";
    form.querySelector("[data-ledger-balance]").value = "0.00";
    form.querySelector("[data-balance-amt]").value = "0.00";
    disableAlloc();
  }

  function setReadonly(on) {
    dialog.dataset.readonly = on ? "1" : "0";
    form.querySelectorAll("input:not([type=hidden]), select").forEach(function (el) { el.readOnly = on; el.disabled = el.disabled || on; });
    form.querySelector("[data-confirm]").hidden = on;
  }

  function open(mode) {
    var row = selectedRow();
    if (mode !== "add" && !row) return;
    state.mode = mode;
    show(formAlert, "");
    resetForm();
    document.querySelector("[data-mode-label]").textContent = mode === "add" ? "Add" : "View";
    if (mode === "add") {
      modeSelect.value = "CA";
      applyModeDefaults();
      setReadonly(false);
      dialog.showModal();
      modeSelect.focus();
      return;
    }
    var params = new URLSearchParams({ p_code: row.p_code, chq_no: row.chq_no, slip_dt: row.slip_dt });
    getJson(root.dataset.detailUrl + "?" + params.toString()).then(function (res) {
      if (!res.ok) { show(alertBox, res.body.message || "Could not open the Money Receipt."); return; }
      var d = res.body;
      modeSelect.value = d.mode || "CA";
      applyModeLayout();
      field("slip_date").value = dmy(d.slip_dt);
      field("amount_received").value = d.amount;
      form.querySelector("[data-total-amount]").value = d.amount;
      field("chq_no").value = d.chq_no;
      field("chq_dt").value = dmy(d.chq_dt);
      field("party_code").value = d.party_code;
      partySearch.value = d.party_name;
      partyCodeDisplay.value = d.party_code;
      bankSearch.value = d.bank_code;
      field("bank_code").value = d.bank_code;
      field("prev_adv").value = d.prev_adv;
      state.bills = (d.lines || []).map(function (l) {
        return { div: l.div, bill_no: l.bill_no, bill_date: l.bill_date, inv_amount: l.inv_amount,
          balance_amt: l.amount_adjusted, bill_type: l.bill_type, locked: true,
          cash_discount: l.cash_discount, tds_amt: l.tds_amt, amount_adjusted: l.amount_adjusted, running_balance: "" };
      });
      state.selectedBillIndex = -1;
      renderBillRows();
      renderHistoryRows(d.history_rows || []);
      setReadonly(true);
      dialog.showModal();
    });
  }

  function save() {
    show(formAlert, "");
    var lines = state.bills.filter(function (b) { return b.locked; }).map(function (b) {
      return { div: b.div, bill_no: b.bill_no, bill_date: b.bill_date, bill_type: b.bill_type,
        inv_amount: b.inv_amount, balance_amt: b.balance_amt,
        cash_discount: b.cash_discount, tds_amt: b.tds_amt, amount_adjusted: b.amount_adjusted };
    });
    // every pending bill's own balance_amt is also needed for the total-outstanding check
    var allBills = state.bills.map(function (b) { return { balance_amt: b.balance_amt }; });
    var payload = {
      mode: modeSelect.value,
      slip_date: dmyToIso(field("slip_date").value),
      amount_received: field("amount_received").value,
      party_code: field("party_code").value.trim(),
      bank_code: field("bank_code").value.trim(),
      chq_no: field("chq_no").value.trim(),
      chq_dt: dmyToIso(field("chq_dt").value),
      prev_adv: field("prev_adv").value,
      lines: allBills.map(function (b, i) {
        var l = lines.find(function (x) { return state.bills[i].locked && x.bill_no === state.bills[i].bill_no && x.div === state.bills[i].div; });
        return l ? l : { bill_no: state.bills[i].bill_no, div: state.bills[i].div, balance_amt: state.bills[i].balance_amt, amount_adjusted: "0.00" };
      }),
    };
    askConfirm("Are You Sure?", function () {
      post(root.dataset.saveUrl, payload).then(function (res) {
        if (!res.ok) {
          show(formAlert, res.body.message || "Could not save the Money Receipt.");
          var first = Object.keys(res.body.errors || {})[0];
          if (first && field(first)) field(first).focus();
          return;
        }
        dialog.close();
        show(alertBox, res.body.message);
        refresh();
      });
    });
  }

  form.querySelector("[data-confirm]").addEventListener("click", save);
  form.querySelectorAll("[data-form-exit]").forEach(function (b) { b.addEventListener("click", function () { dialog.close(); }); });
  dialog.addEventListener("keydown", function (e) { if (e.key === "Escape" && dialog.open) { e.preventDefault(); dialog.close(); } });

  root.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var a = btn.dataset.action;
      if (a === "add") open("add");
      else if (a === "view") open("view");
      else if (a === "delete") { if (selectedRow()) deleteDialog.showModal(); }
      else if (a === "refresh") refresh();
      else if (a === "exit") window.location.href = root.dataset.exitUrl;
    });
  });

  deleteDialog.querySelector("[data-delete-yes]").addEventListener("click", function () {
    var row = selectedRow();
    deleteDialog.close();
    if (!row) return;
    post(root.dataset.deleteUrl, { p_code: row.p_code, chq_no: row.chq_no, slip_dt: row.slip_dt }).then(function (res) {
      show(alertBox, res.body.message || "");
      state.selected = null;
      refresh();
    });
  });
  deleteDialog.querySelector("[data-delete-no]").addEventListener("click", function () { deleteDialog.close(); });

  [startDate, endDate].forEach(function (el) { el.addEventListener("change", refresh); });
  search.addEventListener("input", refresh);

  var today = new Date();
  var pad = function (n) { return String(n).padStart(2, "0"); };
  var todayStr = pad(today.getDate()) + "/" + pad(today.getMonth() + 1) + "/" + today.getFullYear();
  startDate.value = todayStr;
  endDate.value = todayStr;
  renderBillRows();
  refresh();
})();
