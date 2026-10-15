/* GST Debit Note: list (date range, party search), Add / Modify / View / Delete, Enter-key order. */
(function () {
  "use strict";

  var root = document.querySelector("[data-dn]");
  if (!root) return;

  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var canEdit = root.dataset.canEdit === "1";
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var search = root.querySelector("[data-search]");
  var rows = root.querySelector("[data-rows]");
  var alertBox = root.querySelector("[data-alert]");
  var dialog = root.parentElement.querySelector("[data-form]") || document.querySelector("[data-form]");
  var form = document.querySelector("[data-dn-form]");
  var formAlert = document.querySelector("[data-form-alert]");
  var partySearch = document.querySelector("[data-party-search]");
  var deleteDialog = document.querySelector("[data-delete-dialog]");
  var state = { rows: [], selected: null, mode: "add", key: null };
  var alertTimer = null;

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

  function selectedRow() {
    return state.rows.find(function (r) { return r.key === state.selected; }) || null;
  }

  function updateToolbar() {
    var has = Boolean(selectedRow());
    root.querySelectorAll('[data-action="modify"], [data-action="delete"], [data-action="view"]').forEach(function (b) {
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
      tr.append(cell(r.dn_no, "dn-code"), cell(dmy(r.date)), cell(r.bill_no), cell(dmy(r.bill_date)), cell(r.party_code), cell(r.party), cell(r.city), cell(r.net, "num"));
      tr.addEventListener("click", function () { state.selected = r.key; render(); });
      tr.addEventListener("dblclick", function () { state.selected = r.key; open("view"); });
      rows.appendChild(tr);
    });
    if (!state.rows.length) {
      var empty = document.createElement("tr");
      empty.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 8;
      td.textContent = "No debit notes in this date range.";
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
      if (!res.ok) { show(alertBox, res.body.message || "Could not load debit notes."); return; }
      state.rows = res.body.rows;
      if (!selectedRow()) state.selected = null;
      render();
    });
  }

  function field(name) { return form.querySelector('[data-field="' + name + '"]'); }

  function setReadonly(on) {
    form.querySelectorAll("input, textarea").forEach(function (el) { el.readOnly = on; el.disabled = false; });
    form.querySelector("[data-confirm]").hidden = on;
    partySearch.readOnly = on;
  }

  function fillTotals(res) {
    root.querySelectorAll("[data-taxable]").forEach(function (el) { el.value = (res && res.taxable && res.taxable[el.dataset.taxable]) || "0.00"; });
    ["0", "5", "12", "18", "28"].forEach(function (rate) {
      var g = (res && res.gst && res.gst[rate]) || { cgst: "0.00", sgst: "0.00", igst: "0.00" };
      form.querySelector('[data-cgst="' + rate + '"]').textContent = g.cgst;
      form.querySelector('[data-sgst="' + rate + '"]').textContent = g.sgst;
      form.querySelector('[data-igst="' + rate + '"]').textContent = g.igst;
    });
    form.querySelector("[data-total]").value = (res && res.total) || "0.00";
    form.querySelector("[data-net]").value = (res && res.net_rounded) || "0.00";
  }

  function open(mode) {
    var row = selectedRow();
    if (mode !== "add" && !row) return;
    state.mode = mode;
    state.key = mode === "add" ? null : row.key;
    show(formAlert, "");
    form.reset();
    root.parentElement.querySelector(".dn-mode");
    document.querySelector("[data-mode-label]").textContent = mode === "add" ? "Add" : mode === "modify" ? "Modify" : "View";
    if (mode === "add") {
      getJson(root.dataset.nextNoUrl).then(function (res) { field("dn_no").value = res.body.dn_no; });
      var now = new Date();
      var pad = function (n) { return String(n).padStart(2, "0"); };
      field("dn_date").value = pad(now.getDate()) + "/" + pad(now.getMonth() + 1) + "/" + now.getFullYear();
      partySearch.value = "";
      field("party_code").value = "";
      fillTotals(null);
      setReadonly(false);
      dialog.showModal();
      field("dn_date").focus();
      return;
    }
    getJson(root.dataset.detailUrlTemplate.replace("__NO__", encodeURIComponent(row.key))).then(function (res) {
      if (!res.ok) { show(alertBox, res.body.message || "Could not open the debit note."); return; }
      var d = res.body;
      field("dn_no").value = d.dn_no;
      field("dn_date").value = dmy(d.dn_date);
      field("invoice_no").value = d.invoice_no;
      field("invoice_date").value = dmy(d.invoice_date);
      partySearch.value = d.party_name;
      field("party_code").value = d.party_code;
      field("place_of_supply").value = d.place_of_supply;
      field("interstate").checked = !!d.interstate;
      field("narration").value = d.narration;
      field("cess").value = d.cess;
      fillTotals({ taxable: d.taxable, gst: d.gst, total: d.total, net_rounded: d.net_rounded });
      setReadonly(mode === "view" || d.locked);
      dialog.showModal();
    });
  }

  function save() {
    show(formAlert, "");
    var taxable = {};
    root.querySelectorAll("[data-taxable]").forEach(function (el) { taxable[el.dataset.taxable] = el.value; });
    var payload = {
      key: state.mode === "modify" ? state.key : null,
      dn_no: field("dn_no").value.trim(),
      dn_date: window.DateMask.toIso(field("dn_date").value),
      invoice_no: field("invoice_no").value.trim(),
      invoice_date: window.DateMask.toIso(field("invoice_date").value),
      party_code: field("party_code").value.trim(),
      place_of_supply: field("place_of_supply").value.trim(),
      interstate: field("interstate").checked,
      narration: field("narration").value,
      cess: field("cess").value,
      taxable: taxable,
    };
    post(root.dataset.saveUrl, payload).then(function (res) {
      if (!res.ok) {
        show(formAlert, res.body.message || "Could not save the debit note.");
        var first = Object.keys(res.body.errors || {})[0];
        if (first && field(first)) field(first).focus();
        return;
      }
      dialog.close();
      show(alertBox, res.body.message);
      refresh();
    });
  }

  /* Enter-key order: D.N. date, invoice no, invoice date, party, place of supply, narration, rates, cess, then CONFIRM. */
  var order = [field("dn_date"), field("invoice_no"), field("invoice_date"), partySearch, field("place_of_supply"),
    field("narration")];
  form.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" || e.target.tagName !== "INPUT" && e.target.tagName !== "TEXTAREA") return;
    var i = order.indexOf(e.target);
    if (i === -1) return;
    e.preventDefault();
    (order[i + 1] || form.querySelector("[data-confirm]")).focus();
  });

  window.HelpLookup.attach(partySearch, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Party",
    onSelect: function (row) { field("party_code").value = row.code; partySearch.value = row.name; },
  });

  form.querySelector("[data-confirm]").addEventListener("click", function () {
    askConfirm("Are You Sure?", save);
  });
  form.querySelectorAll("[data-form-exit]").forEach(function (b) { b.addEventListener("click", function () { dialog.close(); }); });
  form.querySelectorAll("[data-taxable]").forEach(function () {});

  root.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var a = btn.dataset.action;
      if (a === "add") open("add");
      else if (a === "modify") open("modify");
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
    post(root.dataset.deleteUrl, { dn_no: row.key }).then(function (res) {
      show(alertBox, res.body.message || "");
      state.selected = null;
      refresh();
    });
  });
  deleteDialog.querySelector("[data-delete-no]").addEventListener("click", function () { deleteDialog.close(); });

  startDate.value = window.DateMask.toDisplay(root.dataset.startDate || new Date().toISOString().slice(0, 10));
  endDate.value = window.DateMask.toDisplay(new Date().toISOString().slice(0, 10));
  search.addEventListener("input", function () { clearTimeout(search._t); search._t = setTimeout(refresh, 250); });
  startDate.addEventListener("change", refresh);
  endDate.addEventListener("change", refresh);
  refresh();
})();
