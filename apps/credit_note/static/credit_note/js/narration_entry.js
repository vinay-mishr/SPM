/* GST Credit Note (Narration) Entry: list, Add / Modify / View / Delete, rate-wise totals. */
(function () {
  "use strict";

  var root = document.querySelector("[data-ie]");
  if (!root) return;

  var RATES = ["0", "5", "12", "18", "28"];
  var TAX_RATES = ["5", "12", "18", "28"]; // 0% has no GST, so no CGST/SGST/IGST to edit
  // Per-rate manual override flags: once the user edits a rate's CGST/SGST/IGST
  // directly, updateTotals() stops auto-recomputing that rate's split from the
  // taxable value / rate (but keeps including it in the GST / net totals).
  var overridden = {};

  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var canEdit = root.dataset.canEdit === "1";
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var search = root.querySelector("[data-search]");
  var rows = root.querySelector("[data-rows]");
  var alertBox = root.querySelector("[data-alert]");
  var dialog = document.querySelector("[data-form]");
  var form = document.querySelector("[data-ie-form]");
  var formAlert = document.querySelector("[data-form-alert]");
  var partySearch = document.querySelector("[data-party-search]");
  var deleteDialog = document.querySelector("[data-delete-dialog]");
  var state = { rows: [], selected: null, mode: "add", key: null, interState: false };
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

  function num(v) { return Number(v) || 0; }
  function f2(v) { return (Math.round(v * 100) / 100).toFixed(2); }

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
    root.querySelectorAll('[data-action="modify"], [data-action="delete"], [data-action="view"]').forEach(function (b) {
      b.disabled = !has || (!canEdit && b.dataset.action !== "view");
    });
    root.querySelectorAll('[data-action="print"]').forEach(function (b) { b.disabled = !has; });
  }

  function render() {
    rows.textContent = "";
    state.rows.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.dataset.key = r.key;
      tr.tabIndex = 0;
      if (r.key === state.selected) tr.classList.add("is-selected");
      tr.append(cell(r.cn_no, "cn-code"), cell(dmy(r.date)), cell(r.net, "num"), cell(r.party), cell(r.city));
      tr.addEventListener("click", function () { state.selected = r.key; render(); });
      tr.addEventListener("dblclick", function () { state.selected = r.key; open("view"); });
      rows.appendChild(tr);
    });
    if (!state.rows.length) {
      var empty = document.createElement("tr");
      empty.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 5;
      td.textContent = "No credit notes in this date range.";
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
      if (!res.ok) { show(alertBox, res.body.message || "Could not load credit notes."); return; }
      state.rows = res.body.rows;
      if (!selectedRow()) state.selected = null;
      render();
    });
  }

  function field(name) { return form.querySelector('[data-field="' + name + '"]'); }
  function disInput(r) { return form.querySelector('[data-dis="' + r + '"]'); }
  function taxableInput(r) { return form.querySelector('[data-taxable="' + r + '"]'); }
  function cgstInput(r) { return form.querySelector('[data-cgst="' + r + '"]'); }
  function sgstInput(r) { return form.querySelector('[data-sgst="' + r + '"]'); }
  function igstInput(r) { return form.querySelector('[data-igst="' + r + '"]'); }

  function updateTotals() {
    var amount = 0, gst = 0;
    RATES.forEach(function (r) {
      var t = num(taxableInput(r).value);
      var d = (t * num(disInput(r).value) / 100);
      var taxable = t - d;
      amount += taxable;
      if (r === "0") {
        form.querySelector('[data-cgst="0"]').textContent = "0.00";
        form.querySelector('[data-sgst="0"]').textContent = "0.00";
        form.querySelector('[data-igst="0"]').textContent = "0.00";
        return;
      }
      if (!overridden[r]) {
        var g = taxable * Number(r) / 100;
        if (state.interState) {
          cgstInput(r).value = "0.00";
          sgstInput(r).value = "0.00";
          igstInput(r).value = f2(g);
        } else {
          var cgst = g / 2;
          cgstInput(r).value = f2(cgst);
          sgstInput(r).value = f2(g - cgst);
          igstInput(r).value = "0.00";
        }
      }
      gst += num(cgstInput(r).value) + num(sgstInput(r).value) + num(igstInput(r).value);
    });
    var cess = num(field("cess_amt").value);
    form.querySelector("[data-amount]").value = f2(amount);
    form.querySelector("[data-gst-amount]").value = f2(gst);
    var net = amount + gst + cess;
    form.querySelector("[data-net-amount]").value = f2(net);
    form.querySelector("[data-net-rounded]").value = Math.round(net);
  }

  RATES.forEach(function (r) {
    disInput(r).addEventListener("input", updateTotals);
    taxableInput(r).addEventListener("input", updateTotals);
  });
  TAX_RATES.forEach(function (r) {
    [cgstInput(r), sgstInput(r), igstInput(r)].forEach(function (el) {
      el.addEventListener("input", function () { overridden[r] = true; updateTotals(); });
    });
  });
  field("cess_amt").addEventListener("input", updateTotals);

  window.HelpLookup.attach(partySearch, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Party",
    onSelect: function (row) {
      field("party_code").value = row.code; partySearch.value = row.name; field("city").value = row.city || "";
      state.interState = (row.supply_type || "").toUpperCase() === "I";
      updateTotals();
      field("place_of_supply").focus();
    },
  });

  function setReadonly(on) {
    form.querySelectorAll("input:not([type=hidden]), textarea").forEach(function (el) { el.readOnly = on; });
    form.querySelector("[data-confirm]").hidden = on;
  }

  function resetRates() {
    overridden = {};
    state.interState = false;
    RATES.forEach(function (r) {
      disInput(r).value = "0.00";
      taxableInput(r).value = "0.00";
    });
    TAX_RATES.forEach(function (r) {
      cgstInput(r).value = "0.00";
      sgstInput(r).value = "0.00";
      igstInput(r).value = "0.00";
    });
    field("cess_amt").value = "0.00";
  }

  function open(mode) {
    var row = selectedRow();
    if (mode !== "add" && !row) return;
    state.mode = mode;
    state.key = mode === "add" ? null : row.key;
    show(formAlert, "");
    form.reset();
    resetRates();
    document.querySelector("[data-mode-label]").textContent = mode === "add" ? "Add" : mode === "modify" ? "Modify" : "View";
    if (mode === "add") {
      getJson(root.dataset.nextNoUrl).then(function (res) { field("cn_no").value = res.body.cn_no; });
      var now = new Date();
      var pad = function (n) { return String(n).padStart(2, "0"); };
      field("cn_date").value = pad(now.getDate()) + "/" + pad(now.getMonth() + 1) + "/" + now.getFullYear();
      partySearch.value = "";
      field("city").value = "";
      setReadonly(false);
      updateTotals();
      dialog.showModal();
      field("invoice_no").focus();
      return;
    }
    getJson(root.dataset.detailUrlTemplate.replace("__NO__", encodeURIComponent(row.key))).then(function (res) {
      if (!res.ok) { show(alertBox, res.body.message || "Could not open the credit note."); return; }
      var d = res.body;
      field("cn_no").value = d.cn_no;
      field("cn_date").value = dmy(d.cn_date);
      field("pre_gst").value = d.pre_gst;
      field("invoice_no").value = d.invoice_no;
      field("invoice_date").value = dmy(d.invoice_date);
      field("place_of_supply").value = d.place_of_supply;
      partySearch.value = d.party_name;
      field("party_code").value = d.party_code;
      field("city").value = d.city || "";
      field("nar1").value = d.nar1;
      field("nar2").value = d.nar2;
      field("nar3").value = d.nar3;
      field("nar4").value = d.nar4;
      field("cess_amt").value = d.cess_amt;
      state.interState = (d.supply_type || "").toUpperCase() === "I";
      RATES.forEach(function (r) {
        taxableInput(r).value = (d.taxable || {})[r] || "0.00";
        disInput(r).value = (d.dis_pct || {})[r] || "0.00";
      });
      // Saved CGST/SGST/IGST amounts are shown exactly as stored (they may have been
      // manually edited when last saved) -- mark every rate overridden so updateTotals()
      // below only re-sums them into the totals, instead of recomputing the split.
      TAX_RATES.forEach(function (r) {
        cgstInput(r).value = (d.cgst || {})[r] || "0.00";
        sgstInput(r).value = (d.sgst || {})[r] || "0.00";
        igstInput(r).value = (d.igst || {})[r] || "0.00";
        overridden[r] = true;
      });
      updateTotals();
      setReadonly(mode === "view");
      dialog.showModal();
    });
  }

  function save() {
    show(formAlert, "");
    var taxable = {}, disPct = {}, cgst = {}, sgst = {}, igst = {};
    RATES.forEach(function (r) { taxable[r] = taxableInput(r).value; disPct[r] = disInput(r).value; });
    TAX_RATES.forEach(function (r) { cgst[r] = cgstInput(r).value; sgst[r] = sgstInput(r).value; igst[r] = igstInput(r).value; });
    var payload = {
      key: state.mode === "modify" ? state.key : null,
      cn_no: field("cn_no").value.trim(),
      cn_date: window.DateMask.toIso(field("cn_date").value),
      pre_gst: field("pre_gst").value.trim(),
      invoice_no: field("invoice_no").value.trim(),
      invoice_date: window.DateMask.toIso(field("invoice_date").value),
      place_of_supply: field("place_of_supply").value.trim(),
      party_code: field("party_code").value.trim(),
      nar1: field("nar1").value.trim(), nar2: field("nar2").value.trim(),
      nar3: field("nar3").value.trim(), nar4: field("nar4").value.trim(),
      taxable: taxable, dis_pct: disPct, cess_amt: field("cess_amt").value,
      cgst: cgst, sgst: sgst, igst: igst,
    };
    post(root.dataset.saveUrl, payload).then(function (res) {
      if (!res.ok) {
        show(formAlert, res.body.message || "Could not save the credit note.");
        var first = Object.keys(res.body.errors || {})[0];
        if (first && field(first)) field(first).focus();
        return;
      }
      dialog.close();
      show(alertBox, res.body.message);
      refresh();
    });
  }

  var focusOrder = [
    field("invoice_no"), field("invoice_date"), partySearch, field("place_of_supply"),
    field("nar1"), field("nar2"), field("nar3"), field("nar4"),
  ];

  form.addEventListener("keydown", function (e) {
    if (e.key !== "Enter") return;
    if (e.target === partySearch) return;
    var idx = focusOrder.indexOf(e.target);
    if (idx === -1) return;
    e.preventDefault();
    var next = focusOrder[idx + (e.shiftKey ? -1 : 1)];
    if (next) next.focus();
  });

  form.querySelector("[data-confirm]").addEventListener("click", function () {
    askConfirm("Are You Sure?", save);
  });
  form.querySelectorAll("[data-form-exit]").forEach(function (b) { b.addEventListener("click", function () { dialog.close(); }); });

  root.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var a = btn.dataset.action;
      if (a === "add") open("add");
      else if (a === "modify") open("modify");
      else if (a === "view") open("view");
      else if (a === "print") { var row = selectedRow(); if (row) window.open(root.dataset.printUrlTemplate.replace("__NO__", encodeURIComponent(row.key)), "_blank"); }
      else if (a === "delete") { if (selectedRow()) deleteDialog.showModal(); }
      else if (a === "refresh") refresh();
      else if (a === "exit") window.location.href = root.dataset.exitUrl;
    });
  });

  deleteDialog.querySelector("[data-delete-yes]").addEventListener("click", function () {
    var row = selectedRow();
    deleteDialog.close();
    if (!row) return;
    post(root.dataset.deleteUrl, { cn_no: row.key }).then(function (res) {
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
  refresh();
})();
