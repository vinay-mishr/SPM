/* Money Receipt > Advance Adjustment -- VFP-style layout: ADD/DELETE/CONFIRM/EXIT,
   party + entry details, an upper invoice-pick list feeding Cash Dis./Interest/
   Amt. Adjusted + OK, and one big bottom grid (DIV/INV.NO./.../BALANCE). */
(function () {
  "use strict";

  var root = document.querySelector("[data-aa]");
  if (!root) return;

  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var partySearch = root.querySelector("[data-party-search]");
  var partyCode = root.querySelector("[data-party-code]");
  var partyCity = root.querySelector("[data-party-city]");
  var advanceField = root.querySelector("[data-advance]");
  var entNo = root.querySelector("[data-ent-no]");
  var entDt = root.querySelector("[data-ent-dt]");
  var pickRows = root.querySelector("[data-pick-rows]");
  var gridRows = root.querySelector("[data-rows]");
  var cashDis = root.querySelector("[data-cash-dis]");
  var interestAmt = root.querySelector("[data-interest-amt]");
  var amtAdjusted = root.querySelector("[data-amt-adjusted]");
  var okBtn = root.querySelector("[data-ok]");
  var addBtn = root.querySelector("[data-add]");
  var deleteBtn = root.querySelector("[data-delete]");
  var confirmBtn = root.querySelector("[data-confirm]");
  var alertBox = root.querySelector("[data-alert]");

  var mode = null; // 'add' | 'delete'
  var bills = [];
  var lockedRows = [];
  var selectedBillIndex = -1;
  var advance = 0;
  var alertTimer = null;

  function num(v) { var n = parseFloat(v); return isNaN(n) ? 0 : n; }
  function f2(n) { return (Math.round(n * 100) / 100).toFixed(2); }
  function show(msg, kind) {
    alertBox.textContent = msg || "";
    alertBox.hidden = !msg;
    alertBox.className = "gi-alert" + (kind === "error" ? " gi-alert--error" : "");
    clearTimeout(alertTimer);
    if (msg) alertTimer = setTimeout(function () { alertBox.hidden = true; }, 5000);
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
  attachHyphenMask(entDt);

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

  // --- upper pick list (unlocked pending bills only) -------------------------
  function renderPick() {
    pickRows.textContent = "";
    var remaining = bills.filter(function (b) { return !b.locked; });
    if (!remaining.length) {
      var tr = document.createElement("tr");
      tr.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 4;
      td.textContent = mode ? "No pending bill for this party." : "Press ADD, pick a party.";
      tr.appendChild(td);
      pickRows.appendChild(tr);
      return;
    }
    remaining.forEach(function (b) {
      var i = bills.indexOf(b);
      var tr = document.createElement("tr");
      if (i === selectedBillIndex) tr.classList.add("is-selected");
      tr.append(cell(b.bill_no), cell(dmy(b.bill_date), null), cell(b.inv_amount, "num"), cell(b.balance_amt, "num"));
      tr.addEventListener("click", function () { selectBill(i); });
      pickRows.appendChild(tr);
    });
  }

  function disableAdjustFields() {
    cashDis.disabled = true;
    interestAmt.disabled = true;
    okBtn.disabled = true;
    cashDis.value = "0.00";
    interestAmt.value = "0.00";
    amtAdjusted.value = "0.00";
    selectedBillIndex = -1;
  }

  function remainingAdvance() {
    var used = lockedRows.reduce(function (s, r) { return s + num(r.amount_adj); }, 0);
    return advance - used;
  }

  function selectBill(i) {
    selectedBillIndex = i;
    renderPick();
    var b = bills[i];
    var left = remainingAdvance();
    cashDis.disabled = false;
    interestAmt.disabled = false;
    okBtn.disabled = false;
    cashDis.value = "0.00";
    interestAmt.value = "0.00";
    amtAdjusted.value = f2(Math.min(num(b.balance_amt), Math.max(left, 0)));
    cashDis.focus();
  }

  // Each field's Valid recomputes amt_adj from the bill's own balance (same
  // quirk as Money Receipt Entry's own tc_dis/ti_amount.Valid -- each field
  // independently drives amt_adj off the full balance, not net of the other).
  function recompute(fieldValue) {
    var b = bills[selectedBillIndex];
    if (!b) return;
    var balance = num(b.balance_amt);
    if (fieldValue > balance) {
      window.alert("Invalid Amount <<Check Again>>");
      return;
    }
    var adj = balance - fieldValue;
    var left = remainingAdvance();
    if (adj > left) adj = Math.max(left, 0);
    amtAdjusted.value = f2(adj);
  }
  cashDis.addEventListener("change", function () { recompute(num(cashDis.value)); });
  interestAmt.addEventListener("change", function () { recompute(num(interestAmt.value)); });

  okBtn.addEventListener("click", function () {
    var b = bills[selectedBillIndex];
    if (!b) return;
    if (num(amtAdjusted.value) <= 0) { show("Enter an amount to adjust.", "error"); return; }
    b.locked = true;
    lockedRows.push({
      div: b.div, bill_no: b.bill_no, bill_date: b.bill_date, bill_type: b.bill_type,
      inv_amount: b.inv_amount, balance_amt: b.balance_amt,
      cash_discount: f2(num(cashDis.value)), interest_amt: f2(num(interestAmt.value)),
      amount_adj: f2(num(amtAdjusted.value)),
    });
    disableAdjustFields();
    renderPick();
    renderGrid();
  });

  // --- bottom grid (locked rows + running balance, VFP caltotal) ------------
  function renderGrid() {
    gridRows.textContent = "";
    if (!lockedRows.length) {
      var tr = document.createElement("tr");
      tr.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 10;
      td.innerHTML = "&nbsp;";
      tr.appendChild(td);
      gridRows.appendChild(tr);
      return;
    }
    var mbalance = advance;
    lockedRows.forEach(function (r, i) {
      mbalance -= num(r.amount_adj);
      var tr = document.createElement("tr");
      tr.append(
        cell(i + 1), cell(r.div), cell(r.bill_no), cell(dmy(r.bill_date)), cell(r.inv_amount, "num"),
        cell(r.balance_amt, "num"), cell(r.cash_discount, "num"), cell(r.interest_amt, "num"),
        cell(r.amount_adj, "num"), cell(f2(mbalance), "num")
      );
      tr.addEventListener("dblclick", function () {
        if (mode !== "add") return;
        var b = bills.find(function (x) { return x.bill_no === r.bill_no && x.div === r.div; });
        if (b) b.locked = false;
        lockedRows.splice(i, 1);
        renderPick();
        renderGrid();
      });
      gridRows.appendChild(tr);
    });
  }

  // --- party select ------------------------------------------------------
  function loadParty(p) {
    partyCode.value = p.code;
    partySearch.value = p.name;
    partyCity.value = p.city || "";
    getJson(root.dataset.dataUrl + "?party_code=" + encodeURIComponent(p.code)).then(function (res) {
      advance = num(res.body.advance);
      advanceField.value = f2(advance);
      bills = (res.body.bills || []).map(function (b) { return Object.assign({}, b, { locked: false }); });
      lockedRows = [];
      selectedBillIndex = -1;
      disableAdjustFields();
      renderPick();
      renderGrid();
      if (advance <= 0) show("No Pending Advance for this Party.");
      else if (!bills.length) show("No Pending Bill for this Party.");
      else show("");
    });
  }

  window.HelpLookup.attach(partySearch, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Party",
    onSelect: function (p) {
      if (mode === "delete") {
        partyCode.value = p.code;
        partySearch.value = p.name;
        partyCity.value = p.city || "";
        entNo.disabled = false;
        entNo.focus();
      } else {
        loadParty(p);
      }
    },
  });

  // --- Entry No. lookup in DELETE mode ---------------------------------
  entNo.addEventListener("change", function () {
    if (mode !== "delete" || !partyCode.value || !entNo.value.trim()) return;
    var params = new URLSearchParams({ party_code: partyCode.value, ent_no: entNo.value.trim() });
    getJson(root.dataset.entryUrl + "?" + params.toString()).then(function (res) {
      if (!res.ok) { show(res.body.message || "Entry not found.", "error"); return; }
      var d = res.body;
      entDt.value = dmy(d.ent_dt);
      advance = num(d.prev_adv);
      advanceField.value = f2(advance);
      lockedRows = d.lines.map(function (l) {
        return { div: l.div, bill_no: l.bill_no, bill_date: l.bill_date, bill_type: l.bill_type,
          inv_amount: l.bill_amount, balance_amt: l.bill_amount,
          cash_discount: l.cash_discount, interest_amt: l.interest_amt, amount_adj: l.adjusted };
      });
      bills = [];
      renderPick();
      renderGrid();
      confirmBtn.disabled = false;
      show("");
    });
  });

  // --- toolbar -------------------------------------------------------------
  function resetForm() {
    partySearch.value = ""; partyCode.value = ""; partyCity.value = "";
    advanceField.value = "0.00"; entNo.value = ""; entDt.value = "";
    bills = []; lockedRows = []; advance = 0;
    disableAdjustFields();
    renderPick();
    renderGrid();
    show("");
  }

  addBtn.addEventListener("click", function () {
    mode = "add";
    resetForm();
    partySearch.disabled = false;
    entNo.disabled = false;
    entDt.disabled = false;
    entDt.value = todayDmy();
    confirmBtn.disabled = false;
    deleteBtn.disabled = true;
    partySearch.focus();
  });

  deleteBtn.addEventListener("click", function () {
    mode = "delete";
    resetForm();
    partySearch.disabled = false;
    entNo.disabled = true;
    entDt.disabled = true;
    addBtn.disabled = true;
    confirmBtn.disabled = true;
    partySearch.focus();
  });

  function endMode() {
    mode = null;
    resetForm();
    partySearch.disabled = true;
    entNo.disabled = true;
    entDt.disabled = true;
    addBtn.disabled = false;
    deleteBtn.disabled = false;
    confirmBtn.disabled = true;
  }

  confirmBtn.addEventListener("click", function () {
    if (!mode) return;
    if (mode === "add") {
      if (!partyCode.value) { show("Select a party first.", "error"); return; }
      if (!entNo.value.trim()) { show("Entry No. is required.", "error"); return; }
      if (!lockedRows.length) { show("Press OK to adjust at least one bill.", "error"); return; }
      askConfirm("Are You Sure?", function () {
        post(root.dataset.saveUrl, {
          party_code: partyCode.value, ent_no: entNo.value.trim(), ent_dt: dmyToIso(entDt.value),
          lines: lockedRows.map(function (r) {
            return { bill_type: r.bill_type, div: r.div, bill_no: r.bill_no, bill_date: r.bill_date,
              cash_discount: r.cash_discount, interest_amt: r.interest_amt, adjusted: r.amount_adj };
          }),
        }).then(function (res) {
          if (!res.ok) { show(res.body.message || "Could not adjust the advance.", "error"); return; }
          window.alert(res.body.message);
          endMode();
        });
      });
    } else {
      if (!partyCode.value || !entNo.value.trim()) { show("Select a party and Entry No. first.", "error"); return; }
      askConfirm("Are You Sure?", function () {
        post(root.dataset.deleteUrl, { party_code: partyCode.value, ent_no: entNo.value.trim() }).then(function (res) {
          if (!res.ok) { show(res.body.message || "Could not delete.", "error"); return; }
          window.alert(res.body.message);
          endMode();
        });
      });
    }
  });

  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  partySearch.disabled = true;
  confirmBtn.disabled = true;
  renderPick();
  renderGrid();
})();
