/* Single Issue Slip — list screen + shared Add/Modify/View form. Old VFP: mis1. */
(function () {
  "use strict";

  var root = document.querySelector("[data-issue-slip-entry]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var toast = document.querySelector("[data-toast]");
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;

  var initial = JSON.parse(document.getElementById("mis-initial-data").textContent);
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
      tr.append(cell(row.mis_no, "master-table__code"), cell(dmy(row.mis_date)), cell(row.uname));
      tbody.appendChild(tr);
    });
    emptyNote.hidden = state.rows.length > 0;
    updateToolbar();
  }

  function updateToolbar() {
    var hasSelection = Boolean(selectedRow());
    root.querySelectorAll('[data-action="modify"], [data-action="delete"], [data-action="view"]').forEach(function (btn) {
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

  /* --- Password re-confirmation (Modify / Delete) --------------------------------- */

  var reauthDialog = document.getElementById("mis-reauth-dialog");
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

  /* --- Delete ---------------------------------------------------------------------- */

  var deleteDialog = document.getElementById("mis-delete-dialog");
  var deleteAlert = deleteDialog.querySelector("[data-delete-alert]");

  function doDelete() {
    deleteAlert.hidden = true;
    deleteDialog.showModal();
  }
  deleteDialog.querySelector("[data-delete-yes]").addEventListener("click", function () {
    var row = selectedRow();
    if (!row) return;
    post(root.dataset.deleteUrl, { mis_no: row.mis_no }).then(function (res) {
      if (!res.ok) {
        deleteAlert.textContent = res.body.message || "Could not delete this issue slip.";
        deleteAlert.hidden = false;
        return;
      }
      deleteDialog.close();
      showToast(res.body.message);
      refresh();
    });
  });
  deleteDialog.querySelector("[data-delete-no]").addEventListener("click", function () { deleteDialog.close(); });

  /* --- Toolbar --------------------------------------------------------------------- */

  var actions = {
    add: function () { window.SPIssueSlipForm.open("add", null); },
    modify: function () {
      var row = selectedRow();
      if (!row) return;
      window.SPIssueSlipForm.open("modify", row);
    },
    view: function () { var row = selectedRow(); if (row) window.SPIssueSlipForm.open("view", row); },
    "delete": function () {
      var row = selectedRow();
      if (!row) return;
      requireReauth(doDelete);
    },
    refresh: function () { refresh(); },
    exit: function () { window.location.href = root.dataset.exitUrl; },
  };
  root.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function () { var fn = actions[btn.dataset.action]; if (fn) fn(); });
  });

  window.SPIssueSlipEntry = { refresh: refresh, post: post, postJson: postJson, fetchJson: fetchJson, dmy: dmy, showToast: showToast };

  render();
})();
