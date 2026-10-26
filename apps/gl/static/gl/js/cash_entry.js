/* Accounts > Data Entry > Cash Entry: list of CV voucher lines (ADD/MODIFY/
   DELETE/VIEW a whole voucher by its date+voucher no), form dialog builds a
   double-entry grid and auto-balances against Cash on CONFIRM. */
(function () {
  "use strict";

  var root = document.querySelector("[data-ce]");
  if (!root) return;

  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var rows = root.querySelector("[data-rows]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var search = root.querySelector("[data-search]");
  var alertBox = root.querySelector("[data-alert]");

  var dialog = document.querySelector("[data-form]");
  var form = dialog.querySelector("[data-ce-form]");
  var formAlert = dialog.querySelector("[data-form-alert]");
  var modeLabel = dialog.querySelector("[data-mode-label]");
  var confirmBtn = dialog.querySelector("[data-confirm]");
  var confirmDialog = document.querySelector("[data-confirm-dialog]");

  var dcSelect = form.querySelector("[data-dc]");
  var ledgerSearch = form.querySelector("[data-ledger-search]");
  var ledgerCode = form.querySelector("[data-ledger-code]");
  var partySearch = form.querySelector("[data-party-search]");
  var partyCode = form.querySelector("[data-party-code]");
  var narration = form.querySelector("[data-narration]");
  var amount = form.querySelector("[data-amount]");
  // Select the whole "0.00" placeholder value on focus so typing a digit
  // replaces it outright instead of appending after it (e.g. "0.005").
  amount.addEventListener("focus", function () { amount.select(); });
  var ledgerBalance = form.querySelector("[data-ledger-balance]");
  var partyBalance = form.querySelector("[data-party-balance]");
  var okBtn = form.querySelector("[data-ok]");
  var gridRows = form.querySelector("[data-grid-rows]");

  var listState = { rows: [], selected: null };
  var mode = "add";
  var lineLedger = null; // {code, name}
  var lineParty = null;
  var gridLines = [];

  function field(name) { return form.querySelector('[data-field="' + name + '"]'); }
  function num(v) { var n = parseFloat(v); return isNaN(n) ? 0 : n; }
  function f2(n) { return (Math.round(n * 100) / 100).toFixed(2); }
  // A validation/error message also pops up centered on the page for 5s --
  // the inline red banner (box) is easy to miss at the top of a tall dialog,
  // especially a CONFIRM rejection like "Total mismatch, unable to Confirm."
  function centerPopup(msg) {
    // A plain <dialog> showModal() renders in the browser's own top layer,
    // above every ordinary element regardless of z-index -- a popup appended
    // to document.body would sit UNDER the open dialog, invisible. Appending
    // it inside the open dialog instead puts it in that same top layer (the
    // same host askConfirm's own overlay already uses -- see confirm_box.js).
    var host = document.querySelector("dialog[open]") || document.body;
    var el = host.querySelector(".ce-center-popup");
    if (!el) {
      el = document.createElement("div");
      el.className = "ce-center-popup";
      host.appendChild(el);
    }
    el.textContent = msg;
    el.classList.add("is-visible");
    clearTimeout(centerPopup.timer);
    centerPopup.timer = setTimeout(function () { el.classList.remove("is-visible"); }, 5000);
  }
  // The inline banner is no longer shown -- only the centered popup above --
  // box is kept (not removed) since other code still reads/clears its text,
  // just always left hidden.
  function show(box, msg) {
    box.textContent = msg || "";
    box.hidden = true;
    if (msg) centerPopup(msg);
  }
  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (cls) td.className = cls;
    return td;
  }
  function dmy(iso) {
    var p = String(iso || "").split("-");
    return p.length === 3 ? p[2] + "-" + p[1] + "-" + p[0] : "";
  }
  function dmyToIso(d) {
    var p = String(d || "").split(/[-/]/);
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

  // Keyboard focus sequence: Entry Date -> Voucher No. -> DR/CR -> Ledger ->
  // Party -> Narration -> Amount -> OK. Ledger/Party already advance focus
  // this same way once a lookup selection is made (see help_lookup.js's own
  // focusNext, which walks this form's focusable fields in DOM order) --
  // this just adds the same "next field" behavior to the plain fields
  // HelpLookup doesn't own (date, voucher no, DR/CR, narration, amount).
  function focusableFields() {
    return Array.prototype.slice.call(
      form.querySelectorAll(
        "input:not([type=hidden]):not([readonly]):not([disabled]), " +
        "select:not([disabled]), textarea:not([readonly]):not([disabled]), button:not([disabled])"
      )
    ).filter(function (el) { return el.offsetParent !== null; });
  }
  function focusNextField(fromEl) {
    var candidates = focusableFields();
    var idx = candidates.indexOf(fromEl);
    if (idx > -1 && idx < candidates.length - 1) {
      var next = candidates[idx + 1];
      next.focus();
      if (next.select) next.select();
    }
  }
  function advanceOnEnter(el) {
    el.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      e.preventDefault();
      focusNextField(el);
    });
  }
  advanceOnEnter(field("ent_dt"));
  advanceOnEnter(field("vou_no"));
  advanceOnEnter(dcSelect);
  // Narration is a multiline textarea (an existing feature) -- plain Enter
  // moves on to Amount; Shift+Enter still inserts a newline.
  narration.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" || e.shiftKey) return;
    e.preventDefault();
    focusNextField(narration);
  });
  // Amount is the last field before OK -- Enter here does exactly what
  // clicking OK does (same validation path, same "Pick a ledger..." /
  // "Invalid Amount." messages on failure).
  amount.addEventListener("keydown", function (e) {
    if (e.key !== "Enter") return;
    e.preventDefault();
    okBtn.click();
  });

  function post(url, data) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrf, "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(data || {}),
    }).then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); });
  }
  function getJson(url) {
    return fetch(url, { credentials: "same-origin" }).then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); });
  }
  function askConfirm(message, onYes) {
    confirmDialog.querySelector("[data-confirm-message]").textContent = message;
    confirmDialog.showModal();
    var yesBtn = confirmDialog.querySelector("[data-confirm-yes]");
    var noBtn = confirmDialog.querySelector("[data-confirm-no]");
    function cleanup() { yesBtn.removeEventListener("click", onYesClick); noBtn.removeEventListener("click", onNoClick); }
    function onYesClick() { cleanup(); confirmDialog.close(); onYes(); }
    function onNoClick() { cleanup(); confirmDialog.close(); }
    yesBtn.addEventListener("click", onYesClick);
    noBtn.addEventListener("click", onNoClick);
  }

  // --- master list -----------------------------------------------------------
  function selectedRow() {
    return listState.rows.find(function (r) { return r.key === listState.selected; }) || null;
  }
  function updateToolbar() {
    var has = Boolean(selectedRow());
    root.querySelectorAll('[data-action="modify"], [data-action="delete"], [data-action="view"]').forEach(function (b) {
      b.disabled = !has;
    });
  }
  function renderList() {
    rows.textContent = "";
    listState.rows.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.dataset.key = r.key;
      if (r.key === listState.selected) tr.classList.add("is-selected");
      tr.append(cell(dmy(r.tdate)), cell(r.tdoc), cell(r.account), cell(r.narration), cell(r.debit, "num"), cell(r.credit, "num"));
      tr.addEventListener("click", function () { listState.selected = r.key; renderList(); });
      rows.appendChild(tr);
    });
    if (!listState.rows.length) {
      var empty = document.createElement("tr");
      empty.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 6;
      td.textContent = "No Cash Entries in this date range.";
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
      listState.rows = (res.body.rows || []).map(function (r) { return Object.assign({}, r, { key: r.tdate + "|" + r.tdoc }); });
      if (!selectedRow()) listState.selected = null;
      renderList();
    });
  }

  // --- line entry (ledger OR party, mutually exclusive) ----------------------
  window.HelpLookup.attach(ledgerSearch, {
    endpoint: root.dataset.ledgersUrl, resultsKey: "ledgers", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }],
    title: "Ledger Account",
    onSelect: function (l) {
      lineLedger = { code: l.code, name: l.name };
      lineParty = null;
      ledgerCode.value = l.code;
      partySearch.value = ""; partyCode.value = "";
      partySearch.disabled = true;
      getJson(root.dataset.balanceUrl + "?code=" + encodeURIComponent(l.code) + "&kind=ledger")
        .then(function (res) { ledgerBalance.value = res.body.balance; });
    },
  });
  window.HelpLookup.attach(partySearch, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Party",
    onSelect: function (p) {
      lineParty = { code: p.code, name: p.name };
      lineLedger = null;
      partyCode.value = p.code;
      ledgerSearch.value = ""; ledgerCode.value = "";
      ledgerSearch.disabled = true;
      getJson(root.dataset.balanceUrl + "?code=" + encodeURIComponent(p.code) + "&kind=party")
        .then(function (res) { partyBalance.value = res.body.balance; });
    },
  });
  ledgerSearch.addEventListener("input", function () {
    if (!ledgerSearch.value) { partySearch.disabled = false; lineLedger = null; ledgerCode.value = ""; ledgerBalance.value = "0.00"; }
  });
  partySearch.addEventListener("input", function () {
    if (!partySearch.value) { ledgerSearch.disabled = false; lineParty = null; partyCode.value = ""; partyBalance.value = "0.00"; }
  });

  function resetLine() {
    lineLedger = null; lineParty = null;
    ledgerSearch.value = ""; partySearch.value = "";
    ledgerCode.value = ""; partyCode.value = "";
    ledgerSearch.disabled = false; partySearch.disabled = false;
    narration.value = ""; amount.value = "0.00";
    ledgerBalance.value = "0.00"; partyBalance.value = "0.00";
  }

  var selectedLineIndex = -1;

  function renderGrid() {
    gridRows.textContent = "";
    if (!gridLines.length) {
      var tr = document.createElement("tr");
      tr.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 6;
      td.textContent = "Pick a ledger or party, enter the amount, press OK. Click a row then press Space to remove it.";
      tr.appendChild(td);
      gridRows.appendChild(tr);
    } else {
      gridLines.forEach(function (l, i) {
        var tr = document.createElement("tr");
        if (i === selectedLineIndex) tr.classList.add("is-selected");
        tr.append(cell(i + 1), cell(l.dc), cell(l.ledger_name || l.party_name), cell(l.narration),
          cell(l.dc === "D" ? f2(num(l.amount)) : "", "num"), cell(l.dc === "C" ? f2(num(l.amount)) : "", "num"));
        if (mode !== "view") {
          tr.addEventListener("click", function () { selectedLineIndex = i; renderGrid(); });
          tr.addEventListener("dblclick", function () { editLine(i); });
        }
        gridRows.appendChild(tr);
      });
    }
    var totalDebit = gridLines.filter(function (l) { return l.dc === "D"; }).reduce(function (s, l) { return s + num(l.amount); }, 0);
    var totalCredit = gridLines.filter(function (l) { return l.dc === "C"; }).reduce(function (s, l) { return s + num(l.amount); }, 0);
    form.querySelector("[data-total-debit]").textContent = f2(totalDebit);
    form.querySelector("[data-total-credit]").textContent = f2(totalCredit);
  }

  // Click a line to select it, then Space removes it -- same convention
  // apps.money_receipt.advance's own bill grid uses, instead of a per-row button.
  gridRows.addEventListener("keydown", function (e) {
    if (e.key !== " " || mode === "view") return;
    if (selectedLineIndex < 0 || selectedLineIndex >= gridLines.length) return;
    e.preventDefault();
    gridLines.splice(selectedLineIndex, 1);
    selectedLineIndex = -1;
    renderGrid();
  });

  // Double-click a grid line to pull it back into the entry fields for
  // editing -- it's removed from the grid now, and OK re-adds the edited
  // version, same as building any other line.
  function editLine(i) {
    var l = gridLines[i];
    if (!l) return;
    gridLines.splice(i, 1);
    selectedLineIndex = -1;
    renderGrid();

    dcSelect.value = l.dc;
    narration.value = l.narration;
    amount.value = l.amount;
    if (l.party_code) {
      lineParty = { code: l.party_code, name: l.party_name };
      lineLedger = null;
      partyCode.value = l.party_code;
      partySearch.value = l.party_name;
      ledgerSearch.value = ""; ledgerCode.value = "";
      ledgerSearch.disabled = true; partySearch.disabled = false;
      getJson(root.dataset.balanceUrl + "?code=" + encodeURIComponent(l.party_code) + "&kind=party")
        .then(function (res) { partyBalance.value = res.body.balance; });
    } else {
      lineLedger = { code: l.ledger_code, name: l.ledger_name };
      lineParty = null;
      ledgerCode.value = l.ledger_code;
      ledgerSearch.value = l.ledger_name;
      partySearch.value = ""; partyCode.value = "";
      partySearch.disabled = true; ledgerSearch.disabled = false;
      getJson(root.dataset.balanceUrl + "?code=" + encodeURIComponent(l.ledger_code) + "&kind=ledger")
        .then(function (res) { ledgerBalance.value = res.body.balance; });
    }
    amount.focus();
    amount.select();
  }

  okBtn.addEventListener("click", function () {
    if (!lineLedger && !lineParty) { show(formAlert, "Pick a ledger or a party first."); return; }
    if (num(amount.value) <= 0) { show(formAlert, "Invalid Amount."); return; }
    show(formAlert, "");
    gridLines.push({
      dc: dcSelect.value, ledger_code: lineLedger ? lineLedger.code : "", ledger_name: lineLedger ? lineLedger.name : "",
      party_code: lineParty ? lineParty.code : "", party_name: lineParty ? lineParty.name : "",
      narration: narration.value, amount: amount.value,
    });
    resetLine();
    renderGrid();
    dcSelect.focus();
  });

  // --- open / save / delete ---------------------------------------------------
  function setFieldsEnabled(on) {
    field("vou_no").readOnly = !on;
    dcSelect.disabled = !on; ledgerSearch.disabled = !on; partySearch.disabled = !on;
    narration.disabled = !on; amount.disabled = !on; okBtn.disabled = !on;
    confirmBtn.hidden = !on;
  }

  function openDialog(m) {
    mode = m;
    modeLabel.textContent = m === "add" ? "Add" : m === "modify" ? "Modify" : m === "delete" ? "Delete" : "View";
    show(formAlert, "");
    gridLines = [];
    selectedLineIndex = -1;
    resetLine();
    renderGrid();

    if (m === "add") {
      field("ent_dt").value = todayDmy();
      field("ent_dt").readOnly = false;
      setFieldsEnabled(true);
      getJson(root.dataset.nextNoUrl + "?ent_dt=" + encodeURIComponent(dmyToIso(field("ent_dt").value)))
        .then(function (res) { field("vou_no").value = res.body.vou_no; });
      dialog.showModal();
      // Initial focus goes to Entry Date (the start of the required keyboard
      // sequence) -- must happen after showModal(), since a <dialog> traps
      // focus inside itself only once it's actually open.
      field("ent_dt").focus();
      field("ent_dt").select();
      return;
    }

    var row = selectedRow();
    if (!row) return;
    getJson(root.dataset.detailUrl + "?ent_dt=" + encodeURIComponent(row.tdate) + "&vou_no=" + encodeURIComponent(row.tdoc))
      .then(function (res) {
        if (!res.ok) { show(alertBox, res.body.message || "Entry not found."); return; }
        var d = res.body;
        field("ent_dt").value = dmy(d.ent_dt);
        field("vou_no").value = d.vou_no;
        field("ent_dt").readOnly = true;
        gridLines = d.lines.map(function (l) {
          return { dc: l.dc, ledger_code: l.ledger_code, ledger_name: l.ledger_name,
            party_code: l.party_code, party_name: l.party_name, narration: l.narration, amount: l.amount };
        });
        renderGrid();
        setFieldsEnabled(m === "modify");
        confirmBtn.hidden = m === "view";
        dialog.showModal();
      });
  }

  root.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var a = btn.dataset.action;
      if (a === "add") openDialog("add");
      else if (a === "modify") openDialog("modify");
      else if (a === "delete") openDialog("delete");
      else if (a === "view") openDialog("view");
      else if (a === "refresh") refresh();
      else if (a === "exit") window.location.href = root.dataset.exitUrl;
    });
  });

  dialog.querySelector("[data-form-exit]").addEventListener("click", function () { dialog.close(); });
  dialog.addEventListener("keydown", function (e) { if (e.key === "Escape" && dialog.open) { e.preventDefault(); dialog.close(); } });

  confirmBtn.addEventListener("click", function () {
    show(formAlert, "");
    if (mode === "delete") {
      askConfirm("Are You Sure?", function () {
        post(root.dataset.deleteUrl, { ent_dt: dmyToIso(field("ent_dt").value), vou_no: field("vou_no").value }).then(function (res) {
          if (!res.ok) { show(formAlert, res.body.message || "Could not delete."); return; }
          dialog.close();
          show(alertBox, res.body.message);
          listState.selected = null;
          refresh();
        });
      });
      return;
    }
    if (!gridLines.length) { show(formAlert, "Add at least one line."); return; }
    var payload = {
      ent_dt: dmyToIso(field("ent_dt").value), vou_no: field("vou_no").value,
      lines: gridLines.map(function (l) {
        return { dc: l.dc, ledger_code: l.ledger_code, party_code: l.party_code, narration: l.narration, amount: l.amount };
      }),
      is_modify: mode === "modify",
      old_ent_dt: mode === "modify" ? dmyToIso(field("ent_dt").value) : "",
      old_vou_no: mode === "modify" ? field("vou_no").value : "",
    };
    askConfirm("Are You Sure?", function () {
      post(root.dataset.saveUrl, payload).then(function (res) {
        if (!res.ok) {
          show(formAlert, res.body.message || "Could not save the entry.");
          var first = Object.keys(res.body.errors || {})[0];
          if (first && field(first)) field(first).focus();
          return;
        }
        dialog.close();
        show(alertBox, res.body.message);
        refresh();
      });
    });
  });

  [startDate, endDate].forEach(function (el) { el.addEventListener("change", refresh); });
  search.addEventListener("input", refresh);

  var today = new Date();
  var pad = function (n) { return String(n).padStart(2, "0"); };
  var todayStr = pad(today.getDate()) + "/" + pad(today.getMonth() + 1) + "/" + today.getFullYear();
  startDate.value = todayStr;
  endDate.value = todayStr;
  renderGrid();
  refresh();
})();
