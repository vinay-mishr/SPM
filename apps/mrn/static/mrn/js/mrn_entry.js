/* MRN Entry — list screen + shared Add/Modify/View form. Old VFP: MRN ENTRY / grn5. */
(function () {
  "use strict";

  var root = document.querySelector("[data-mrn-entry]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var toast = document.querySelector("[data-toast]");
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;

  var initial = JSON.parse(document.getElementById("mrn-initial-data").textContent);
  var state = { rows: initial.rows || [], selectedKey: null };

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function post(url, data) {
    var body = new URLSearchParams();
    Object.keys(data || {}).forEach(function (k) { body.append(k, data[k] == null ? "" : data[k]); });
    return fetch(url, {
      method: "POST", credentials: "same-origin", body: body,
      headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" },
    }).then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; }); });
  }

  function postJson(url, data) {
    return fetch(url, {
      method: "POST", credentials: "same-origin", body: JSON.stringify(data),
      headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json" },
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

  /* --- Listing ----------------------------------------------------------------- */

  function selectedRow() {
    return state.rows.find(function (r) { return r.key === state.selectedKey; }) || null;
  }

  function render() {
    tbody.textContent = "";
    state.rows.forEach(function (row) {
      var tr = document.createElement("tr");
      tr.dataset.key = row.key;
      tr.tabIndex = 0;
      if (row.key === state.selectedKey) tr.classList.add("is-selected");
      tr.append(
        cell(row.mrn_no, "master-table__code"),
        cell(dmy(row.mrn_date)),
        cell(dmy(row.bill_date)),
        cell(row.bill_no),
        cell(row.party_name || row.party_code),
        cell(row.city),
        cell(row.ac_transferred),
        cell(row.uname)
      );
      tbody.appendChild(tr);
    });
    emptyNote.hidden = state.rows.length > 0;
    updateToolbar();
  }

  function updateToolbar() {
    var hasSelection = Boolean(selectedRow());
    root.querySelectorAll('[data-action="modify"], [data-action="delete"], [data-action="view"], [data-action="close"], [data-action="print"]').forEach(function (btn) {
      btn.disabled = !hasSelection;
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

  function currentQuery() {
    var params = new URLSearchParams();
    params.set("start_date", window.DateMask.toIso(startDate.value));
    params.set("end_date", window.DateMask.toIso(endDate.value));
    return params;
  }

  function refresh(selectKey) {
    return fetchJson(root.dataset.listUrl + "?" + currentQuery().toString()).then(function (res) {
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

  /* --- Password re-confirmation (Modify / Delete / Close) ------------------------ */

  var reauthDialog = document.getElementById("mrn-reauth-dialog");
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
      if (!res.ok) {
        reauthAlert.textContent = res.body.message || "Invalid password.";
        reauthAlert.hidden = false;
        return;
      }
      reauthDialog.close();
      if (reauthPending) reauthPending();
    });
  });
  reauthDialog.querySelector("[data-reauth-cancel]").addEventListener("click", function () { reauthDialog.close(); });

  /* --- Close MRN ----------------------------------------------------------------- */

  var closeDialog = document.getElementById("mrn-close-dialog");
  var closeAlert = closeDialog.querySelector("[data-close-alert]");

  function doClose() {
    var row = selectedRow();
    if (!row) return;
    closeAlert.hidden = true;
    closeDialog.querySelector("[data-close-question]").textContent = "Close MRN " + row.mrn_no + "? Are you sure?";
    closeDialog.showModal();
  }
  closeDialog.querySelector("[data-close-yes]").addEventListener("click", function () {
    var row = selectedRow();
    if (!row) return;
    post(root.dataset.closeUrl, { div: row.div, mrn_no: row.mrn_no }).then(function (res) {
      if (!res.ok) {
        closeAlert.textContent = res.body.message || "Could not close this MRN.";
        closeAlert.hidden = false;
        return;
      }
      closeDialog.close();
      showToast(res.body.message);
      refresh(row.key);
    });
  });
  closeDialog.querySelector("[data-close-no]").addEventListener("click", function () { closeDialog.close(); });

  /* --- Delete ---------------------------------------------------------------------- */

  var deleteDialog = document.getElementById("mrn-delete-dialog");
  var deleteAlert = deleteDialog.querySelector("[data-delete-alert]");

  function doDelete() {
    deleteAlert.hidden = true;
    deleteDialog.showModal();
  }
  deleteDialog.querySelector("[data-delete-yes]").addEventListener("click", function () {
    var row = selectedRow();
    if (!row) return;
    post(root.dataset.deleteUrl, { div: row.div, mrn_no: row.mrn_no }).then(function (res) {
      if (!res.ok) {
        deleteAlert.textContent = res.body.message || "Could not delete this MRN.";
        deleteAlert.hidden = false;
        return;
      }
      deleteDialog.close();
      showToast(res.body.message);
      refresh();
    });
  });
  deleteDialog.querySelector("[data-delete-no]").addEventListener("click", function () { deleteDialog.close(); });

  /* --- Print options (View / Print / Print PDF / WhatsApp / Exit) ----------------- */
  /* Same consolidated dialog pattern as the Purchase Order and Pending PO
     Reminder screens -- Print no longer prints immediately, it opens this
     dialog instead. */

  var printOptionsDialog = document.getElementById("mrn-print-options-dialog");

  function printUrl(row, preview) {
    var url = root.dataset.printUrlTemplate.replace("__DIV__", encodeURIComponent(row.div)).replace("__MRNNO__", encodeURIComponent(row.mrn_no));
    return preview ? url + "?preview=1" : url;
  }
  function pdfUrl(row) {
    return root.dataset.pdfUrlTemplate.replace("__DIV__", encodeURIComponent(row.div)).replace("__MRNNO__", encodeURIComponent(row.mrn_no));
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
  /* No WhatsApp Business API is configured in this project, so there's no way to
     actually attach and send a PDF from the server -- same limitation as the
     Purchase Order module's own WhatsApp flow. This creates a public share link
     to the real MRN PDF and opens the party's WhatsApp chat with the message
     (MRN details + that link) already filled in; attaching/sending is the
     person's own last step, never claimed as done automatically here. */

  var whatsappDialog = document.getElementById("mrn-whatsapp-dialog");
  var whatsappParty = whatsappDialog.querySelector("[data-whatsapp-party]");
  var whatsappMobile = whatsappDialog.querySelector("[data-whatsapp-mobile]");
  var whatsappAlert = whatsappDialog.querySelector("[data-whatsapp-alert]");

  function openWhatsAppDialog(row) {
    whatsappAlert.hidden = true;
    whatsappParty.value = row.party_name || "";
    whatsappMobile.value = row.party_mobile || "";
    whatsappDialog.dataset.div = row.div;
    whatsappDialog.dataset.mrnNo = row.mrn_no;
    whatsappDialog.showModal();
    whatsappMobile.focus();
  }

  function normalizeMobile(raw) {
    var digits = (raw || "").replace(/\D/g, "");
    if (digits.length === 10) return "91" + digits; // bare 10-digit Indian number -> add the country code
    if (digits.length === 12 && digits.startsWith("91")) return digits;
    return null;
  }

  whatsappDialog.querySelector("[data-whatsapp-send]").addEventListener("click", function () {
    var mobile = normalizeMobile(whatsappMobile.value);
    if (!mobile) {
      whatsappAlert.textContent = "Enter a valid 10-digit mobile number.";
      whatsappAlert.hidden = false;
      return;
    }
    var div = whatsappDialog.dataset.div, mrnNo = whatsappDialog.dataset.mrnNo;
    var sendBtn = whatsappDialog.querySelector("[data-whatsapp-send]");
    sendBtn.disabled = true;
    // Open the tab NOW, synchronously, inside the click -- popup blockers only
    // allow window.open() during the click itself; calling it later, once the
    // fetch below resolves, silently does nothing.
    var waTab = window.open("", "_blank");
    var url = root.dataset.shareUrlTemplate.replace("__DIV__", encodeURIComponent(div)).replace("__MRNNO__", encodeURIComponent(mrnNo));
    postJson(url, {}).then(function (res) {
      sendBtn.disabled = false;
      if (!res.ok) {
        if (waTab) waTab.close();
        whatsappAlert.textContent = res.body.message || "Could not create a share link.";
        whatsappAlert.hidden = false;
        return;
      }
      var lines = [
        "Dear " + (whatsappParty.value || "Sir/Madam") + ",",
        "Please find your Material Receipt Note (MRN) details below.",
        "MRN No: " + mrnNo,
        "Download MRN PDF:",
        res.body.url,
        "Thank you.",
        "SP MACHINES",
      ];
      whatsappDialog.close();
      var waUrl = "https://wa.me/" + mobile + "?text=" + encodeURIComponent(lines.join("\n"));
      if (waTab) waTab.location.href = waUrl; else window.open(waUrl, "_blank");
    }).catch(function () {
      sendBtn.disabled = false;
      if (waTab) waTab.close();
      whatsappAlert.textContent = "Could not reach the server.";
      whatsappAlert.hidden = false;
    });
  });
  whatsappDialog.querySelector("[data-whatsapp-back]").addEventListener("click", function () { whatsappDialog.close(); });

  /* --- Toolbar --------------------------------------------------------------------- */

  var actions = {
    add: function () { window.SPMrnForm.open("add", null); },
    modify: function () {
      var row = selectedRow();
      if (!row) return;
      if (row.mrn_closed === "Y") { showToast("MRN is Closed, Unable to Modify.", "error"); return; }
      if (row.ac_transferred === "Y") { showToast("A/C TRANSFERED, Unable to Modify.", "error"); return; }
      window.SPMrnForm.open("modify", row);
    },
    view: function () { var row = selectedRow(); if (row) window.SPMrnForm.open("view", row); },
    "delete": function () {
      var row = selectedRow();
      if (!row) return;
      if (row.mrn_closed === "Y") { showToast("MRN is Closed, Unable to Delete.", "error"); return; }
      requireReauth(doDelete);
    },
    close: function () {
      if (selectedRow()) doClose();
    },
    print: function () {
      var row = selectedRow();
      if (!row) return;
      printOptionsDialog.querySelector("[data-print-mrn-no]").value = row.mrn_no;
      printOptionsDialog.querySelector("[data-print-party]").value = row.party_name || row.party_code;
      printOptionsDialog.showModal();
    },
    refresh: function () { refresh(); },
    exit: function () { window.location.href = root.dataset.exitUrl; },
  };
  root.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function () { var fn = actions[btn.dataset.action]; if (fn) fn(); });
  });

  window.SPMrnEntry = { refresh: refresh, post: post, postJson: postJson, fetchJson: fetchJson, dmy: dmy, showToast: showToast };

  render();
})();
