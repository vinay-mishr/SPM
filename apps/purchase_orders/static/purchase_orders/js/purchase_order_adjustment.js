/* Pending Purchase Order Adjustment — for one party, list every still-pending, not-yet-
 * adjusted PO line and let the user write an ADJ value onto each. Old VFP form: PENDING
 * PURCHASE ORDER ADJUSTMENT. */
(function () {
  "use strict";

  var root = document.querySelector("[data-po-adjustment]");
  if (!root) return;

  var canEdit = root.dataset.canEdit === "1";
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var partySearch = root.querySelector("[data-party-search]");
  var partyCode = root.querySelector("[data-party-code]");
  var runDate = root.querySelector("[data-run-date]");
  var confirmBtn = root.querySelector("[data-confirm]");
  var alertBox = root.querySelector("[data-form-alert]");
  var toast = document.querySelector("[data-toast]");

  function todayDmy() {
    var d = new Date();
    return String(d.getDate()).padStart(2, "0") + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + d.getFullYear();
  }
  runDate.value = todayDmy();

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function fetchJson(url, options) {
    return fetch(url, Object.assign({ credentials: "same-origin" }, options || {})).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; });
    });
  }

  partySearch.addEventListener("input", function () {
    if (!partySearch.value.trim()) { partyCode.value = ""; render([]); }
  });

  if (window.HelpLookup) {
    window.HelpLookup.attach(partySearch, {
      endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
      displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }], title: "Party",
      onSelect: function (row) { partyCode.value = row.code; load(); },
    });
  }

  function dmy(iso) {
    if (!iso) return "";
    var p = iso.split("-");
    return p.length === 3 ? p[2] + "-" + p[1] + "-" + p[0] : iso;
  }

  function render(rows) {
    tbody.textContent = "";
    rows.forEach(function (row) {
      var tr = document.createElement("tr");
      tr.dataset.poNo = row.po_no;
      tr.dataset.div = row.div;
      tr.dataset.partCode = row.part_code;
      [row.po_no, dmy(row.order_date), row.item_name].forEach(function (v) {
        var td = document.createElement("td");
        td.textContent = v;
        tr.appendChild(td);
      });
      [row.qty_ordered, row.qty_received, row.pending].forEach(function (v) {
        var td = document.createElement("td");
        td.className = "num";
        td.textContent = v;
        tr.appendChild(td);
      });
      var adjTd = document.createElement("td");
      var adjInput = document.createElement("input");
      adjInput.className = "form-control poa-adj-input";
      adjInput.maxLength = 1;
      adjInput.value = row.adj || "";
      adjInput.disabled = !canEdit;
      adjInput.addEventListener("input", function () { adjInput.value = adjInput.value.toUpperCase(); updateConfirmState(); });
      adjTd.appendChild(adjInput);
      tr.appendChild(adjTd);
      var codeTd = document.createElement("td");
      codeTd.textContent = row.part_code;
      codeTd.className = "master-table__code";
      tr.appendChild(codeTd);
      var divTd = document.createElement("td");
      divTd.textContent = row.div;
      tr.appendChild(divTd);
      tbody.appendChild(tr);
    });
    emptyNote.hidden = rows.length > 0;
    emptyNote.textContent = partyCode.value.trim()
      ? "No pending purchase orders found for this party."
      : "Select a party to see its pending orders.";
    updateConfirmState();
  }

  function updateConfirmState() {
    var hasAdj = Array.from(tbody.querySelectorAll(".poa-adj-input")).some(function (i) { return i.value.trim(); });
    confirmBtn.disabled = !canEdit || !hasAdj;
  }

  function load() {
    alertBox.hidden = true;
    if (!partyCode.value.trim()) { render([]); return; }
    fetchJson(root.dataset.dataUrl + "?party_code=" + encodeURIComponent(partyCode.value.trim())).then(function (res) {
      if (!res.ok) { showToast(res.body.message || "Could not load the report.", "error"); return; }
      render(res.body.rows || []);
    });
  }

  root.querySelector("[data-show]").addEventListener("click", load);

  root.querySelector("[data-exit]").addEventListener("click", function () {
    window.location.href = root.dataset.exitUrl;
  });

  confirmBtn.addEventListener("click", function () {
    alertBox.hidden = true;
    var rows = [];
    tbody.querySelectorAll("tr").forEach(function (tr) {
      var input = tr.querySelector(".poa-adj-input");
      var adj = input.value.trim();
      if (!adj) return;
      rows.push({ po_no: tr.dataset.poNo, div: tr.dataset.div, part_code: tr.dataset.partCode, adj: adj });
    });
    if (!rows.length) return;

    confirmBtn.disabled = true;
    fetchJson(root.dataset.saveUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify({ party_code: partyCode.value.trim(), rows: rows }),
    }).then(function (res) {
      if (res.ok) {
        showToast(res.body.message);
        load();
      } else {
        alertBox.textContent = res.body.message || "Could not save.";
        alertBox.hidden = false;
        confirmBtn.disabled = false;
      }
    }).catch(function () {
      alertBox.textContent = "Could not reach the server. Nothing was saved.";
      alertBox.hidden = false;
      confirmBtn.disabled = false;
    });
  });

  render([]);
  partySearch.focus();
})();
