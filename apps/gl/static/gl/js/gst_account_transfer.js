/* Accounts > Data Entry > GST Account Transfer: list of closed, unposted
   MRNs; ADD loads a header (confirmed columns only -- see the module
   docstring on the backend). The tax grid/CONFIRM are read-only/disabled
   until the GST-slab schema is confirmed. */
(function () {
  "use strict";

  var root = document.querySelector("[data-gat]");
  if (!root) return;

  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var rows = root.querySelector("[data-rows]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var search = root.querySelector("[data-search]");
  var alertBox = root.querySelector("[data-alert]");

  var dialog = document.querySelector("[data-form]");
  var form = dialog.querySelector("[data-gat-form]");
  var formAlert = dialog.querySelector("[data-form-alert]");
  var confirmBtn = dialog.querySelector("[data-confirm]");

  var listState = { rows: [], selected: null };

  function field(name) { return form.querySelector('[data-field="' + name + '"]'); }
  function show(box, msg) { box.textContent = msg || ""; box.hidden = !msg; }
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

  function getJson(url) {
    return fetch(url, { credentials: "same-origin" }).then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); });
  }
  function post(url, data) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrf, "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(data || {}),
    }).then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); });
  }

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
      tr.dataset.key = r.mrn_no;
      if (r.mrn_no === listState.selected) tr.classList.add("is-selected");
      tr.append(cell(r.mrn_no), cell(dmy(r.mrn_dt)), cell(r.party_name), cell(r.city),
        cell(r.net_amount, "num"), cell(r.ac_transfer));
      tr.addEventListener("click", function () { listState.selected = r.mrn_no; renderList(); });
      rows.appendChild(tr);
    });
    if (!listState.rows.length) {
      var empty = document.createElement("tr");
      empty.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 6;
      td.textContent = "No closed MRNs in this date range.";
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
      listState.rows = res.body.rows || [];
      if (!selectedRow()) listState.selected = null;
      renderList();
    });
  }

  var formState = { cstat: "" };

  // Populates the header fields from one fetched MRN record -- shared by
  // the manual GRN NO. lookup (loadMrn) and the ADD-mode auto-fetch
  // (loadLatestClosedMrn) so both paths fill party/invoice/dates/GR from
  // the exact same row, never mixing fields from different MRNs.
  function applyMrnData(d) {
    field("mrn_no").value = d.mrn_no;
    form.querySelector("[data-r-date]").value = dmy(d.mrn_dt);
    form.querySelector("[data-r-cacr]").value = d.ca_cr || "CR";
    form.querySelector("[data-r-invno]").value = d.bill_no;
    form.querySelector("[data-r-invdt]").value = dmy(d.bill_date);
    form.querySelector("[data-r-party]").value = d.party_name;
    form.querySelector("[data-r-partycode]").value = d.party_code;
    form.querySelector("[data-r-city]").value = d.city;
    form.querySelector("[data-r-grno]").value = d.gr_no;
    form.querySelector("[data-r-grdt]").value = dmy(d.gr_date);
    form.querySelector("[data-r-transport]").value = d.transport;
    form.querySelector("[data-r-duedt]").value = dmy(d.due_date);
    formState.cstat = d.cstat || "";
    resetGrid();
    recalc();
  }

  function loadMrn(mrnNo) {
    show(formAlert, "");
    getJson(root.dataset.mrnUrl + "?mrn_no=" + encodeURIComponent(mrnNo)).then(function (res) {
      if (!res.ok) { show(formAlert, res.body.message || "MRN not found."); return; }
      applyMrnData(res.body);
    });
  }

  // ADD mode's own auto-prefill: fetches the single latest CLOSED, unposted
  // MRN/GRN (see the backend's own get_latest_closed_mrn_no docstring) and
  // fills the header with it, same as typing its GRN NO. would. Runs once,
  // right after the form opens clean -- nothing the user typed exists yet
  // to overwrite. A 404 ("no eligible record") is not an error: the form
  // just stays clean with a plain message, ready for manual entry.
  function loadLatestClosedMrn() {
    show(formAlert, "");
    getJson(root.dataset.latestMrnUrl).then(function (res) {
      if (!res.ok) { show(formAlert, res.body.message || "No closed MRN/GRN record found."); return; }
      applyMrnData(res.body);
    });
  }

  // Tax-grid live preview only (no save path yet -- see backend docstring).
  // VFP formula: dis amt = taxable * dis% / 100; net taxable = taxable - dis
  // amt; tax amt = net taxable * rate% / 100; split CGST+SGST (half each)
  // within-state (cstat === 'W'), else full amount to IGST.
  var rateRows = Array.prototype.slice.call(form.querySelectorAll("[data-rate-rows] tr"));
  var num = function (v) { var n = parseFloat(v); return isNaN(n) ? 0 : n; };
  var fmt = function (n) { return n.toFixed(2); };

  function resetGrid() {
    rateRows.forEach(function (tr) {
      tr.querySelector("[data-pur]").value = "0.00";
      tr.querySelector("[data-dis]").value = "0.00";
    });
    ["1", "2"].forEach(function (i) {
      form.querySelector('[data-adj-name="' + i + '"]').value = "";
      form.querySelector('[data-adj-amt="' + i + '"]').value = "0.00";
    });
  }

  function recalc() {
    var totalTaxable = 0, totalGst = 0;
    rateRows.forEach(function (tr) {
      var rate = num(tr.dataset.rate);
      var pur = num(tr.querySelector("[data-pur]").value);
      var dis = num(tr.querySelector("[data-dis]").value);
      var disAmt = pur * dis / 100;
      var netTaxable = pur - disAmt;
      var gstAmt = netTaxable * rate / 100;
      var cgst = 0, sgst = 0, igst = 0;
      if (formState.cstat === "W") { cgst = gstAmt / 2; sgst = gstAmt / 2; } else { igst = gstAmt; }
      tr.querySelector("[data-taxable]").value = fmt(netTaxable);
      tr.querySelector("[data-cgst]").value = fmt(cgst);
      tr.querySelector("[data-sgst]").value = fmt(sgst);
      tr.querySelector("[data-igst]").value = fmt(igst);
      totalTaxable += netTaxable;
      totalGst += gstAmt;
    });

    var net = totalTaxable + totalGst;
    ["1", "2"].forEach(function (i) {
      var sign = form.querySelector('[data-adj-sign="' + i + '"]').value;
      var amt = num(form.querySelector('[data-adj-amt="' + i + '"]').value);
      net += sign === "L" ? -amt : amt;
    });

    form.querySelector("[data-t-total]").value = fmt(totalTaxable);
    form.querySelector("[data-t-gst]").value = fmt(totalGst);
    form.querySelector("[data-t-net]").value = fmt(net);
    form.querySelector("[data-t-rounded]").value = fmt(Math.round(net));
  }

  rateRows.forEach(function (tr) {
    tr.querySelector("[data-pur]").addEventListener("input", recalc);
    tr.querySelector("[data-dis]").addEventListener("input", recalc);
  });
  ["1", "2"].forEach(function (i) {
    form.querySelector('[data-adj-sign="' + i + '"]').addEventListener("change", recalc);
    form.querySelector('[data-adj-amt="' + i + '"]').addEventListener("input", recalc);
  });

  function triggerLookup() {
    if (field("mrn_no").value.trim()) loadMrn(field("mrn_no").value.trim());
  }
  // "change" alone only fires on blur -- Enter without then tabbing/clicking
  // away (what the field's own placeholder tells the user to do) doesn't
  // blur the field, so it's also handled explicitly here. An "input" listener
  // (debounced) on top of that fetches the party automatically as the user
  // types, without waiting for Enter or a blur at all.
  var lookupTimer = null;
  field("mrn_no").addEventListener("input", function () {
    clearTimeout(lookupTimer);
    lookupTimer = setTimeout(triggerLookup, 400);
  });
  field("mrn_no").addEventListener("change", triggerLookup);

  // Keyboard focus sequence: GRN No. -> G.R. No. -> GR Date -> Transport ->
  // Due Date -> (Amount -> Dis % -> Taxable -> CGST -> SGST -> IGST) for
  // each of the five rate rows, in the same 0/5/12/18/28 DOM order
  // recalc() already walks -> CONFIRM. Explicit tabindex values below (one
  // per sequence stop) make Tab visit every stop in this exact order too.
  var focusSequence = [field("mrn_no"), form.querySelector("[data-r-grno]"), form.querySelector("[data-r-grdt]"),
    form.querySelector("[data-r-transport]"), form.querySelector("[data-r-duedt]")];
  rateRows.forEach(function (tr) {
    ["[data-pur]", "[data-dis]", "[data-taxable]", "[data-cgst]", "[data-sgst]", "[data-igst]"].forEach(function (sel) {
      focusSequence.push(tr.querySelector(sel));
    });
  });
  focusSequence.push(confirmBtn);
  focusSequence.forEach(function (el, i) { el.tabIndex = i + 1; });

  function focusSequenceNext(el) {
    var idx = focusSequence.indexOf(el);
    if (idx > -1 && idx < focusSequence.length - 1) {
      var next = focusSequence[idx + 1];
      next.focus();
      if (next.select && next !== confirmBtn) next.select();
    }
  }
  focusSequence.forEach(function (el) {
    if (el === field("mrn_no") || el === confirmBtn) return; // each has its own handler/native behavior
    el.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      e.preventDefault();
      focusSequenceNext(el);
    });
  });
  // CONFIRM is a native <button> -- Enter while it's focused already fires
  // its one click handler on its own; no extra listener here, so it never
  // fires twice.

  field("mrn_no").addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      clearTimeout(lookupTimer);
      triggerLookup();
      focusSequenceNext(field("mrn_no"));
    }
  });

  // The 0.00 default on an editable amount/discount field is replaced
  // outright the moment the user starts typing, instead of appending after
  // it (e.g. "0.005") -- select-all on focus only when the field still
  // holds the untouched default; a genuine value the user is revisiting is
  // left alone (cursor placed normally), per the project's own existing
  // convention (apps.gl.cash_entry's own amount field does the same, just
  // unconditionally there since it's a single field, not a dirty check).
  var ZERO_VALUE = /^0(\.0+)?$/;
  rateRows.forEach(function (tr) {
    [tr.querySelector("[data-pur]"), tr.querySelector("[data-dis]")].forEach(function (el) {
      el.addEventListener("focus", function () {
        if (ZERO_VALUE.test(el.value.trim())) el.select();
      });
    });
  });

  function resetForm() {
    form.reset();
    form.querySelectorAll("input[readonly]").forEach(function (el) { el.value = ""; });
    formState.cstat = "";
    resetGrid();
    recalc();
    show(formAlert, "");
  }

  root.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var a = btn.dataset.action;
      if (a === "add") {
        resetForm();
        dialog.showModal();
        field("mrn_no").focus();
        loadLatestClosedMrn();
      } else if (a === "refresh") {
        refresh();
      } else if (a === "exit") {
        window.location.href = root.dataset.exitUrl;
      } else if (a === "modify" || a === "delete" || a === "view") {
        var row = selectedRow();
        if (!row) return;
        resetForm();
        loadMrn(row.mrn_no);
        dialog.showModal();
      }
    });
  });

  dialog.querySelector("[data-form-exit]").addEventListener("click", function () { dialog.close(); });
  dialog.addEventListener("keydown", function (e) { if (e.key === "Escape" && dialog.open) { e.preventDefault(); dialog.close(); } });

  confirmBtn.addEventListener("click", function () {
    post(root.dataset.saveUrl, {}).then(function (res) {
      show(formAlert, res.body.message || "Could not save.");
    });
  });

  [startDate, endDate].forEach(function (el) { el.addEventListener("change", refresh); });
  search.addEventListener("input", refresh);

  var today = new Date();
  var pad = function (n) { return String(n).padStart(2, "0"); };
  var todayStr = pad(today.getDate()) + "/" + pad(today.getMonth() + 1) + "/" + today.getFullYear();
  startDate.value = todayStr;
  endDate.value = todayStr;
  refresh();
})();
