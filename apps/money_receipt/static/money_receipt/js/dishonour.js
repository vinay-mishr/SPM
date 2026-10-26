/* Money Receipt > Cheque Dishonour: pick a party, pick a cheque, enter Cheque Dis. Date + Bank Charges, CONFIRM. */
(function () {
  "use strict";

  var root = document.querySelector("[data-cd]");
  if (!root) return;

  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var partySearch = root.querySelector("[data-party-search]");
  var partyCode = root.querySelector("[data-party-code]");
  var partyCity = root.querySelector("[data-party-city]");
  var prevAdv = root.querySelector("[data-prev-adv]");
  var totalAmt = root.querySelector("[data-total-amt]");
  var chqSelect = root.querySelector("[data-chq-select]");
  var chqDt = root.querySelector("[data-chq-dt]");
  var bankName = root.querySelector("[data-bank-name]");
  var chqAmount = root.querySelector("[data-chq-amount]");
  var slipDt = root.querySelector("[data-slip-dt]");
  var chqDisDt = root.querySelector("[data-chq-dis-dt]");
  var bankCharges = root.querySelector("[data-bank-charges]");
  var rows = root.querySelector("[data-rows]");
  var alertBox = root.querySelector("[data-alert]");
  var confirmBtn = root.querySelector("[data-confirm]");
  var alertTimer = null;
  var detail = null;

  function show(msg) {
    alertBox.textContent = msg || "";
    alertBox.hidden = !msg;
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
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : "";
  }

  function ymd(dmyStr) {
    var p = String(dmyStr || "").split(/[-/]/);
    return p.length === 3 ? p[2] + "-" + p[1] + "-" + p[0] : "";
  }

  function render() {
    rows.textContent = "";
    var lines = (detail && detail.lines) || [];
    if (!lines.length) {
      var tr = document.createElement("tr");
      tr.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 8;
      td.textContent = "No bill lines for this cheque.";
      tr.appendChild(td);
      rows.appendChild(tr);
      return;
    }
    lines.forEach(function (l, i) {
      var tr = document.createElement("tr");
      tr.append(cell(i + 1), cell(l.div), cell(l.bill_no), cell(dmy(l.bill_date)), cell(l.inv_amount, "num"),
        cell(l.cash_discount, "num"), cell(l.interest_amt, "num"), cell(l.amount_adjusted, "num"));
      rows.appendChild(tr);
    });
  }

  function post(url, data) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrf, "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(data || {}),
    }).then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); });
  }

  function resetForm() {
    detail = null;
    chqSelect.value = ""; chqDt.value = ""; bankName.value = ""; chqAmount.value = "0.00";
    slipDt.value = ""; chqDisDt.value = ""; bankCharges.value = "0.00"; prevAdv.value = "0.00"; totalAmt.value = "0.00";
    rows.textContent = ""; render();
    confirmBtn.disabled = true;
  }

  function loadParty(p) {
    partyCode.value = p.code;
    partySearch.value = p.name;
    partyCity.value = p.city || "";
    resetForm();
    fetch(root.dataset.chequesUrl + "?party_code=" + encodeURIComponent(p.code), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        chqSelect.innerHTML = '<option value="">Select cheque...</option>';
        (d.cheques || []).forEach(function (c) {
          var opt = document.createElement("option");
          opt.value = c.chq_no;
          opt.textContent = c.chq_no + " - " + dmy(c.chq_dt) + " - " + c.amount;
          chqSelect.appendChild(opt);
        });
        if (!d.cheques || !d.cheques.length) show("No pending (un-dishonoured) cheque for this party.");
      });
  }

  chqSelect.addEventListener("change", function () {
    if (!chqSelect.value) { resetForm(); return; }
    fetch(root.dataset.detailUrl + "?party_code=" + encodeURIComponent(partyCode.value) +
      "&chq_no=" + encodeURIComponent(chqSelect.value), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.chq_no) { show(d.message || "Cheque entry not found."); return; }
        detail = d;
        chqDt.value = dmy(d.chq_dt);
        bankName.value = d.bank_name;
        chqAmount.value = d.amount;
        slipDt.value = dmy(d.slip_dt);
        prevAdv.value = d.prev_adv;
        totalAmt.value = d.total_amt;
        chqDisDt.value = ""; bankCharges.value = "0.00";
        render();
        confirmBtn.disabled = false;
      });
  });

  window.HelpLookup.attach(partySearch, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Party",
    onSelect: loadParty,
  });

  root.querySelector("[data-add]").addEventListener("click", function () {
    partySearch.value = ""; partyCode.value = ""; partyCity.value = "";
    resetForm(); show("");
    root.querySelector("[data-form]").hidden = false;
    confirmBtn.hidden = false;
    root.querySelector("[data-exit]").hidden = false;
    partySearch.focus();
  });

  confirmBtn.addEventListener("click", function () {
    if (!partyCode.value || !chqSelect.value) { show("Select a party and a cheque first."); return; }
    if (!chqDisDt.value) { show("Enter Cheque Dis. Date."); return; }
    askConfirm("Are You Sure?", function () {
      post(root.dataset.saveUrl, {
        party_code: partyCode.value, chq_no: chqSelect.value,
        ch_dt: ymd(chqDisDt.value), bank_charges: bankCharges.value,
      }).then(function (res) {
        if (!res.ok) { show(res.body.message || "Could not mark the cheque dishonoured."); return; }
        window.alert(res.body.message);
        loadParty({ code: partyCode.value, name: partySearch.value, city: partyCity.value });
      });
    });
  });

  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });
  render();
})();
