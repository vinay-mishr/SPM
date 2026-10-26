/* Money Receipt > Cheque Master: register of post-dated customer cheques. */
(function () {
  "use strict";

  var root = document.querySelector("[data-cm]");
  if (!root) return;

  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var rows = root.querySelector("[data-rows]");
  var alertBox = root.querySelector("[data-alert]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var dialog = document.querySelector("[data-form]");
  var form = dialog.querySelector("[data-cm-form]");
  var formAlert = dialog.querySelector("[data-form-alert]");
  var modeLabel = dialog.querySelector("[data-mode-label]");
  var confirmBtn = dialog.querySelector("[data-confirm]");
  var confirmDialog = document.querySelector("[data-confirm-dialog]");
  var selectedRow = null;
  var mode = "add";
  var alertTimer = null;

  function fields(name) { return form.querySelector('[data-field="' + name + '"]'); }

  function show(box, msg) {
    box.textContent = msg || "";
    box.hidden = !msg;
    clearTimeout(alertTimer);
    if (msg) alertTimer = setTimeout(function () { box.hidden = true; }, 5000);
  }

  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (cls) td.className = cls;
    return td;
  }

  function dmy(iso) {
    var p = String(iso || "").split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : "";
  }
  function ymd(dmyStr) {
    var p = String(dmyStr || "").split(/[-/]/);
    return p.length === 3 ? p[2] + "-" + p[1] + "-" + p[0] : "";
  }

  function setActionsEnabled(on) {
    root.querySelector('[data-action="modify"]').disabled = !on;
    root.querySelector('[data-action="delete"]').disabled = !on;
    root.querySelector('[data-action="view"]').disabled = !on;
  }

  function renderList(list) {
    rows.textContent = "";
    selectedRow = null;
    setActionsEnabled(false);
    if (!list.length) {
      var tr = document.createElement("tr");
      tr.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 5;
      td.textContent = "No cheques in this date range.";
      tr.appendChild(td);
      rows.appendChild(tr);
      return;
    }
    list.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.append(cell(r.chq_no), cell(dmy(r.chq_dt)), cell(r.party_name), cell(r.amount, "num"), cell(r.bank));
      tr.addEventListener("click", function () {
        rows.querySelectorAll("tr").forEach(function (t) { t.classList.remove("is-sel"); });
        tr.classList.add("is-sel");
        selectedRow = r;
        setActionsEnabled(true);
      });
      rows.appendChild(tr);
    });
  }

  function loadList() {
    var params = new URLSearchParams();
    params.set("start_date", window.DateMask.toIso(startDate.value));
    params.set("end_date", window.DateMask.toIso(endDate.value));
    fetch(root.dataset.listUrl + "?" + params.toString(), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        renderList(d.rows || []);
        root.querySelector("[data-g-total]").value = d.total;
      });
  }

  function setFieldsEnabled(on) {
    form.querySelectorAll("input, select").forEach(function (el) { el.disabled = false; el.readOnly = !on; });
    confirmBtn.hidden = !on;
  }

  function resetForm() {
    form.reset();
    fields("chq_dt").value = window.DateMask.toDisplay(new Date().toISOString().slice(0, 10));
    fields("amount").value = "0.00";
    fields("party_code").value = "";
    dialog.querySelector("[data-party-search]").value = "";
    show(formAlert, "");
  }

  function openDialog(m, entry) {
    mode = m;
    modeLabel.textContent = m.toUpperCase();
    resetForm();
    if (m === "add") {
      setFieldsEnabled(true);
    } else if (entry) {
      fields("chq_no").value = entry.chq_no;
      fields("chq_dt").value = dmy(entry.chq_dt);
      fields("party_code").value = entry.party_code;
      dialog.querySelector("[data-party-search]").value = entry.party_name;
      fields("bank").value = entry.bank;
      fields("amount").value = entry.amount;
      setFieldsEnabled(m === "modify");
      fields("chq_no").readOnly = true;
    }
    confirmBtn.textContent = mode === "delete" ? "DELETE" : "CONFIRM";
    confirmBtn.hidden = mode === "view";
    dialog.showModal();
  }

  window.HelpLookup.attach(dialog.querySelector("[data-party-search]"), {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Party",
    onSelect: function (p) { fields("party_code").value = p.code; dialog.querySelector("[data-party-search]").value = p.name; },
  });

  root.querySelector('[data-action="add"]').addEventListener("click", function () { openDialog("add"); });
  root.querySelector('[data-action="refresh"]').addEventListener("click", loadList);
  root.querySelector('[data-action="exit"]').addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  function loadDetailThen(m) {
    if (!selectedRow) return;
    fetch(root.dataset.detailUrl + "?chq_no=" + encodeURIComponent(selectedRow.chq_no), { credentials: "same-origin" })
      .then(function (r) { return r.json(); }).then(function (d) { openDialog(m, d); });
  }
  root.querySelector('[data-action="modify"]').addEventListener("click", function () { loadDetailThen("modify"); });
  root.querySelector('[data-action="view"]').addEventListener("click", function () { loadDetailThen("view"); });
  root.querySelector('[data-action="delete"]').addEventListener("click", function () { loadDetailThen("delete"); });

  dialog.querySelector("[data-form-exit]").addEventListener("click", function () { dialog.close(); });

  function askConfirmDialog(message, onYes) {
    confirmDialog.querySelector("[data-confirm-message]").textContent = message;
    confirmDialog.showModal();
    function yes() { cleanup(); onYes(); }
    function no() { cleanup(); }
    function cleanup() {
      confirmDialog.close();
      confirmDialog.querySelector("[data-confirm-yes]").removeEventListener("click", yes);
      confirmDialog.querySelector("[data-confirm-no]").removeEventListener("click", no);
    }
    confirmDialog.querySelector("[data-confirm-yes]").addEventListener("click", yes);
    confirmDialog.querySelector("[data-confirm-no]").addEventListener("click", no);
  }

  function post(url, data) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrf, "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(data || {}),
    }).then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); });
  }

  confirmBtn.addEventListener("click", function () {
    askConfirmDialog("Are You Sure?", function () {
      if (mode === "delete") {
        post(root.dataset.deleteUrl, { chq_no: fields("chq_no").value }).then(function (res) {
          if (!res.ok) { show(formAlert, res.body.message || "Could not delete."); return; }
          dialog.close();
          show(alertBox, res.body.message);
          loadList();
        });
        return;
      }
      var payload = {
        mode: mode, chq_no: fields("chq_no").value, chq_dt: ymd(fields("chq_dt").value),
        party_code: fields("party_code").value, bank: fields("bank").value, amount: fields("amount").value,
      };
      post(root.dataset.saveUrl, payload).then(function (res) {
        if (!res.ok) { show(formAlert, res.body.message || "Could not save."); return; }
        dialog.close();
        show(alertBox, res.body.message);
        loadList();
      });
    });
  });

  var today = new Date().toISOString().slice(0, 10);
  startDate.value = window.DateMask.toDisplay(today);
  endDate.value = window.DateMask.toDisplay(today);
  loadList();
})();
