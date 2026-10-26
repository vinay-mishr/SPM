/* Money Receipt > Bad Debit Entry: write off part of a bill's balance against
   an expense ledger, without a Money Receipt. */
(function () {
  "use strict";

  var root = document.querySelector("[data-bd]");
  if (!root) return;

  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var rows = root.querySelector("[data-rows]");
  var alertBox = root.querySelector("[data-alert]");
  var dialog = document.querySelector("[data-form]");
  var form = dialog.querySelector("[data-bd-form]");
  var formAlert = dialog.querySelector("[data-form-alert]");
  var modeLabel = dialog.querySelector("[data-mode-label]");
  var confirmBtn = dialog.querySelector("[data-confirm]");
  var confirmDialog = document.querySelector("[data-confirm-dialog]");
  var list = [];
  var mode = "add"; // add | modify | delete | view
  var alertTimer = null;

  function fields(name) { return form.querySelector('[data-field="' + name + '"]'); }

  function show(box, msg) {
    box.textContent = msg || "";
    box.hidden = !msg;
    clearTimeout(alertTimer);
    if (msg) alertTimer = setTimeout(function () { box.hidden = true; }, 5000);
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

  var selectedRow = null;

  function renderList() {
    rows.textContent = "";
    if (!list.length) {
      var tr = document.createElement("tr");
      tr.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 7;
      td.textContent = "No Bad Debit entries this financial year.";
      tr.appendChild(td);
      rows.appendChild(tr);
      return;
    }
    list.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.append(cell(r.ent_no), cell(dmy(r.ent_dt)), cell(r.bill_no), cell(dmy(r.bill_dt)),
        cell(r.party_name), cell(r.city), cell(r.amt_adj, "num"));
      tr.addEventListener("click", function () {
        rows.querySelectorAll("tr").forEach(function (t) { t.classList.remove("is-sel"); });
        tr.classList.add("is-sel");
        selectedRow = r;
        setActionsEnabled(true);
      });
      rows.appendChild(tr);
    });
  }

  function setActionsEnabled(on) {
    root.querySelector('[data-action="modify"]').disabled = !on;
    root.querySelector('[data-action="delete"]').disabled = !on;
    root.querySelector('[data-action="view"]').disabled = !on;
  }

  function loadList() {
    fetch(root.dataset.listUrl, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        list = d.rows || [];
        renderList();
        selectedRow = null;
        setActionsEnabled(false);
      });
  }

  function setFieldsEnabled(on) {
    form.querySelectorAll("input").forEach(function (el) { el.readOnly = !on; });
    confirmBtn.hidden = !on;
  }

  function fillBillInfo(bill) {
    dialog.querySelector("[data-bill-amount]").value = bill ? bill.bill_amount : "0.00";
    dialog.querySelector("[data-party]").value = bill ? (bill.party_name + (bill.party_city ? ", " + bill.party_city : "")) : "";
    dialog.querySelector("[data-amount-recd]").value = bill ? bill.amount_received : "0.00";
    dialog.querySelector("[data-bal-amount]").value = bill ? bill.balance : "0.00";
  }

  function lookupBill() {
    var billNo = fields("bill_no").value.trim();
    var billDt = ymd(fields("bill_dt").value);
    if (!billNo || !billDt) return;
    fetch(root.dataset.findBillUrl + "?bill_no=" + encodeURIComponent(billNo) + "&bill_dt=" + encodeURIComponent(billDt),
      { credentials: "same-origin" })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        if (!res.ok) { show(formAlert, res.body.message || "BILL DATE NOT EXIST"); fillBillInfo(null); return; }
        fillBillInfo(res.body);
      });
  }

  function resetForm() {
    form.reset();
    fields("ent_dt").value = window.DateMask.toDisplay(new Date().toISOString().slice(0, 10));
    fields("amt_adj").value = "0.00";
    fillBillInfo(null);
    dialog.querySelector("[data-ledger-search]").value = "";
    fields("gcode").value = "";
    show(formAlert, "");
  }

  function openDialog(m, entry) {
    mode = m;
    modeLabel.textContent = m.toUpperCase();
    resetForm();
    if (m === "add") {
      fetch(root.dataset.nextNoUrl, { credentials: "same-origin" }).then(function (r) { return r.json(); })
        .then(function (d) { fields("ent_no").value = d.ent_no; });
      setFieldsEnabled(true);
      fields("ent_no").readOnly = false;
    } else if (entry) {
      fields("ent_no").value = entry.ent_no;
      fields("ent_dt").value = dmy(entry.ent_dt);
      fields("bill_no").value = entry.bill_no;
      fields("bill_dt").value = dmy(entry.bill_dt);
      fields("amt_adj").value = entry.amt_adj;
      fillBillInfo(entry.bill);
      if (entry.bill) { dialog.querySelector("[data-ledger-search]").value = entry.gcode; }
      fields("gcode").value = entry.gcode;
      setFieldsEnabled(m === "modify");
      fields("ent_no").readOnly = true;
      if (m === "modify") fields("bill_no").readOnly = false, fields("bill_dt").readOnly = false;
    }
    confirmBtn.textContent = mode === "delete" ? "DELETE" : "CONFIRM";
    dialog.showModal();
  }

  ["bill_no", "bill_dt"].forEach(function (name) {
    fields(name).addEventListener("change", lookupBill);
  });

  window.HelpLookup.attach(dialog.querySelector("[data-ledger-search]"), {
    endpoint: root.dataset.ledgersUrl, resultsKey: "ledgers", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }],
    title: "Account",
    onSelect: function (l) { fields("gcode").value = l.code; dialog.querySelector("[data-ledger-search]").value = l.name; },
  });

  root.querySelector('[data-action="add"]').addEventListener("click", function () { openDialog("add"); });
  root.querySelector('[data-action="modify"]').addEventListener("click", function () {
    if (!selectedRow) return;
    fetch(root.dataset.detailUrl + "?ent_no=" + encodeURIComponent(selectedRow.ent_no), { credentials: "same-origin" })
      .then(function (r) { return r.json(); }).then(function (d) { openDialog("modify", d); });
  });
  root.querySelector('[data-action="view"]').addEventListener("click", function () {
    if (!selectedRow) return;
    fetch(root.dataset.detailUrl + "?ent_no=" + encodeURIComponent(selectedRow.ent_no), { credentials: "same-origin" })
      .then(function (r) { return r.json(); }).then(function (d) { openDialog("view", d); });
  });
  root.querySelector('[data-action="delete"]').addEventListener("click", function () {
    if (!selectedRow) return;
    fetch(root.dataset.detailUrl + "?ent_no=" + encodeURIComponent(selectedRow.ent_no), { credentials: "same-origin" })
      .then(function (r) { return r.json(); }).then(function (d) { openDialog("delete", d); });
  });
  root.querySelector('[data-action="exit"]').addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  dialog.querySelector("[data-form-exit]").addEventListener("click", function () { dialog.close(); });

  function askConfirmDialog(message, onYes) {
    confirmDialog.querySelector("[data-confirm-message]").textContent = message;
    confirmDialog.showModal();
    function yes() { cleanup(); onYes(); }
    function no() { cleanup(); }
    function cleanup() {
      confirmDialog.close();
      confirmDialog.querySelector("[data-confirm-yes]").removeEventListener("click", yes);
      confirmDialog.querySelector("[data-confirm-no]").removeEventListener("click", no);
    }
    confirmDialog.querySelector("[data-confirm-yes]").addEventListener("click", yes);
    confirmDialog.querySelector("[data-confirm-no]").addEventListener("click", no);
  }

  function post(url, data) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrf, "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(data || {}),
    }).then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); });
  }

  confirmBtn.addEventListener("click", function () {
    if (mode === "view") { dialog.close(); return; }
    askConfirmDialog("Are You Sure?", function () {
      if (mode === "delete") {
        post(root.dataset.deleteUrl, { ent_no: fields("ent_no").value }).then(function (res) {
          if (!res.ok) { show(formAlert, res.body.message || "Could not delete."); return; }
          dialog.close();
          show(alertBox, res.body.message);
          loadList();
        });
        return;
      }
      var payload = {
        mode: mode, ent_no: fields("ent_no").value, ent_dt: ymd(fields("ent_dt").value),
        bill_no: fields("bill_no").value, bill_dt: ymd(fields("bill_dt").value),
        gcode: fields("gcode").value, amt_adj: fields("amt_adj").value,
      };
      post(root.dataset.saveUrl, payload).then(function (res) {
        if (!res.ok) { show(formAlert, res.body.message || "Could not save."); return; }
        dialog.close();
        show(alertBox, res.body.message);
        loadList();
      });
    });
  });

  loadList();
})();
