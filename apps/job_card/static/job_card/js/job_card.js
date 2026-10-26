/* Job Card Entry -- list, Add / Modify / View form, Receive, Close, Delete. Old VFP: JOB ENTRY. */
(function () {
  "use strict";

  var root = document.querySelector("[data-job-card]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var search = root.querySelector("[data-search]");
  var toast = document.querySelector("[data-toast]");
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var canEdit = root.dataset.canEdit === "1";
  var initial = JSON.parse(document.getElementById("jc-initial-data").textContent);
  var state = { rows: [], selectedKey: null, mode: "add", key: null, productCode: "" };

  var dialog = document.getElementById("jc-form-dialog");
  var form = dialog.querySelector("[data-jc-form]");
  var alertBox = dialog.querySelector("[data-form-alert]");
  var modeLabel = dialog.querySelector("[data-mode-label]");
  var lineRows = dialog.querySelector("[data-line-rows]");
  var productName = dialog.querySelector("[data-product-name]");
  var productSearch = dialog.querySelector("[data-product-search]");

  var actionDialog = document.getElementById("jc-action-dialog");
  var actionForm = actionDialog.querySelector("[data-action-form]");
  var actionFields = actionDialog.querySelector("[data-action-fields]");
  var actionAlert = actionDialog.querySelector("[data-action-alert]");
  var actionTitle = actionDialog.querySelector("#jc-action-title");
  var actionHandler = null;

  var reauthDialog = document.getElementById("jc-reauth-dialog");
  var reauthPassword = reauthDialog.querySelector("[data-reauth-password]");
  var reauthAlert = reauthDialog.querySelector("[data-reauth-alert]");
  var reauthPending = null;

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function request(method, url, data, isForm) {
    var options = { method: method, credentials: "same-origin", headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" } };
    if (data) {
      if (isForm) {
        var body = new URLSearchParams();
        Object.keys(data).forEach(function (k) { body.append(k, data[k] == null ? "" : data[k]); });
        options.body = body;
      } else {
        options.body = JSON.stringify(data);
        options.headers["Content-Type"] = "application/json";
      }
    }
    return fetch(url, options).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, body: b }; });
    });
  }

  function getJson(url) {
    return fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, body: b }; }); });
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

  /* --- List ----------------------------------------------------------------- */

  function selectedRow() { return state.rows.find(function (r) { return r.key === state.selectedKey; }) || null; }

  function updateToolbar() {
    var row = selectedRow();
    var open = row && !row.closed;
    root.querySelectorAll('[data-action]').forEach(function (b) {
      var a = b.dataset.action;
      if (a === "add" || a === "refresh" || a === "exit") return;
      if (a === "view") b.disabled = !row;
      else if (a === "receive") b.disabled = !(open && canEdit);
      else if (a === "close") b.disabled = !(open && canEdit);
      else b.disabled = !(row && canEdit && (a !== "modify" || open));
    });
  }

  function render() {
    tbody.textContent = "";
    state.rows.forEach(function (row) {
      var tr = document.createElement("tr");
      tr.dataset.key = row.key;
      tr.tabIndex = 0;
      if (row.key === state.selectedKey) tr.classList.add("is-selected");
      tr.append(cell(row.job_no, "master-table__code"), cell(dmy(row.date)), cell(row.item_name),
        cell(row.qty, "num"), cell(row.received, "num"), cell(row.closed ? "Y" : "N"));
      tbody.appendChild(tr);
    });
    emptyNote.hidden = state.rows.length > 0;
    updateToolbar();
  }

  function select(key) {
    state.selectedKey = key;
    tbody.querySelectorAll("tr").forEach(function (tr) { tr.classList.toggle("is-selected", tr.dataset.key === key); });
    updateToolbar();
  }

  function refresh(keepKey) {
    var params = new URLSearchParams();
    params.set("start_date", window.DateMask.toIso(startDate.value));
    params.set("end_date", window.DateMask.toIso(endDate.value));
    params.set("search", search.value.trim());
    return getJson(root.dataset.listUrl + "?" + params.toString()).then(function (res) {
      if (!res.ok) { showToast(res.body.message || "Could not load job cards.", "error"); return; }
      state.rows = res.body.rows || [];
      if (keepKey !== undefined) state.selectedKey = keepKey;
      if (!selectedRow()) state.selectedKey = null;
      render();
    });
  }

  tbody.addEventListener("click", function (e) { var tr = e.target.closest("tr[data-key]"); if (tr) select(tr.dataset.key); });
  tbody.addEventListener("dblclick", function (e) { var tr = e.target.closest("tr[data-key]"); if (tr) { select(tr.dataset.key); openForm("view", selectedRow()); } });

  startDate.value = window.DateMask.toDisplay(initial.start_date);
  endDate.value = window.DateMask.toDisplay(initial.end_date);
  startDate.addEventListener("change", function () { refresh(); });
  endDate.addEventListener("change", function () { refresh(); });
  var searchTimer = null;
  search.addEventListener("input", function () { clearTimeout(searchTimer); searchTimer = setTimeout(function () { refresh(); }, 250); });

  /* --- Password gate (Delete) --------------------------------------------- */

  function requireReauth(onConfirmed) {
    reauthAlert.hidden = true;
    reauthPassword.value = "";
    reauthPending = onConfirmed;
    reauthDialog.showModal();
    reauthPassword.focus();
  }

  reauthDialog.querySelector("[data-reauth-confirm]").addEventListener("click", function () {
    request("POST", root.dataset.reauthUrl, { password: reauthPassword.value }).then(function (res) {
      if (!res.ok) { reauthAlert.textContent = res.body.message || "Invalid password."; reauthAlert.hidden = false; return; }
      reauthDialog.close();
      if (reauthPending) reauthPending();
    });
  });
  reauthDialog.querySelector("[data-reauth-cancel]").addEventListener("click", function () { reauthDialog.close(); });

  /* --- Generic action dialog (Receive / Close) --------------------------- */

  function openAction(title, fields, handler) {
    actionTitle.textContent = title;
    actionFields.textContent = "";
    actionAlert.hidden = true;
    actionHandler = handler;
    fields.forEach(function (f) {
      var label = document.createElement("label");
      label.textContent = f.label;
      var input = document.createElement("input");
      input.name = f.name;
      input.value = f.value || "";
      input.inputMode = f.numeric ? "decimal" : "text";
      if (f.date) { input.setAttribute("data-date-mask", ""); input.placeholder = "dd/mm/yyyy"; input.maxLength = 10; }
      label.appendChild(input);
      actionFields.appendChild(label);
      if (f.date) window.DateMask.attach(input);
    });
    actionDialog.showModal();
    var first = actionFields.querySelector("input");
    if (first) first.focus();
  }

  function actionValues() {
    var out = {};
    actionFields.querySelectorAll("input").forEach(function (i) { out[i.name] = i.dataset.dateMask !== undefined || i.hasAttribute("data-date-mask") ? window.DateMask.toIso(i.value) : i.value.trim(); });
    return out;
  }

  actionForm.addEventListener("submit", function (e) {
    e.preventDefault();
    if (!actionHandler) return;
    actionHandler(actionValues()).then(function (res) {
      if (!res.ok) { actionAlert.textContent = res.body.message || "Could not complete."; actionAlert.hidden = false; return; }
      actionDialog.close();
      showToast(res.body.message || "Done.");
      refresh(res.body.job_no);
      if (dialog.open) openForm("modify", { key: res.body.job_no });
    });
  });
  actionDialog.querySelector("[data-action-cancel]").addEventListener("click", function () { actionDialog.close(); });

  /* --- Form ---------------------------------------------------------------- */

  function field(name) { return form.querySelector('[data-field="' + name + '"]'); }

  function setLocked(locked) {
    form.querySelectorAll("input").forEach(function (el) {
      if (el.dataset.field === "received_qty" || el.dataset.field === "rejected" || el.dataset.field === "close_date" || el.dataset.field === "time_taken" || el.dataset.field === "received") { el.readOnly = true; return; }
      el.readOnly = locked;
    });
    productSearch.readOnly = locked;
    form.querySelectorAll('[data-form-save]').forEach(function (b) { b.hidden = locked; });
  }

  function renderLines(issued, received) {
    lineRows.textContent = "";
    var all = issued.map(function (l) { return ["Issue", l]; }).concat(received.map(function (l) { return ["Receive", l]; }));
    if (!all.length) {
      var tr = document.createElement("tr");
      tr.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 5;
      td.textContent = "No component lines yet.";
      tr.appendChild(td);
      lineRows.appendChild(tr);
      return;
    }
    all.forEach(function (pair) {
      var tr = document.createElement("tr");
      tr.append(cell(pair[0]), cell(pair[1].part_code), cell(pair[1].part_name), cell(pair[1].qty, "num"), cell(dmy(pair[1].date)));
      lineRows.appendChild(tr);
    });
  }

  function fillForm(data) {
    field("job_no").value = data.job_no || "";
    field("job_date").value = dmy(data.job_date);
    field("item_code").value = data.item_code || "";
    productSearch.value = data.item_code || "";
    productName.textContent = data.item_name || "";
    field("qty").value = data.qty || "";
    field("received_qty").value = data.received_qty || "0";
    field("rejected").value = data.rejected || "0";
    field("close_date").value = dmy(data.close_date);
    field("supervisor").value = data.supervisor || "";
    field("start_date").value = dmy(data.start_date);
    field("time_taken").value = data.time_taken || "0.00";
    field("received").value = data.received || "0";
    renderLines(data.issued || [], data.received_lines || []);
  }

  function openForm(mode, row) {
    var isAdd = mode === "add";
    state.mode = mode;
    state.key = isAdd ? null : row.key;
    modeLabel.textContent = isAdd ? "Add" : mode === "modify" ? "Modify" : "View";
    alertBox.hidden = true;
    form.reset();
    productName.textContent = "";
    lineRows.textContent = "";
    if (isAdd) {
      getJson(root.dataset.nextNoUrl).then(function (res) { field("job_no").value = res.body.job_no || ""; });
      var now = new Date();
      var pad = function (n) { return String(n).padStart(2, "0"); };
      field("job_date").value = pad(now.getDate()) + "/" + pad(now.getMonth() + 1) + "/" + now.getFullYear();
      setLocked(false);
      productSearch.readOnly = false;
      dialog.showModal();
      return;
    }
    getJson(root.dataset.detailUrlTemplate.replace("__JOBNO__", encodeURIComponent(row.key))).then(function (res) {
      if (!res.ok) { showToast(res.body.message || "Could not open job card.", "error"); return; }
      fillForm(res.body);
      setLocked(mode === "view" || res.body.closed || res.body.sub_assembly);
      productSearch.readOnly = true;
      if (mode === "modify") {
        field("qty").readOnly = true;
        productSearch.readOnly = true;
      }
      dialog.showModal();
    });
  }

  window.HelpLookup.attach(productSearch, {
    endpoint: root.dataset.itemsUrl, resultsKey: "items", valueField: "code",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "unit", label: "Unit" }],
    title: "Product",
    onSelect: function (row) {
      field("item_code").value = row.code;
      productName.textContent = row.name;
    },
  });

  function save() {
    alertBox.hidden = true;
    var payload = {
      key: state.key,
      job_no: field("job_no").value.trim(),
      job_date: window.DateMask.toIso(field("job_date").value),
      item_code: field("item_code").value.trim(),
      qty: field("qty").value.trim(),
      supervisor: field("supervisor").value.trim(),
      start_date: window.DateMask.toIso(field("start_date").value),
    };
    request("POST", root.dataset.saveUrl, payload).then(function (res) {
      if (!res.ok) {
        var errs = res.body.errors || {};
        var first = Object.keys(errs)[0];
        alertBox.textContent = res.body.message || "Could not save.";
        alertBox.hidden = false;
        if (first && field(first)) field(first).focus();
        return;
      }
      dialog.close();
      showToast(res.body.message || "Saved.");
      refresh(res.body.job_no);
    });
  }

  form.querySelector("[data-form-save]").addEventListener("click", save);

  dialog.querySelectorAll("[data-form-exit]").forEach(function (b) { b.addEventListener("click", function () { dialog.close(); }); });

  /* --- Toolbar ------------------------------------------------------------- */

  function receiveAction() {
    var row = selectedRow();
    if (!row) return;
    openAction("Receive against " + row.job_no, [{ name: "qty", label: "Receive qty", numeric: true }], function (v) {
      return request("POST", root.dataset.receiveUrl, { job_no: row.key, qty: v.qty });
    });
  }

  function closeAction() {
    var row = selectedRow();
    if (!row) return;
    openAction("Close " + row.job_no, [
      { name: "close_date", label: "Close date", date: true, value: dmy(new Date().toISOString().slice(0, 10)) },
      { name: "received", label: "Product received", numeric: true, value: "0" },
      { name: "waste", label: "Net weight (waste)", numeric: true, value: "0" },
      { name: "time_taken", label: "Time taken (hrs)", numeric: true, value: "0" },
    ], function (v) {
      return request("POST", root.dataset.closeUrl, { job_no: row.key, close_date: v.close_date, received: v.received, waste: v.waste, time_taken: v.time_taken });
    });
  }

  function deleteAction() {
    var row = selectedRow();
    if (!row) return;
    requireReauth(function () {
      askConfirm("Delete job card " + row.job_no + "?", function () {
        request("POST", root.dataset.deleteUrl, { job_no: row.key }).then(function (res) {
          if (!res.ok) { showToast(res.body.message || "Could not delete.", "error"); return; }
          showToast(res.body.message);
          refresh();
        });
      });
    });
  }

  var actions = {
    add: function () { openForm("add", null); },
    modify: function () { var row = selectedRow(); if (row) openForm("modify", row); },
    view: function () { var row = selectedRow(); if (row) openForm("view", row); },
    receive: receiveAction,
    close: closeAction,
    "delete": deleteAction,
    refresh: function () { refresh(); },
    exit: function () { window.location.href = root.dataset.exitUrl; },
  };
  root.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function () { var fn = actions[btn.dataset.action]; if (fn) fn(); });
  });

  render();
  refresh();
})();
