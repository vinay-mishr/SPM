/* Product Issue -- serial-numbered issues of a product's components against an open job card. */
(function () {
  "use strict";

  var root = document.querySelector("[data-product-issue]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var search = root.querySelector("[data-search]");
  var toast = document.querySelector("[data-toast]");
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var canEdit = root.dataset.canEdit === "1";
  var initial = JSON.parse(document.getElementById("pi-initial-data").textContent);
  var state = { rows: [], selectedKey: null, mode: "add", key: null };

  var dialog = document.getElementById("pi-form-dialog");
  var form = dialog.querySelector("[data-pi-form]");
  var alertBox = dialog.querySelector("[data-form-alert]");
  var modeLabel = dialog.querySelector("[data-mode-label]");
  var lineRows = dialog.querySelector("[data-line-rows]");
  var itemSearch = dialog.querySelector("[data-item-search]");
  var itemName = dialog.querySelector("[data-item-name]");
  var jobSelect = dialog.querySelector("[data-job-select]");
  var jobDate = dialog.querySelector("[data-job-date]");
  var jobQty = dialog.querySelector("[data-job-qty]");

  var reauthDialog = document.getElementById("pi-reauth-dialog");
  var reauthPassword = reauthDialog.querySelector("[data-reauth-password]");
  var reauthAlert = reauthDialog.querySelector("[data-reauth-alert]");
  var reauthPending = null;

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function request(method, url, data) {
    var options = { method: method, credentials: "same-origin", headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" } };
    if (data) {
      options.body = JSON.stringify(data);
      options.headers["Content-Type"] = "application/json";
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
    var has = Boolean(selectedRow());
    root.querySelectorAll('[data-action="modify"], [data-action="delete"]').forEach(function (b) { b.disabled = !has || !canEdit; });
    root.querySelector('[data-action="view"]').disabled = !has;
  }

  function render() {
    tbody.textContent = "";
    state.rows.forEach(function (row) {
      var tr = document.createElement("tr");
      tr.dataset.key = row.key;
      tr.tabIndex = 0;
      if (row.key === state.selectedKey) tr.classList.add("is-selected");
      tr.append(cell(row.serial_no, "master-table__code"), cell(dmy(row.date)), cell(row.item_name), cell(row.job_no));
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
      if (!res.ok) { showToast(res.body.message || "Could not load product issues.", "error"); return; }
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

  /* --- Password gate (Delete) ------------------------------------------------ */

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

  /* --- Form ------------------------------------------------------------------- */

  function field(name) { return form.querySelector('[data-field="' + name + '"]'); }

  function renderLines(components) {
    lineRows.textContent = "";
    if (!components || !components.length) {
      var tr = document.createElement("tr");
      tr.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 4;
      td.textContent = "No component lines.";
      tr.appendChild(td);
      lineRows.appendChild(tr);
      return;
    }
    components.forEach(function (c, i) {
      var tr = document.createElement("tr");
      tr.append(cell(i + 1), cell(c.part_code), cell(c.part_name), cell(c.qty, "num"));
      lineRows.appendChild(tr);
    });
  }

  function loadOpenJobs(item, selectJob) {
    jobSelect.textContent = "";
    var placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Select an open job card";
    jobSelect.appendChild(placeholder);
    jobDate.value = "";
    jobQty.value = "";
    renderLines([]);
    if (!item) return Promise.resolve();
    return getJson(root.dataset.openJobsUrl + "?item=" + encodeURIComponent(item)).then(function (res) {
      (res.body.jobs || []).forEach(function (j) {
        var opt = document.createElement("option");
        opt.value = j.job_no;
        opt.textContent = j.job_no + "  (" + dmy(j.date) + ", qty " + j.qty + ")";
        opt.dataset.date = j.date;
        opt.dataset.qty = j.qty;
        jobSelect.appendChild(opt);
      });
      if (selectJob) jobSelect.value = selectJob;
      if (!(res.body.jobs || []).length) showToast("No open job card for this item.", "error");
    });
  }

  function loadPreview() {
    var job = jobSelect.value;
    var item = field("item_code").value;
    if (!job || !item) { jobDate.value = ""; jobQty.value = ""; renderLines([]); return; }
    var opt = jobSelect.options[jobSelect.selectedIndex];
    jobDate.value = dmy(opt.dataset.date);
    jobQty.value = opt.dataset.qty;
    getJson(root.dataset.previewUrl + "?item=" + encodeURIComponent(item) + "&job=" + encodeURIComponent(job)).then(function (res) {
      if (!res.ok) { alertBox.textContent = res.body.message || "Could not load components."; alertBox.hidden = false; renderLines([]); return; }
      alertBox.hidden = true;
      renderLines(res.body.components);
    });
  }

  jobSelect.addEventListener("change", loadPreview);

  window.HelpLookup.attach(itemSearch, {
    endpoint: root.dataset.itemsUrl, resultsKey: "items", valueField: "code",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "unit", label: "Unit" }],
    title: "Item",
    onSelect: function (row) {
      field("item_code").value = row.code;
      itemName.textContent = row.name;
      loadOpenJobs(row.code);
    },
  });

  function openForm(mode, row) {
    var isAdd = mode === "add";
    state.mode = mode;
    state.key = isAdd ? null : row.key;
    modeLabel.textContent = isAdd ? "Add" : mode === "modify" ? "Modify" : "View";
    alertBox.hidden = true;
    form.reset();
    itemName.textContent = "";
    jobSelect.textContent = "";
    renderLines([]);
    if (isAdd) {
      var now = new Date();
      var pad = function (n) { return String(n).padStart(2, "0"); };
      field("date").value = pad(now.getDate()) + "/" + pad(now.getMonth() + 1) + "/" + now.getFullYear();
      loadOpenJobs("");
      setLocked(false);
      dialog.showModal();
      return;
    }
    getJson(root.dataset.detailUrlTemplate.replace("__SERIAL__", encodeURIComponent(row.key))).then(function (res) {
      if (!res.ok) { showToast(res.body.message || "Could not open serial.", "error"); return; }
      field("serial_no").value = res.body.serial_no;
      field("date").value = dmy(res.body.date);
      field("item_code").value = res.body.item_code;
      itemSearch.value = res.body.item_code;
      itemName.textContent = res.body.item_name || "";
      jobSelect.textContent = "";
      var opt = document.createElement("option");
      opt.value = res.body.job_no;
      opt.textContent = res.body.job_no;
      jobSelect.appendChild(opt);
      jobSelect.value = res.body.job_no;
      renderLines(res.body.components);
      setLocked(mode === "view");
      if (mode === "modify") field("serial_no").readOnly = true;
      dialog.showModal();
    });
  }

  function setLocked(locked) {
    form.querySelectorAll("input").forEach(function (el) { el.readOnly = locked || el.hasAttribute("readonly"); });
    itemSearch.readOnly = locked;
    jobSelect.disabled = locked;
    form.querySelector("[data-form-save]").hidden = locked;
  }

  function save() {
    alertBox.hidden = true;
    var payload = {
      mode: state.mode === "modify" ? "modify" : "add",
      serial_no: field("serial_no").value.trim(),
      date: window.DateMask.toIso(field("date").value),
      item_code: field("item_code").value.trim(),
      job_no: jobSelect.value,
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
      refresh(res.body.serial_no);
    });
  }

  form.querySelector("[data-form-save]").addEventListener("click", save);
  dialog.querySelectorAll("[data-form-exit]").forEach(function (b) { b.addEventListener("click", function () { dialog.close(); }); });

  function deleteAction() {
    var row = selectedRow();
    if (!row) return;
    requireReauth(function () {
      askConfirm("Delete Serial No. " + row.serial_no + "? Stock will be restored.", function () {
        request("POST", root.dataset.deleteUrl, { serial_no: row.key }).then(function (res) {
          if (!res.ok) { showToast(res.body.message || "Could not delete.", "error"); return; }
          showToast(res.body.message);
          refresh();
        });
      });
    });
  }

  var actions = {
    add: function () { openForm("add", null); },
    modify: function () {
      var row = selectedRow();
      if (!row) return;
      openForm("modify", row);
    },
    view: function () { var row = selectedRow(); if (row) openForm("view", row); },
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
