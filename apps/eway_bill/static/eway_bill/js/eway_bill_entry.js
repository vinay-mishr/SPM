/* E-Way Bill: list of eligible GST invoices (apps.eway_bill, built entirely on
   apps.gst_invoice's own data) + right-hand response/status/generate panel. */
(function () {
  "use strict";

  var root = document.querySelector("[data-eb]");
  if (!root) return;

  var canEdit = root.dataset.canEdit === "1";
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var search = root.querySelector("[data-search]");
  var rows = root.querySelector("[data-rows]");
  var alertBox = root.querySelector("[data-alert]");
  var detailBox = root.querySelector("[data-detail]");
  var jsonBtn = root.querySelector('[data-action="json"]');
  var printBtn = root.querySelector('[data-action="print"]');
  var tokenBtn = root.querySelector('[data-action="token"]');
  var tokenStatus = root.querySelector("[data-token-status]");
  var state = { rows: [], selected: null, busy: false, tokenBusy: false };
  var tokenState = { full: null, revealed: false };
  var alertTimer = null;

  function csrfToken() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : "";
  }

  function show(msg) {
    alertBox.textContent = msg || "";
    alertBox.hidden = !msg;
    if (msg) {
      clearTimeout(alertTimer);
      alertTimer = setTimeout(function () { alertBox.hidden = true; }, 6000);
    }
  }

  function post(url, data) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken(), "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(data || {}),
    }).then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); });
  }

  function getJson(url) {
    return fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); });
  }

  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (cls) td.className = cls;
    return td;
  }

  function statusClass(label) {
    return "eb-status eb-status--" + String(label || "").toLowerCase().replace(/\s+/g, "_");
  }

  function render() {
    rows.textContent = "";
    state.rows.forEach(function (r, i) {
      var tr = document.createElement("tr");
      tr.dataset.key = r.bill_no;
      if (r.bill_no === state.selected) tr.classList.add("is-selected");
      tr.append(
        cell(i + 1), cell(r.bill_no), cell(r.date), cell(r.party || r.city),
        cell(r.net_amount, "num")
      );
      var statusTd = document.createElement("td");
      var badge = document.createElement("span");
      badge.className = statusClass(r.eway_status);
      badge.textContent = r.eway_status;
      statusTd.appendChild(badge);
      tr.appendChild(statusTd);
      tr.append(cell(r.eway_bill_no || "-"), cell(r.ack_no || "-"));
      tr.addEventListener("click", function () { selectBill(r.bill_no); });
      rows.appendChild(tr);
    });
    if (!state.rows.length) {
      var empty = document.createElement("tr");
      empty.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 8;
      td.textContent = "No GST invoices in this date range.";
      empty.appendChild(td);
      rows.appendChild(empty);
    }
  }

  function refresh() {
    var params = new URLSearchParams();
    params.set("start_date", window.DateMask.toIso(startDate.value));
    params.set("end_date", window.DateMask.toIso(endDate.value));
    params.set("search", search.value.trim());
    getJson(root.dataset.listUrl + "?" + params.toString()).then(function (res) {
      if (!res.ok) { show(res.body.message || "Could not load the invoice list."); return; }
      state.rows = res.body.rows;
      render();
    });
  }

  function fieldRow(label, value) {
    return "<dt>" + label + "</dt><dd>" + (value == null || value === "" ? "&mdash;" : escapeHtml(value)) + "</dd>";
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function renderDetail(data) {
    var inv = data.invoice, e = data.eway;
    var html = "";

    html += "<h3>Invoice</h3><dl class=\"eb-kv\">"
      + fieldRow("Bill No", inv.bill_no) + fieldRow("Date", inv.date)
      + fieldRow("Party", inv.party_name || inv.cash_party_name)
      + fieldRow("GSTIN", inv.gst_no) + fieldRow("Net Amount", inv.net_amount)
      + "</dl>";

    html += "<h3>E-Way Bill Status</h3><dl class=\"eb-kv\">"
      + fieldRow("Status", e.status_label)
      + fieldRow("IRN", e.irn) + fieldRow("Ack No", e.ack_no)
      + fieldRow("E-Way Bill No", e.eway_bill_no)
      + fieldRow("Valid Upto", e.valid_upto)
      + "</dl>";

    if (e.last_error) {
      html += '<div class="eb-errors"><strong>Last error:</strong> ' + escapeHtml(e.last_error) + "</div>";
    }

    if (data.validation.length) {
      html += '<div class="eb-errors"><strong>Before you can generate:</strong><ul>'
        + data.validation.map(function (m) { return "<li>" + escapeHtml(m) + "</li>"; }).join("")
        + "</ul></div>";
    }

    // Vehicle No, Recipient PIN and the party's default Transporter already
    // come straight from the database (vehi_no on the invoice; pin/ctrp on
    // the party record) -- shown read-only, not re-entered here. Only the
    // four fields with no source anywhere in the schema stay editable.
    html += "<h3>From Records (read-only)</h3><dl class=\"eb-kv\">"
      + fieldRow("Vehicle No", e.vehicle_no)
      + fieldRow("Recipient PIN", e.recipient_pincode)
      + fieldRow("Transporter", e.transporter_name)
      + "</dl>";

    html += '<h3>Transport Details (not in the database -- enter manually)</h3><div class="eb-form">'
      + '<div class="eb-form-row">'
      + '<label>Transporter GSTIN <input data-f="transporter_gstin" value="' + escapeHtml(e.transporter_gstin) + '"></label>'
      + '<label>Transport Mode <select data-f="transport_mode">'
      + ['', '1|Road', '2|Rail', '3|Air', '4|Ship'].map(function (o) {
          var p = o.split("|"); var v = p[0]; var l = p[1] || "Select";
          return '<option value="' + v + '"' + (e.transport_mode === v ? " selected" : "") + ">" + l + "</option>";
        }).join("")
      + '</select></label>'
      + '</div><div class="eb-form-row">'
      + '<label>Transport Doc No <input data-f="transport_doc_no" value="' + escapeHtml(e.transport_doc_no) + '"></label>'
      + '<label>Distance (km) <input data-f="distance_km" value="' + escapeHtml(e.distance_km || "") + '"></label>'
      + '</div></div>';

    html += '<div class="eb-actions">'
      + '<button type="button" class="btn btn--secondary" data-save-transport' + (canEdit ? "" : " disabled") + '>Save Transport Details</button>'
      + '<button type="button" class="btn btn--primary" data-generate ' + (canEdit && e.status !== "GENERATED" ? "" : "disabled") + '>Generate E-Way Bill</button>'
      + "</div>";

    detailBox.innerHTML = html;

    detailBox.querySelector("[data-save-transport]") && detailBox.querySelector("[data-save-transport]").addEventListener("click", function () {
      saveTransport(inv.bill_no);
    });
    var genBtn = detailBox.querySelector("[data-generate]");
    if (genBtn) genBtn.addEventListener("click", function () { generate(inv.bill_no); });
  }

  function collectTransport() {
    var data = {};
    detailBox.querySelectorAll("[data-f]").forEach(function (el) { data[el.dataset.f] = el.value; });
    return data;
  }

  function saveTransport(billNo) {
    var data = collectTransport();
    data.bill_no = billNo;
    post(root.dataset.transportUrl, data).then(function (res) {
      if (!res.ok) { show(res.body.message || "Could not save transport details."); return; }
      show(res.body.message);
      selectBill(billNo);
    });
  }

  function generate(billNo) {
    if (state.busy) return; // prevents a repeated click from firing a duplicate request
    state.busy = true;
    var genBtn = detailBox.querySelector("[data-generate]");
    if (genBtn) { genBtn.disabled = true; genBtn.textContent = "Generating…"; }
    post(root.dataset.generateUrl, { bill_no: billNo }).then(function (res) {
      state.busy = false;
      if (!res.ok) {
        show(res.body.message || "Could not generate the e-way bill.");
        selectBill(billNo);
        return;
      }
      show(res.body.message);
      refresh();
      selectBill(billNo);
    });
  }

  function selectBill(billNo) {
    state.selected = billNo;
    render();
    jsonBtn.disabled = false;
    printBtn.disabled = false;
    jsonBtn.onclick = function () { window.open(root.dataset.jsonUrlTemplate.replace("__NO__", encodeURIComponent(billNo)), "_blank"); };
    printBtn.onclick = function () { window.open(root.dataset.printUrlTemplate.replace("__NO__", encodeURIComponent(billNo)), "_blank"); };
    detailBox.innerHTML = '<p class="eb-empty">Loading…</p>';
    getJson(root.dataset.detailUrlTemplate.replace("__NO__", encodeURIComponent(billNo))).then(function (res) {
      if (!res.ok) { show(res.body.message || "Could not load this invoice."); return; }
      renderDetail(res.body);
    });
  }

  function maskToken(t) {
    if (!t) return "";
    return t.length <= 8 ? "••••••••" : t.slice(0, 4) + "••••••••" + t.slice(-4);
  }

  function renderTokenStatus(expiresAt) {
    tokenStatus.hidden = false;
    var expiryText = expiresAt ? new Date(expiresAt).toLocaleString() : "unknown";
    tokenStatus.innerHTML = "Token ready &mdash; expires " + escapeHtml(expiryText)
      + ' <code data-token-value>' + escapeHtml(tokenState.revealed ? tokenState.full : maskToken(tokenState.full)) + "</code>"
      + ' <button type="button" data-token-toggle>' + (tokenState.revealed ? "Hide" : "Show") + "</button>";
    tokenStatus.querySelector("[data-token-toggle]").addEventListener("click", function () {
      tokenState.revealed = !tokenState.revealed;
      renderTokenStatus(expiresAt);
    });
  }

  function requestToken() {
    if (state.tokenBusy) return; // prevents a repeated click from firing a duplicate request
    state.tokenBusy = true;
    tokenBtn.disabled = true;
    var prevText = tokenBtn.textContent;
    tokenBtn.textContent = "Requesting…";
    post(root.dataset.tokenUrl, {}).then(function (res) {
      state.tokenBusy = false;
      tokenBtn.disabled = !canEdit;
      tokenBtn.textContent = prevText;
      if (!res.ok) {
        tokenStatus.hidden = true;
        show(res.body.message || "Could not get a token from the e-way bill provider.");
        return;
      }
      tokenState.full = res.body.token;
      tokenState.revealed = false;
      renderTokenStatus(res.body.expires_at);
    });
  }

  if (tokenBtn) tokenBtn.addEventListener("click", requestToken);

  root.querySelector('[data-action="refresh"]').addEventListener("click", refresh);
  root.querySelector('[data-action="exit"]').addEventListener("click", function () {
    window.location.href = "/";
  });
  search.addEventListener("input", function () { clearTimeout(search._t); search._t = setTimeout(refresh, 250); });
  startDate.addEventListener("change", refresh);
  endDate.addEventListener("change", refresh);

  var today = window.DateMask.toDisplay(new Date().toISOString().slice(0, 10));
  startDate.value = today;
  endDate.value = today;
  refresh();
})();
