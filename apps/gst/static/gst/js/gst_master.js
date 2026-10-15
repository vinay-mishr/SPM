/* GST Master — list of GST % brackets; ADD / MODIFY / VIEW open a form dialog with the
 * Sale/Purchase account configuration, DELETE removes a bracket. Old VFP form: GST MASTER.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-gst-master]");
  if (!root) return;

  var initial = JSON.parse(document.getElementById("gst-initial-data").textContent);
  var canEdit = initial.can_edit;
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var toast = document.querySelector("[data-toast]");

  var ACCOUNT_FIELDS = [
    "sale_taxfree_account", "sale_account", "sale_cgst_account", "sale_sgst_account",
    "sale_interstate_account", "sale_igst_account",
    "purchase_taxfree_account", "purchase_account", "purchase_cgst_account", "purchase_sgst_account",
    "purchase_interstate_account", "purchase_igst_account",
  ];

  var state = { rates: initial.rates, selected: null };
  var ledgers = [];
  var ledgersLoaded = false;

  /* --- Helpers ------------------------------------------------------------------ */

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text;
    if (cls) td.className = cls;
    return td;
  }

  function selectedRate() {
    return state.rates.find(function (r) { return r.rate === state.selected; }) || null;
  }

  function fetchJson(url, options) {
    return fetch(url, Object.assign({ credentials: "same-origin" }, options || {})).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; });
    });
  }

  function postJson(url, data) {
    return fetchJson(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(data),
    });
  }

  function postForm(url) {
    return fetchJson(url, { method: "POST", headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" } });
  }

  /* --- List ---------------------------------------------------------------------- */

  function render() {
    tbody.textContent = "";
    state.rates.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.dataset.rate = r.rate;
      tr.tabIndex = 0;
      if (r.rate === state.selected) tr.classList.add("is-selected");
      tr.append(cell(r.rate, "num"));
      tbody.appendChild(tr);
    });
    emptyNote.hidden = state.rates.length > 0;
    updateToolbar();
  }

  function updateToolbar() {
    var has = Boolean(selectedRate());
    root.querySelector('[data-action="view"]').disabled = !has;
    root.querySelector('[data-action="modify"]').disabled = !has || !canEdit;
    root.querySelector('[data-action="delete"]').disabled = !has || !canEdit;
  }

  function select(rate) {
    state.selected = rate;
    tbody.querySelectorAll("tr").forEach(function (tr) { tr.classList.toggle("is-selected", tr.dataset.rate === rate); });
    updateToolbar();
  }

  function refresh(selectRate) {
    return fetchJson(root.dataset.listUrl).then(function (res) {
      state.rates = res.body.rates;
      state.selected = selectRate !== undefined ? selectRate : state.selected;
      if (!selectedRate()) state.selected = null;
      render();
    });
  }

  tbody.addEventListener("click", function (e) { var tr = e.target.closest("tr"); if (tr) select(tr.dataset.rate); });
  tbody.addEventListener("dblclick", function (e) {
    var tr = e.target.closest("tr");
    if (tr) { select(tr.dataset.rate); openForm(canEdit ? "modify" : "view"); }
  });
  tbody.addEventListener("keydown", function (e) {
    var tr = e.target.closest("tr");
    if (!tr) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      var next = e.key === "ArrowDown" ? tr.nextElementSibling : tr.previousElementSibling;
      if (next) { next.focus(); select(next.dataset.rate); }
    }
  });

  /* --- Form (ADD / MODIFY / VIEW) ------------------------------------------------ */

  var dialog = document.getElementById("gst-form-dialog");
  var form = dialog.querySelector("[data-gst-form]");
  var alertBox = dialog.querySelector("[data-form-alert]");
  var confirmBox = dialog.querySelector("[data-confirm-box]");
  var confirmText = dialog.querySelector("[data-confirm-text]");
  var confirmBtn = dialog.querySelector("[data-form-confirm]");
  var rateField = dialog.querySelector('[data-field="rate"]');
  var accountFieldsets = dialog.querySelectorAll("[data-account-fields]");

  var formState = { mode: "add", snapshot: "" };

  function clearErrors() {
    alertBox.hidden = true;
    form.querySelectorAll("[data-error-for]").forEach(function (el) { el.textContent = ""; });
    form.querySelectorAll(".mform__field.is-invalid").forEach(function (el) { el.classList.remove("is-invalid"); });
  }

  function showErrors(errors) {
    var generic = [];
    Object.keys(errors || {}).forEach(function (key) {
      if (key === "rate") {
        var target = form.querySelector('[data-error-for="rate"]');
        target.textContent = errors[key];
        rateField.closest(".mform__field").classList.add("is-invalid");
      } else {
        generic.push(errors[key]);
      }
    });
    if (generic.length) {
      alertBox.textContent = generic.join(" ");
      alertBox.hidden = false;
    }
  }

  function accountInputs() {
    return ACCOUNT_FIELDS.map(function (field) {
      return {
        field: field,
        search: dialog.querySelector('[data-account-search="' + field + '"]'),
        code: dialog.querySelector('[data-account-code="' + field + '"]'),
      };
    });
  }

  function fillAccountFields(data) {
    accountInputs().forEach(function (row) {
      var code = (data && data[row.field]) || "";
      row.code.value = code;
      var ledger = ledgers.find(function (l) { return l.ledger_code === code; });
      row.search.value = ledger ? ledger.description : "";
    });
  }

  function clearAccountFields() {
    accountInputs().forEach(function (row) { row.search.value = ""; row.code.value = ""; });
  }

  function loadLedgers() {
    if (ledgersLoaded) return Promise.resolve(ledgers);
    return fetchJson(root.dataset.ledgersUrl).then(function (res) {
      ledgers = (res.body.ledgers || []).map(function (l) {
        return { ledger_code: l.ledger_code || l.id, description: l.description || "" };
      });
      ledgersLoaded = true;
      return ledgers;
    });
  }

  if (window.HelpLookup) {
    accountInputs().forEach(function (row) {
      window.HelpLookup.attach(row.search, {
        data: function () { return ledgers; },
        valueField: "description",
        displayFields: [{ key: "ledger_code", label: "Code" }, { key: "description", label: "Name" }],
        title: "Ledger Account",
        onSelect: function (hit) { row.code.value = hit.ledger_code; row.search.value = hit.description; },
      });
    });
  }

  function setMode(mode) {
    formState.mode = mode;
    dialog.dataset.mode = mode;
    dialog.querySelector("[data-mode-label]").textContent = mode === "add" ? "Add" : mode === "modify" ? "Modify" : "View";
    var readOnly = mode === "view";
    rateField.readOnly = readOnly || mode === "modify";
    accountFieldsets.forEach(function (fs) { fs.disabled = readOnly; });
    confirmBtn.hidden = readOnly;
  }

  function snapshot() {
    var data = { rate: rateField.value };
    accountInputs().forEach(function (row) { data[row.field] = row.code.value; });
    return JSON.stringify(data);
  }

  function openForm(mode) {
    var row = selectedRate();
    clearErrors();
    confirmBox.hidden = true;
    setMode(mode);

    rateField.value = row ? row.rate : "";
    clearAccountFields();

    loadLedgers().then(function () {
      if (row) fillAccountFields(row);
      formState.snapshot = snapshot();
      dialog.showModal();
      (mode === "add" ? rateField : dialog.querySelector("[data-account-search]")).focus();
    });
  }

  function ask(text, onYes) {
    confirmText.textContent = text;
    formState.afterConfirm = onYes;
    confirmBox.hidden = false;
    dialog.querySelector("[data-confirm-no]").focus();
  }
  dialog.querySelector("[data-confirm-yes]").addEventListener("click", function () {
    confirmBox.hidden = true;
    if (formState.afterConfirm) formState.afterConfirm();
  });
  dialog.querySelector("[data-confirm-no]").addEventListener("click", function () { confirmBox.hidden = true; });

  function save() {
    clearErrors();
    var rate = rateField.value.trim();
    if (!rate) { showErrors({ rate: "GST % is required." }); return; }
    if (formState.mode === "add") {
      var exists = state.rates.some(function (r) { return Number(r.rate) === Number(rate); });
      if (exists) { showErrors({ rate: "GST Rate Already Defined..." }); return; }
    }

    var payload = { mode: formState.mode, rate: rate };
    accountInputs().forEach(function (row) { payload[row.field] = row.code.value.trim(); });

    confirmBtn.disabled = true;
    postJson(root.dataset.saveUrl, payload).then(function (res) {
      if (res.ok) {
        dialog.close();
        showToast(res.body.message);
        refresh(res.body.rate.rate);
      } else if (res.body.errors) {
        showErrors(res.body.errors);
      } else {
        alertBox.textContent = res.body.message || "Could not save (error " + res.status + ").";
        alertBox.hidden = false;
      }
    }).catch(function () {
      alertBox.textContent = "Could not reach the server. Nothing was saved.";
      alertBox.hidden = false;
    }).finally(function () {
      confirmBtn.disabled = false;
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (formState.mode === "view") return;
    ask("Are you sure?", save);
  });

  function requestExit() {
    dialog.close();
  }
  dialog.querySelectorAll("[data-form-exit]").forEach(function (b) { b.addEventListener("click", requestExit); });
  dialog.addEventListener("cancel", function (e) {
    e.preventDefault();
    if (!confirmBox.hidden) confirmBox.hidden = true;
    else requestExit();
  });

  /* --- Delete ------------------------------------------------------------------- */

  var delDialog = document.getElementById("gst-delete-dialog");
  function openDelete(row) {
    var dl = delDialog.querySelector("[data-delete-details]");
    dl.textContent = "";
    [["GST %", row.rate]].forEach(function (p) {
      var dt = document.createElement("dt"), dd = document.createElement("dd");
      dt.textContent = p[0]; dd.textContent = p[1];
      dl.append(dt, dd);
    });
    delDialog.querySelector("[data-delete-alert]").hidden = true;
    delDialog.querySelector("[data-delete-yes]").disabled = false;
    delDialog.showModal();
    delDialog.querySelector("[data-delete-no]").focus();
  }
  delDialog.querySelector("[data-delete-no]").addEventListener("click", function () { delDialog.close(); });
  delDialog.querySelector("[data-delete-yes]").addEventListener("click", function () {
    var row = selectedRate();
    var btn = delDialog.querySelector("[data-delete-yes]");
    var alertBox2 = delDialog.querySelector("[data-delete-alert]");
    if (!row) return;
    btn.disabled = true;
    postForm(root.dataset.deleteUrlTemplate.replace("__RATE__", encodeURIComponent(row.rate))).then(function (res) {
      if (res.ok) {
        delDialog.close();
        showToast(res.body.message);
        state.selected = null;
        refresh();
      } else {
        alertBox2.textContent = res.body.message || "Could not delete.";
        alertBox2.hidden = false;
        btn.disabled = false;
      }
    });
  });

  /* --- Toolbar ------------------------------------------------------------------ */

  var actions = {
    add: function () { openForm("add"); },
    modify: function () { if (selectedRate()) openForm("modify"); },
    view: function () { if (selectedRate()) openForm("view"); },
    "delete": function () { var r = selectedRate(); if (r) openDelete(r); },
    exit: function () { window.location.href = root.dataset.exitUrl; },
  };
  root.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function () { actions[btn.dataset.action](); });
  });
  document.addEventListener("keydown", function (e) {
    if (!e.altKey || document.querySelector("dialog[open]")) return;
    var map = { a: "add", m: "modify", v: "view", d: "delete", e: "exit" };
    var btn = map[e.key.toLowerCase()] && root.querySelector('[data-action="' + map[e.key.toLowerCase()] + '"]');
    if (btn && !btn.disabled) { e.preventDefault(); btn.click(); }
  });

  render();
})();
