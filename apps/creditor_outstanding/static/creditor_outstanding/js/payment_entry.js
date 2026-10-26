/* Creditor Outstanding > Payment Entry: vendor, pending bills, adjustments, CONFIRM / DELETE. */
(function () {
  "use strict";

  var root = document.querySelector("[data-pe]");
  if (!root) return;

  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var partySearch = root.querySelector("[data-party-search]");
  var partyCode = root.querySelector("[data-party-code]");
  var bankSearch = root.querySelector("[data-bank-search]");
  var bankCode = root.querySelector("[data-bank-code]");
  var modeSel = root.querySelector("[data-mode]");
  var billsBody = root.querySelector("[data-bills]");
  var linesBody = root.querySelector("[data-lines]");
  var alertBox = root.querySelector("[data-alert]");
  var lines = [];
  var selectedBill = null;

  function num(el) { return Number(el.value) || 0; }
  function money(v) { return (Math.round(v * 100) / 100).toFixed(2); }
  var alertTimer = null;
  function show(msg) {
    alertBox.textContent = msg || "";
    alertBox.hidden = !msg;
    clearTimeout(alertTimer);
    if (msg) alertTimer = setTimeout(function () { alertBox.hidden = true; }, 5000);
  }

  function post(url, data) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrf, "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(data || {}),
    }).then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); });
  }

  function getJson(url) {
    return fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json(); });
  }

  function dmy(iso) {
    var p = String(iso || "").split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : "";
  }

  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (cls) td.className = cls;
    return td;
  }

  function renderBills(rows) {
    billsBody.textContent = "";
    rows.forEach(function (b) {
      var tr = document.createElement("tr");
      tr.append(cell(b.div), cell(b.bill_no), cell(dmy(b.bill_date)), cell(b.bill_amount, "num"), cell(b.balance, "num"));
      tr.addEventListener("click", function () {
        billsBody.querySelectorAll("tr").forEach(function (x) { x.classList.remove("is-sel"); });
        tr.classList.add("is-sel");
        selectedBill = b;
        root.querySelector("[data-adjusted]").value = money(Math.max(0, Math.min(Number(b.balance), amountLeft())));
      });
      billsBody.appendChild(tr);
    });
  }

  function amountLeft() {
    var paid = num(root.querySelector("[data-amount-paid]"));
    return paid - lines.reduce(function (s, l) { return s + l.adjusted; }, 0);
  }

  function renderLines() {
    linesBody.textContent = "";
    var running = num(root.querySelector("[data-amount-paid]"));
    if (!lines.length) {
      var tr = document.createElement("tr");
      tr.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 10;
      td.textContent = "Select a vendor, pick a bill and press OK.";
      tr.appendChild(td);
      linesBody.appendChild(tr);
    }
    lines.forEach(function (l, i) {
      running -= l.adjusted;
      var tr = document.createElement("tr");
      tr.append(cell(i + 1), cell(l.div), cell(l.bill_no), cell(dmy(l.bill_date)), cell(l.bill_amount, "num"),
        cell(l.balance, "num"), cell(money(l.cash_dis), "num"), cell(money(l.interest), "num"),
        cell(money(l.adjusted), "num"), cell(money(running), "num"));
      linesBody.appendChild(tr);
    });
    root.querySelector("[data-total]").value = money(lines.reduce(function (s, l) { return s + l.adjusted; }, 0));
  }

  function selectParty(p) {
    partyCode.value = p.code;
    partySearch.value = p.name;
    root.querySelector("[data-party-display]").value = p.code;
    root.querySelector("[data-party-city]").value = p.city || "";
    getJson(root.dataset.billsUrl + "?party_code=" + encodeURIComponent(p.code)).then(function (r) {
      renderBills(r.bills);
      lines = [];
      renderLines();
      show(r.bills.length ? "" : "No pending bill for this vendor.");
    });
  }

  window.HelpLookup.attach(partySearch, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Customer",
    onSelect: function (p) { selectParty(p); root.querySelector("[data-date]").focus(); },
  });

  root.querySelector("[data-amount-paid]").addEventListener("input", function () {
    root.querySelector("[data-total]").value = this.value;
  });

  window.HelpLookup.attach(bankSearch, {
    endpoint: root.dataset.banksUrl, resultsKey: "banks", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Bank" }],
    title: "Bank",
    onSelect: function (b) { bankCode.value = b.code; bankSearch.value = b.name; },
  });

  modeSel.addEventListener("change", function () {
    var cash = modeSel.value === "CA";
    bankSearch.disabled = cash;
    if (cash) { bankSearch.value = ""; bankCode.value = ""; }
  });

  root.querySelector("[data-ok]").addEventListener("click", function () {
    if (!selectedBill) { show("Pick a bill first."); return; }
    var adjusted = num(root.querySelector("[data-adjusted]"));
    var cash = num(root.querySelector("[data-cash-dis]"));
    var interest = num(root.querySelector("[data-interest]"));
    var balance = Number(selectedBill.balance);
    lines.push({
      div: selectedBill.div, bill_no: selectedBill.bill_no, bill_date: selectedBill.bill_date,
      bill_amount: selectedBill.bill_amount, balance: selectedBill.balance,
      cash_dis: cash, interest: interest, adjusted: adjusted,
      balance_after: balance - adjusted - cash + interest,
    });
    renderLines();
    selectedBill = null;
    billsBody.querySelectorAll("tr").forEach(function (x) { x.classList.remove("is-sel"); });
    root.querySelector("[data-cash-dis]").value = "0.00";
    root.querySelector("[data-interest]").value = "0.00";
    root.querySelector("[data-adjusted]").value = "0.00";
  });

  var listSection = root.querySelector("[data-list]");
  var formSection = root.querySelector("[data-form]");
  var listRows = root.querySelector("[data-list-rows]");
  var listSearch = root.querySelector("[data-list-search]");
  var selectedPayment = null;
  var allPayments = [];

  function renderList(rows) {
    listRows.textContent = "";
    selectedPayment = null;
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.append(cell(dmy(r.date)), cell(r.party_code), cell(r.party_name), cell(r.chq_no), cell(r.amount, "num"));
      tr.addEventListener("click", function () {
        listRows.querySelectorAll("tr").forEach(function (x) { x.classList.remove("is-sel"); });
        tr.classList.add("is-sel");
        selectedPayment = r;
      });
      listRows.appendChild(tr);
    });
    if (!rows.length) {
      var empty = document.createElement("tr");
      empty.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 5;
      td.textContent = allPayments.length ? "No payments match your search." : "No payments yet. Press ADD to enter one.";
      empty.appendChild(td);
      listRows.appendChild(empty);
    }
  }

  function applyListSearch() {
    var q = listSearch.value.trim().toLowerCase();
    if (!q) { renderList(allPayments); return; }
    renderList(allPayments.filter(function (r) {
      return (r.party_code || "").toLowerCase().indexOf(q) !== -1
        || (r.party_name || "").toLowerCase().indexOf(q) !== -1
        || (r.chq_no || "").toLowerCase().indexOf(q) !== -1;
    }));
  }

  listSearch.addEventListener("input", applyListSearch);

  function loadList() {
    getJson(root.dataset.listUrl).then(function (res) {
      allPayments = res.rows;
      listSearch.value = "";
      renderList(allPayments);
    });
  }

  var mainToolbar = root.querySelector("[data-main-toolbar]");

  var focusOrder = [
    partySearch,
    root.querySelector("[data-date]"),
    modeSel,
    root.querySelector("[data-chq-no]"),
    root.querySelector("[data-amount-paid]"),
    root.querySelector("[data-total]"),
    root.querySelector("[data-bank-charges]"),
    root.querySelector("[data-prev-adv]"),
    bankSearch,
    root.querySelector("[data-remarks]"),
  ];
  focusOrder.forEach(function (el, i) { el.tabIndex = i + 1; });
  root.querySelector("[data-total]").removeAttribute("readonly");
  root.querySelector("[data-prev-adv]").removeAttribute("readonly");

  function nextField(current) {
    var i = focusOrder.indexOf(current);
    for (var k = i + 1; k < focusOrder.length; k++) {
      if (!focusOrder[k].disabled) return focusOrder[k];
    }
    return root.querySelector("[data-ok]");
  }

  formSection.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" || e.defaultPrevented) return;
    var idx = focusOrder.indexOf(e.target);
    if (idx === -1) return;
    e.preventDefault();
    nextField(e.target).focus();
  });

  function showForm() {
    listSection.hidden = true;
    mainToolbar.hidden = true;
    formSection.hidden = false;
    partySearch.focus();
  }

  function showList() {
    formSection.hidden = true;
    mainToolbar.hidden = false;
    listSection.hidden = false;
    loadList();
  }

  root.querySelector("[data-add]").addEventListener("click", function () {
    show("");
    editing = null;
    setEditable(true);
    partySearch.value = ""; partyCode.value = ""; bankSearch.value = ""; bankCode.value = "";
    root.querySelector("[data-chq-no]").value = "";
    root.querySelector("[data-remarks]").value = "";
    root.querySelector("[data-bank-charges]").value = "0.00";
    root.querySelector("[data-amount-paid]").value = "0.00";
    root.querySelector("[data-date]").value = window.DateMask.toDisplay(new Date().toISOString().slice(0, 10));
    lines = [];
    renderBills([]);
    renderLines();
    showForm();
  });

  root.querySelector("[data-back]").addEventListener("click", showList);

  var editing = null;

  function setEditable(on) {
    formSection.querySelectorAll("input, select").forEach(function (el) {
      if (el.hasAttribute("readonly") && el.dataset.keepReadonly !== undefined) return;
      if (el.type === "hidden") return;
      el.disabled = !on;
    });
    root.querySelector("[data-confirm]").hidden = !on;
    root.querySelector("[data-ok]").disabled = !on;
  }

  function openSaved(mode) {
    if (!selectedPayment) { window.alert("Select a payment in the list first."); return; }
    getJson(root.dataset.detailUrl + "?party_code=" + encodeURIComponent(selectedPayment.party_code) +
      "&chq_no=" + encodeURIComponent(selectedPayment.chq_no)).then(function (d) {
      if (d.message) { show(d.message); return; }
      show("");
      partySearch.value = d.party_name; partyCode.value = d.party_code;
      modeSel.value = d.mode; bankCode.value = d.bank_code; bankSearch.value = d.bank_code;
      bankSearch.disabled = d.mode === "CA";
      root.querySelector("[data-chq-no]").value = d.chq_no;
      root.querySelector("[data-date]").value = window.DateMask.toDisplay(d.date);
      root.querySelector("[data-amount-paid]").value = d.amount_paid;
      root.querySelector("[data-bank-charges]").value = "0.00";
      root.querySelector("[data-remarks]").value = "";
      renderBills([]);
      lines = d.lines.map(function (l) {
        return { div: l.div, bill_no: l.bill_no, bill_date: l.bill_date, bill_amount: l.bill_amount,
          balance: l.balance, cash_dis: Number(l.cash_dis), interest: Number(l.interest),
          adjusted: Number(l.adjusted), balance_after: Number(l.balance) - Number(l.adjusted) - Number(l.cash_dis) + Number(l.interest) };
      });
      renderLines();
      editing = mode === "modify" ? { party_code: d.party_code, chq_no: d.chq_no } : null;
      showForm();
      setEditable(mode === "modify");
    });
  }

  root.querySelector("[data-view]").addEventListener("click", function () { openSaved("view"); });
  root.querySelector("[data-modify]").addEventListener("click", function () { openSaved("modify"); });

  root.querySelector("[data-confirm]").addEventListener("click", function () {
    show("");
    askConfirm("Are You Sure?", function () {
    var payload = {
      party_code: partyCode.value, mode: modeSel.value, bank_code: bankCode.value,
      chq_no: root.querySelector("[data-chq-no]").value.trim(),
      date: window.DateMask.toIso(root.querySelector("[data-date]").value),
      bank_charges: num(root.querySelector("[data-bank-charges]")),
      amount_paid: num(root.querySelector("[data-amount-paid]")),
      remarks: root.querySelector("[data-remarks]").value.trim(),
      lines: lines.map(function (l) {
        return { div: l.div, bill_no: l.bill_no, bill_date: l.bill_date, bill_amount: l.bill_amount,
          cash_dis: l.cash_dis, interest: l.interest, adjusted: l.adjusted };
      }),
    };
    var reverse = editing
      ? post(root.dataset.deleteUrl, { party_code: editing.party_code, chq_no: editing.chq_no })
      : Promise.resolve({ ok: true, body: {} });
    reverse.then(function (r) {
      if (!r.ok) { show(r.body.message || "Could not reverse the old payment."); return; }
      return post(root.dataset.saveUrl, payload).then(function (res) {
        if (!res.ok) { show(res.body.message || "Could not post the payment."); return; }
        editing = null;
        window.alert(res.body.message);
        showList();
      });
    });
    });
  });

  root.querySelector("[data-delete]").addEventListener("click", function () {
    if (!selectedPayment) { window.alert("Select a payment in the list first."); return; }
    askConfirm("Are You Sure You Want To Delete This Payment?", function () {
      post(root.dataset.deleteUrl, { party_code: selectedPayment.party_code, chq_no: selectedPayment.chq_no }).then(function (res) {
        window.alert(res.body.message || "");
        loadList();
      });
    });
  });

  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });
  loadList();
})();
