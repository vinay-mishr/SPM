/* Job Entry (Sub-Assembly): ADD, MODIFY, DELETE, CLOSE, CONFIRM, EXIT. */
(function () {
  "use strict";

  var root = document.querySelector("[data-sa]");
  if (!root) return;

  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var canEdit = root.dataset.canEdit === "1";
  var alertBox = root.querySelector("[data-alert]");
  var numberInput = root.querySelector('[data-field="number"]');
  var itemSearch = root.querySelector("[data-item-search]");
  var mode = null;
  var alertTimer = null;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var listSearch = root.querySelector("[data-search]");
  var initial = JSON.parse(document.getElementById("sa-initial-data").textContent);
  var listState = { rows: [], selectedNumber: null };

  function f(name) { return root.querySelector('[data-field="' + name + '"]'); }

  function show(msg) {
    alertBox.textContent = msg || "";
    alertBox.hidden = !msg;
    clearTimeout(alertTimer);
    if (msg) alertTimer = setTimeout(function () { alertBox.hidden = true; }, 5000);
  }

  function dmy(iso) {
    var p = String(iso || "").split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : "";
  }

  function getJson(url) {
    return fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); });
  }

  function post(data) {
    return fetch(root.dataset.saveUrl, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrf, "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(data),
    }).then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); });
  }

  function setMode(m) {
    mode = m;
    var dlg = document.getElementById("sa-form-dialog");
    if (m === null) {
      if (dlg.open) dlg.close();
    } else if (!dlg.open) {
      dlg.showModal();
    }
    dlg.querySelector("[data-mode-label]").textContent = { add: "Add", modify: "Modify", delete: "Delete", close: "Close" }[m] || "";
    var editable = m === "add" || m === "modify";
    root.querySelectorAll("input").forEach(function (el) {
      if (el.type === "hidden") return;
      el.readOnly = !editable && !(m === "close" && (el.dataset.field === "produced" || el.dataset.field === "finish_rejection" || el.dataset.field === "close_date"));
    });
    numberInput.readOnly = m !== null && m !== "add";
    itemSearch.disabled = m !== "add";
    root.querySelector('[data-act="confirm"]').disabled = m === null;
  }

  function fill(d) {
    numberInput.value = d.number;
    f("job_date").value = dmy(d.job_date);
    f("item_code").value = d.item_code;
    itemSearch.value = d.item_code;
    f("qty").value = d.qty;
    f("produced").value = d.produced;
    f("finish_rejection").value = d.finish_rejection;
    f("close_date").value = dmy(d.close_date);
  }

  function clearForm() {
    root.querySelectorAll("input").forEach(function (el) { if (el !== numberInput) el.value = ""; });
  }

  function load(callback) {
    var no = numberInput.value.trim();
    if (!no) { show("Enter the job no."); return; }
    getJson(root.dataset.detailUrlTemplate.replace("__NO__", encodeURIComponent(no))).then(function (res) {
      if (!res.ok) { show(res.body.message || "Job no. not found."); return; }
      fill(res.body);
      if (callback) callback(res.body);
    });
  }

  /* --- List ----------------------------------------------------------------- */

  function cell(text, className) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (className) td.className = className;
    return td;
  }

  function renderList() {
    tbody.textContent = "";
    listState.rows.forEach(function (row) {
      var tr = document.createElement("tr");
      tr.dataset.number = row.number;
      tr.tabIndex = 0;
      if (row.number === listState.selectedNumber) tr.classList.add("is-selected");
      tr.append(cell(row.job_no), cell(dmy(row.job_date)), cell(row.item_name),
        cell(row.qty, "num"), cell(row.produced, "num"), cell(row.issued ? "Y" : "N"), cell(row.closed ? "Y" : "N"));
      tbody.appendChild(tr);
    });
    emptyNote.hidden = listState.rows.length > 0;
  }

  function selectListRow(number) {
    listState.selectedNumber = number;
    tbody.querySelectorAll("tr").forEach(function (tr) { tr.classList.toggle("is-selected", tr.dataset.number === number); });
  }

  function refreshList() {
    var params = new URLSearchParams();
    params.set("start_date", window.DateMask.toIso(startDate.value));
    params.set("end_date", window.DateMask.toIso(endDate.value));
    params.set("search", listSearch.value.trim());
    return getJson(root.dataset.listUrl + "?" + params.toString()).then(function (res) {
      if (!res.ok) { show(res.body.message || "Could not load job entries."); return; }
      listState.rows = res.body.rows || [];
      if (!listState.rows.some(function (r) { return r.number === listState.selectedNumber; })) listState.selectedNumber = null;
      renderList();
    });
  }

  tbody.addEventListener("click", function (e) {
    var tr = e.target.closest("tr[data-number]");
    if (tr) selectListRow(tr.dataset.number);
  });

  startDate.value = window.DateMask.toDisplay(initial.start_date);
  endDate.value = window.DateMask.toDisplay(initial.end_date);
  startDate.addEventListener("change", function () { refreshList(); });
  endDate.addEventListener("change", function () { refreshList(); });
  var listSearchTimer = null;
  listSearch.addEventListener("input", function () {
    clearTimeout(listSearchTimer);
    listSearchTimer = setTimeout(refreshList, 250);
  });

  var focusOrder = [numberInput, f("job_date"), itemSearch, f("qty"), f("produced"), f("finish_rejection"), f("close_date")];

  root.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" || e.target.tagName === "BUTTON") return;
    var idx = focusOrder.indexOf(e.target);
    if (idx === -1) return;
    e.preventDefault();
    if (e.target === numberInput && mode && mode !== "add") load();
    var next = focusOrder[idx + 1];
    if (next && !next.disabled) next.focus();
  });

  window.HelpLookup.attach(itemSearch, {
    endpoint: root.dataset.partsUrl, resultsKey: "parts", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "unit", label: "Unit" }],
    title: "Product",
    onSelect: function (row) {
      f("item_code").value = row.code;
      f("qty").focus();
    },
  });

  function startAdd() {
    show("");
    clearForm();
    getJson(root.dataset.nextUrl).then(function (res) {
      numberInput.value = res.body.number;
      var now = new Date();
      var pad = function (n) { return String(n).padStart(2, "0"); };
      f("job_date").value = pad(now.getDate()) + "/" + pad(now.getMonth() + 1) + "/" + now.getFullYear();
    });
    setMode("add");
    numberInput.focus();
  }

  root.querySelectorAll("[data-act]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var a = btn.dataset.act;
      show("");
      if (a === "add") startAdd();
      else if (a === "modify") {
        clearForm(); numberInput.value = listState.selectedNumber || ""; setMode("modify");
        if (listState.selectedNumber) load(); else numberInput.focus();
      }
      else if (a === "close") {
        clearForm(); numberInput.value = listState.selectedNumber || ""; setMode("close");
        if (listState.selectedNumber) load(); else numberInput.focus();
      }
      else if (a === "delete") {
        clearForm(); numberInput.value = listState.selectedNumber || ""; setMode("delete");
        numberInput.focus();
      }
      else if (a === "confirm") confirm();
      else if (a === "exit" || a === "cancel") { setMode(null); clearForm(); numberInput.value = ""; }
      else if (a === "refresh") refreshList();
    });
  });

  function confirm() {
    if (!mode) return;
    if (mode === "delete") {
      if (!numberInput.value.trim()) { show("Enter the job no. to delete."); return; }
      askConfirm("Are You Sure?", function () {
        post({ mode: "delete", number: numberInput.value.trim() }).then(done);
      });
      return;
    }
    askConfirm("Are You Sure?", function () {
    var payload = {
      mode: mode, number: numberInput.value.trim(), job_date: window.DateMask.toIso(f("job_date").value),
      item_code: f("item_code").value, qty: f("qty").value,
      produced: f("produced").value, finish_rejection: f("finish_rejection").value,
      close_date: window.DateMask.toIso(f("close_date").value),
    };
    post(payload).then(done);
    });
  }

  function done(res) {
    if (!res.ok) { show(res.body.message || "Could not save."); return; }
    show(res.body.message);
    setMode(null);
    clearForm();
    numberInput.value = "";
    refreshList();
  }

  setMode(null);
  if (!canEdit) root.querySelectorAll('[data-act="add"]').forEach(function (b) { b.disabled = true; });
  refreshList();
})();
