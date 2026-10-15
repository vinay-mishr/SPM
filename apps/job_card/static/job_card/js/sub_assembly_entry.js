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
      else if (a === "modify") { clearForm(); numberInput.value = ""; setMode("modify"); numberInput.focus(); }
      else if (a === "close") { clearForm(); numberInput.value = ""; setMode("close"); numberInput.focus(); }
      else if (a === "delete") {
        clearForm(); numberInput.value = ""; setMode("delete");
        numberInput.focus();
      }
      else if (a === "confirm") confirm();
      else if (a === "exit" || a === "cancel") { setMode(null); clearForm(); numberInput.value = ""; }
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
  }

  setMode(null);
  if (!canEdit) root.querySelectorAll('[data-act="add"]').forEach(function (b) { b.disabled = true; });
})();
