/* GST Returnable Challan Entry -- list + Add/Modify/View form. Old VFP: chl7 / GCHL8. */
(function () {
  "use strict";

  var root = document.querySelector("[data-challan-entry]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var search = root.querySelector("[data-search]");
  var toast = document.querySelector("[data-toast]");
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var canEdit = root.dataset.canEdit === "1";
  var initial = JSON.parse(document.getElementById("ch-initial-data").textContent);
  var state = { rows: initial.rows || [], selectedKey: null };

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function postJson(url, data) {
    return fetch(url, {
      method: "POST", credentials: "same-origin", body: JSON.stringify(data || {}),
      headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json" },
    }).then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; }); });
  }

  function postForm(url, data) {
    var body = new URLSearchParams();
    Object.keys(data || {}).forEach(function (k) { body.append(k, data[k] == null ? "" : data[k]); });
    return fetch(url, {
      method: "POST", credentials: "same-origin", body: body,
      headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" },
    }).then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; }); });
  }

  function fetchJson(url) {
    return fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; }); });
  }

  function dmy(iso) {
    if (!iso) return "";
    var p = String(iso).split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : iso;
  }

  function cell(text, className) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (className) td.className = className;
    return td;
  }

  /* --- Listing ---------------------------------------------------------------- */

  function selectedRow() { return state.rows.find(function (r) { return r.key === state.selectedKey; }) || null; }

  function render() {
    tbody.textContent = "";
    state.rows.forEach(function (row) {
      var tr = document.createElement("tr");
      tr.dataset.key = row.key;
      tr.tabIndex = 0;
      if (row.key === state.selectedKey) tr.classList.add("is-selected");
      tr.append(cell(row.chl_no, "master-table__code"), cell(dmy(row.date)), cell(row.party_name), cell(row.city));
      tbody.appendChild(tr);
    });
    emptyNote.hidden = state.rows.length > 0;
    updateToolbar();
  }

  function updateToolbar() {
    var has = Boolean(selectedRow());
    root.querySelectorAll('[data-action="modify"], [data-action="delete"], [data-action="view"], [data-action="print"]').forEach(function (b) {
      b.disabled = !has || (!canEdit && b.dataset.action !== "view" && b.dataset.action !== "print");
    });
  }

  function select(key) {
    state.selectedKey = key;
    tbody.querySelectorAll("tr").forEach(function (tr) { tr.classList.toggle("is-selected", tr.dataset.key === key); });
    updateToolbar();
  }

  tbody.addEventListener("click", function (e) {
    var tr = e.target.closest("tr[data-key]");
    if (tr) select(tr.dataset.key);
  });
  tbody.addEventListener("dblclick", function (e) {
    var tr = e.target.closest("tr[data-key]");
    if (tr) { select(tr.dataset.key); openView(); }
  });

  function currentQuery() {
    var params = new URLSearchParams();
    params.set("start_date", window.DateMask.toIso(startDate.value));
    params.set("end_date", window.DateMask.toIso(endDate.value));
    if (search.value.trim()) params.set("search", search.value.trim());
    return params;
  }

  function refresh(selectKey) {
    return fetchJson(root.dataset.listUrl + "?" + currentQuery().toString()).then(function (res) {
      if (!res.ok) { showToast(res.body.message || "Could not load challans.", "error"); return; }
      state.rows = res.body.rows || [];
      if (selectKey !== undefined) state.selectedKey = selectKey;
      if (!selectedRow()) state.selectedKey = null;
      render();
    });
  }

  startDate.value = window.DateMask.toDisplay(initial.start_date);
  endDate.value = window.DateMask.toDisplay(initial.end_date);
  startDate.addEventListener("change", function () { refresh(); });
  endDate.addEventListener("change", function () { refresh(); });
  search.addEventListener("input", function () { clearTimeout(search._t); search._t = setTimeout(function () { refresh(); }, 250); });

  /* --- Password re-confirmation (Modify / Delete) ------------------------------- */

  var reauthDialog = document.getElementById("ch-reauth-dialog");
  var reauthPassword = reauthDialog.querySelector("[data-reauth-password]");
  var reauthAlert = reauthDialog.querySelector("[data-reauth-alert]");
  var reauthPending = null;

  function requireReauth(onConfirmed) {
    reauthAlert.hidden = true;
    reauthPassword.value = "";
    reauthPending = onConfirmed;
    reauthDialog.showModal();
    reauthPassword.focus();
  }
  reauthDialog.querySelector("[data-reauth-confirm]").addEventListener("click", function () {
    postJson(root.dataset.reauthUrl, { password: reauthPassword.value }).then(function (res) {
      if (!res.ok) { reauthAlert.textContent = res.body.message || "Invalid password."; reauthAlert.hidden = false; return; }
      reauthDialog.close();
      if (reauthPending) reauthPending();
    });
  });
  reauthDialog.querySelector("[data-reauth-cancel]").addEventListener("click", function () { reauthDialog.close(); });

  /* --- Delete ---------------------------------------------------------------------- */

  var deleteDialog = document.getElementById("ch-delete-dialog");
  var deleteAlert = deleteDialog.querySelector("[data-delete-alert]");
  deleteDialog.querySelector("[data-delete-yes]").addEventListener("click", function () {
    var row = selectedRow();
    if (!row) return;
    postForm(root.dataset.deleteUrl, { chl_no: row.chl_no }).then(function (res) {
      if (!res.ok) { deleteAlert.textContent = res.body.message || "Could not delete."; deleteAlert.hidden = false; return; }
      deleteDialog.close();
      showToast(res.body.message);
      refresh();
    });
  });
  deleteDialog.querySelector("[data-delete-no]").addEventListener("click", function () { deleteDialog.close(); });

  /* --- Toolbar -------------------------------------------------------------------- */

  function openView() { var row = selectedRow(); if (row) window.SPChallanForm.open("view", row); }

  /* --- Print options (View / Print / Print PDF / WhatsApp / Exit) ----------------- */
  /* Same consolidated dialog pattern as the Purchase Order and MRN screens --
     Print no longer prints immediately, it opens this dialog instead. */

  var printOptionsDialog = document.getElementById("ch-print-options-dialog");
  var copyCheckboxes = printOptionsDialog.querySelectorAll('input[name="ch-copy-type"]');
  // Only one copy type makes sense at a time -- checking one unchecks the rest.
  copyCheckboxes.forEach(function (box) {
    box.addEventListener("change", function () {
      if (box.checked) copyCheckboxes.forEach(function (other) { if (other !== box) other.checked = false; });
      else box.checked = true; // always exactly one selected, never zero
    });
  });
  function copyType() {
    var checked = Array.prototype.find.call(copyCheckboxes, function (b) { return b.checked; });
    return checked ? checked.value : "";
  }

  function printUrl(row, preview) {
    var url = root.dataset.printUrlTemplate.replace("__CHLNO__", encodeURIComponent(row.chl_no));
    var params = new URLSearchParams();
    if (preview) params.set("preview", "1");
    params.set("copy", copyType());
    return url + "?" + params.toString();
  }
  function pdfUrl(row) {
    var url = root.dataset.pdfUrlTemplate.replace("__CHLNO__", encodeURIComponent(row.chl_no));
    return url + "?copy=" + encodeURIComponent(copyType());
  }

  printOptionsDialog.querySelectorAll("[data-print-action]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var action = btn.dataset.printAction;
      if (action === "exit") { printOptionsDialog.close(); return; }
      var row = selectedRow();
      if (!row) return;
      printOptionsDialog.close();
      if (action === "whatsapp") openWhatsAppDialog(row);
      else if (action === "pdf") window.open(pdfUrl(row), "_blank");
      else window.open(printUrl(row, action === "preview"), "_blank");
    });
  });

  /* --- WhatsApp -------------------------------------------------------------------- */

  var whatsappDialog = document.getElementById("ch-whatsapp-dialog");
  var whatsappParty = whatsappDialog.querySelector("[data-whatsapp-party]");
  var whatsappMobile = whatsappDialog.querySelector("[data-whatsapp-mobile]");
  var whatsappAlert = whatsappDialog.querySelector("[data-whatsapp-alert]");
  var whatsappRow = null;

  function normalizeMobile(raw) {
    var digits = (raw || "").replace(/\D/g, "");
    if (digits.length === 10) return "91" + digits;
    if (digits.length === 12 && digits.startsWith("91")) return digits;
    return null;
  }

  function openWhatsAppDialog(row) {
    whatsappAlert.hidden = true;
    whatsappParty.value = row.party_name || "";
    whatsappMobile.value = row.phone || "";
    whatsappRow = row;
    whatsappDialog.showModal();
    whatsappMobile.focus();
  }

  whatsappDialog.querySelector("[data-whatsapp-send]").addEventListener("click", function () {
    var mobile = normalizeMobile(whatsappMobile.value);
    if (!mobile) {
      whatsappAlert.textContent = "Enter a valid 10-digit mobile number.";
      whatsappAlert.hidden = false;
      return;
    }
    var row = whatsappRow;
    var shareUrl = root.dataset.shareUrlTemplate.replace("__CHLNO__", encodeURIComponent(row.chl_no));
    var sendBtn = whatsappDialog.querySelector("[data-whatsapp-send]");
    sendBtn.disabled = true;
    // Open the tab NOW, synchronously, inside the click -- popup blockers only
    // allow window.open() during the click itself; calling it later, after the
    // fetch below resolves, does nothing. Point this tab at the real wa.me URL
    // once the link is ready.
    var waTab = window.open("", "_blank");
    postJson(shareUrl, {}).then(function (res) {
      sendBtn.disabled = false;
      if (!res.ok) {
        if (waTab) waTab.close();
        whatsappAlert.textContent = res.body.message || "Could not create a share link for this challan.";
        whatsappAlert.hidden = false;
        return;
      }
      var message = "Dear " + (whatsappParty.value || "Sir/Madam") + ",\n" +
        "Please find your GST Returnable Challan below.\n" +
        "Challan No: " + row.chl_no + "\n" +
        "Download Challan PDF:\n" + res.body.url + "\n" +
        "Thank you.\nSP MACHINES";
      whatsappDialog.close();
      var waUrl = "https://wa.me/" + mobile + "?text=" + encodeURIComponent(message);
      if (waTab) waTab.location.href = waUrl; else window.open(waUrl, "_blank");
    }).catch(function () {
      sendBtn.disabled = false;
      if (waTab) waTab.close();
      whatsappAlert.textContent = "Could not reach the server.";
      whatsappAlert.hidden = false;
    });
  });
  whatsappDialog.querySelector("[data-whatsapp-back]").addEventListener("click", function () { whatsappDialog.close(); });

  var actions = {
    add: function () { window.SPChallanForm.open("add", null); },
    modify: function () {
      var row = selectedRow();
      if (!row) return;
      window.SPChallanForm.open("modify", row);
    },
    view: openView,
    print: function () {
      var row = selectedRow();
      if (!row) return;
      printOptionsDialog.querySelector("[data-print-chl-no]").value = row.chl_no;
      printOptionsDialog.querySelector("[data-print-chl-amount]").value = row.amount;
      printOptionsDialog.showModal();
    },
    "delete": function () {
      var row = selectedRow();
      if (!row) return;
      requireReauth(function () { deleteAlert.hidden = true; deleteDialog.showModal(); });
    },
    refresh: function () { refresh(); },
    exit: function () { window.location.href = root.dataset.exitUrl; },
  };
  root.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function () { var fn = actions[btn.dataset.action]; if (fn) fn(); });
  });

  window.SPChallanEntry = { refresh: refresh, postJson: postJson, fetchJson: fetchJson, showToast: showToast, dmy: dmy };
  render();
})();
