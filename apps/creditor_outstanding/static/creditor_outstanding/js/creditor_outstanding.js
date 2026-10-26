/* Creditor Outstanding — grid first; ADD / MODIFY in a compact form; DELETE with YES / NO.
 * The PARTY field searches Vendor Master (Sundry Creditors only) by code or name and
 * stores the party code. CONFIRM asks "Are you sure?" and saves through Django.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-creditor-outstanding]");
  if (!root) return;

  var initial = JSON.parse(document.getElementById("co-initial-data").textContent);
  var canEdit = initial.can_edit;
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var countNote = root.querySelector("[data-count]");
  var searchBox = root.querySelector("[data-search]");
  var divFilter = root.querySelector("[data-div-filter]");
  var toast = document.querySelector("[data-toast]");
  var money = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  var state = { bills: initial.bills, selected: null, query: "" };

  /* --- Helpers ------------------------------------------------------------------ */

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function dmy(iso) {
    if (!iso) return "";
    var p = iso.split("-");
    return p[2] + "/" + p[1] + "/" + p[0];
  }

  function cents(text) {
    var t = String(text || "").trim();
    if (!/^\d+(\.\d{1,2})?$/.test(t)) return NaN;
    var parts = t.split(".");
    return Number(parts[0]) * 100 + Number(((parts[1] || "") + "00").slice(0, 2));
  }

  function post(url, data) {
    var body = new FormData();
    Object.keys(data).forEach(function (k) { body.append(k, data[k]); });
    return fetch(url, {
      method: "POST", body: body, credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" }
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; });
    });
  }

  function selectedBill() {
    return state.bills.find(function (b) { return b.key === state.selected; }) || null;
  }

  /* --- Grid ----------------------------------------------------------------------- */

  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text;
    if (cls) td.className = cls;
    return td;
  }

  function matches(b) {
    if (!state.query) return true;
    return [b.div, b.bill_no, dmy(b.bill_date), b.party_code, b.party_name].join(" ").toLowerCase().indexOf(state.query) > -1;
  }

  function render() {
    var visible = state.bills.filter(matches);
    var total = 0, totalCd = 0;
    tbody.textContent = "";
    visible.forEach(function (b, i) {
      var tr = document.createElement("tr");
      tr.dataset.key = b.key;
      tr.tabIndex = 0;
      if (b.key === state.selected) tr.classList.add("is-selected");
      tr.append(
        cell(i + 1, "num"), cell(b.div), cell(b.bill_no, "master-table__code"), cell(dmy(b.bill_date)),
        cell(b.party_name ? b.party_name + " (" + b.party_code + ")" : b.party_code),
        cell(money.format(Number(b.net_amount)), "num"), cell(money.format(Number(b.cash_discount)), "num")
      );
      tbody.appendChild(tr);
      total += cents(b.net_amount) || 0;
      totalCd += cents(b.cash_discount) || 0;
    });
    root.querySelector("[data-total-balance]").textContent = money.format(total / 100);
    root.querySelector("[data-total-cd]").textContent = money.format(totalCd / 100);
    emptyNote.hidden = visible.length > 0;
    countNote.textContent = visible.length + " of " + state.bills.length + " entries";
    updateToolbar();
  }

  function updateToolbar() {
    var has = Boolean(selectedBill());
    root.querySelector('[data-action="modify"]').disabled = !has || !canEdit;
    root.querySelector('[data-action="delete"]').disabled = !has || !canEdit;
  }

  function select(key) {
    state.selected = key;
    tbody.querySelectorAll("tr").forEach(function (tr) { tr.classList.toggle("is-selected", tr.dataset.key === key); });
    updateToolbar();
  }

  function refresh(selectKey) {
    return fetch(root.dataset.listUrl + "?div=" + encodeURIComponent(divFilter.value), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        state.bills = data.bills;
        state.selected = selectKey !== undefined ? selectKey : state.selected;
        if (!selectedBill()) state.selected = null;
        render();
        var row = tbody.querySelector('tr[data-key="' + CSS.escape(state.selected || "") + '"]');
        if (row) row.scrollIntoView({ block: "nearest" });
      });
  }

  tbody.addEventListener("click", function (e) { var tr = e.target.closest("tr"); if (tr) select(tr.dataset.key); });
  tbody.addEventListener("dblclick", function (e) {
    var tr = e.target.closest("tr");
    if (tr) { select(tr.dataset.key); if (canEdit) openForm("modify", selectedBill()); }
  });
  tbody.addEventListener("keydown", function (e) {
    var tr = e.target.closest("tr");
    if (!tr) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      var next = e.key === "ArrowDown" ? tr.nextElementSibling : tr.previousElementSibling;
      if (next) { next.focus(); select(next.dataset.key); }
    } else if (e.key === "Enter" && canEdit) {
      select(tr.dataset.key);
      openForm("modify", selectedBill());
    }
  });
  searchBox.addEventListener("input", function () { state.query = searchBox.value.trim().toLowerCase(); render(); });
  divFilter.addEventListener("change", function () { refresh(null); });

  /* --- Form (ADD / MODIFY) ------------------------------------------------------------ */

  var dialog = document.getElementById("co-form-dialog");
  var form = dialog.querySelector("[data-co-form]");
  var alertBox = dialog.querySelector("[data-form-alert]");
  var confirmBox = dialog.querySelector("[data-confirm-box]");
  var confirmText = dialog.querySelector("[data-confirm-text]");
  var partyCode = dialog.querySelector('[data-field="party_code"]');
  var partySearch = dialog.querySelector("[data-party-search]");
  var partyList = dialog.querySelector("[data-party-list]");
  var partyName = dialog.querySelector("[data-party-name]");
  var confirmBtn = dialog.querySelector("[data-form-confirm]");
  var FIELDS = ["div", "bill_no", "bill_date", "party_code", "net_amount", "cash_discount"];
  var formState = { mode: "add", key: null, snapshot: "", afterConfirm: null, parties: {} };

  function field(name) { return form.querySelector('[data-field="' + name + '"]'); }
  function values() {
    var v = {};
    FIELDS.forEach(function (n) { v[n] = field(n).value.trim(); });
    return v;
  }

  function clearErrors() {
    alertBox.hidden = true;
    form.querySelectorAll("[data-error-for]").forEach(function (el) { el.textContent = ""; });
    form.querySelectorAll(".mform__field.is-invalid").forEach(function (el) { el.classList.remove("is-invalid"); });
  }

  function showErrors(errors) {
    var first = null;
    Object.keys(errors).forEach(function (name) {
      var msg = errors[name].map(function (e) { return e.message || e; }).join(" ");
      var target = form.querySelector('[data-error-for="' + name + '"]');
      if (target) {
        target.textContent = msg;
        target.closest(".mform__field").classList.add("is-invalid");
        first = first || field(name);
      } else {
        alertBox.textContent = msg;
        alertBox.hidden = false;
      }
    });
    if (first) first.focus();
  }

  function setPartyName(name) { partyName.textContent = name ? "Vendor: " + name : ""; }

  function loadParties(q) {
    if (!q) return Promise.resolve([]);
    return fetch(root.dataset.vendorsUrl + "?q=" + encodeURIComponent(q), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        partyList.textContent = "";
        data.parties.forEach(function (p) {
          formState.parties[p.code] = p.name;
          var o = document.createElement("option");
          o.value = p.code;
          o.label = p.name;
          o.textContent = p.name;
          partyList.appendChild(o);
        });
        return data.parties;
      });
  }

  var searchTimer;
  partySearch.addEventListener("input", function () {
    var q = partySearch.value.trim();
    // Picking from the list puts the party code into this box: move it to the code field.
    if (formState.parties[q.toUpperCase()] !== undefined) {
      partyCode.value = q.toUpperCase();
      partySearch.value = formState.parties[partyCode.value];
      setPartyName(partySearch.value);
      return;
    }
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () { loadParties(q); }, 200);
  });
  partyCode.addEventListener("change", function () {
    var code = partyCode.value.trim().toUpperCase();
    partyCode.value = code;
    loadParties(code).then(function (list) {
      var hit = list.find(function (p) { return p.code === code; });
      partySearch.value = hit ? hit.name : "";
      setPartyName(hit ? hit.name : "");
    });
  });

  // Universal Help/Lookup: focus the vendor code, press Enter, pick from a searchable grid.
  if (window.HelpLookup) {
    window.HelpLookup.attach(partyCode, {
      endpoint: root.dataset.vendorsUrl,
      resultsKey: "parties",
      valueField: "code",
      displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }],
      title: "Vendor",
      onSelect: function (row) {
        formState.parties[row.code] = row.name;
        partySearch.value = row.name;
        setPartyName(row.name);
      },
    });
  }

  var MODE_LABELS = { add: "Add", modify: "Modify", "delete": "Delete" };

  function openForm(mode, bill) {
    formState.mode = mode;
    formState.key = bill ? bill.key : null;
    clearErrors();
    confirmBox.hidden = true;
    dialog.querySelector("[data-mode-label]").textContent = MODE_LABELS[mode];
    field("div").value = bill ? bill.div : (divFilter.value || "OL");
    field("bill_no").value = bill ? bill.bill_no : "";
    field("bill_date").value = bill ? window.DateMask.toDisplay(bill.bill_date) : "";
    field("party_code").value = bill ? bill.party_code : "";
    partySearch.value = bill ? bill.party_name : "";
    setPartyName(bill ? bill.party_name : "");
    if (bill) formState.parties[bill.party_code] = bill.party_name;
    field("net_amount").value = bill ? bill.net_amount : "";
    field("cash_discount").value = bill ? bill.cash_discount : "0.00";
    var readOnlyMode = mode === "delete";
    FIELDS.forEach(function (n) { field(n).readOnly = readOnlyMode; });
    partySearch.readOnly = readOnlyMode;
    confirmBtn.textContent = mode === "delete" ? "Delete" : "Confirm";
    confirmBtn.classList.toggle("btn--danger", mode === "delete");
    confirmBtn.classList.toggle("btn--primary", mode !== "delete");
    formState.snapshot = JSON.stringify(values());
    dialog.showModal();
    (mode === "add" ? field("div") : mode === "delete" ? confirmBtn : field("net_amount")).focus();
  }

  function isDirty() { return formState.mode !== "delete" && JSON.stringify(values()) !== formState.snapshot; }

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

  function validate(v) {
    var e = {};
    if (!v.div) e.div = ["DIV is required (e.g. OL)."];
    if (!v.bill_no) e.bill_no = ["Invoice no. is required."];
    if (!v.bill_date) e.bill_date = ["Invoice date is required."];
    if (!v.party_code) e.party_code = ["Select a vendor."];
    if (!v.net_amount) e.net_amount = ["Balance amount is required."];
    else if (isNaN(cents(v.net_amount))) e.net_amount = ["Enter an amount like 5000.00 (no letters)."];
    else if (cents(v.net_amount) === 0) e.net_amount = ["Balance amount must be more than 0."];
    if (v.cash_discount && isNaN(cents(v.cash_discount))) e.cash_discount = ["Enter an amount like 50.00 (no letters)."];
    return e;
  }

  function save() {
    var data = values();
    data.key = formState.key || "";
    post(root.dataset.saveUrl, data).then(function (res) {
      if (res.ok) {
        dialog.close();
        showToast(res.body.message);
        refresh(res.body.key);
      } else if (res.body.errors) {
        showErrors(res.body.errors);
      } else {
        alertBox.textContent = res.body.message || "Could not save (error " + res.status + ").";
        alertBox.hidden = false;
      }
    }).catch(function () {
      alertBox.textContent = "Could not reach the server. Nothing was saved.";
      alertBox.hidden = false;
    });
  }

  function performDelete() {
    post(root.dataset.deleteUrl, { key: formState.key || "" }).then(function (res) {
      if (res.ok) {
        dialog.close();
        showToast(res.body.message);
        refresh(null);
      } else {
        alertBox.textContent = res.body.message || "Could not delete.";
        alertBox.hidden = false;
      }
    }).catch(function () {
      alertBox.textContent = "Could not reach the server. Nothing was deleted.";
      alertBox.hidden = false;
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    clearErrors();
    if (formState.mode === "delete") {
      ask("Are you sure you want to delete this Creditor Outstanding entry?", performDelete);
      return;
    }
    var errs = validate(values());
    if (Object.keys(errs).length) { showErrors(errs); return; }
    ask("Are you sure?", save);
  });

  // Enter moves to the next field instead of submitting.
  form.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" || e.target.tagName !== "INPUT") return;
    e.preventDefault();
    var inputs = Array.prototype.slice.call(form.querySelectorAll(".mform__input"));
    var i = inputs.indexOf(e.target);
    if (i > -1 && i < inputs.length - 1) inputs[i + 1].focus();
    else form.querySelector("[data-form-confirm]").focus();
  });

  form.addEventListener("focusout", function (e) {
    var el = e.target;
    if ((el === field("net_amount") || el === field("cash_discount")) && !isNaN(cents(el.value)) && el.value.trim()) {
      var c = cents(el.value);
      el.value = Math.floor(c / 100) + "." + String(c % 100).padStart(2, "0");
    }
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

  /* --- Toolbar ------------------------------------------------------------------------ */

  var actions = {
    add: function () { openForm("add", null); },
    modify: function () { var b = selectedBill(); if (b) openForm("modify", b); },
    "delete": function () { var b = selectedBill(); if (b) openForm("delete", b); },
    exit: function () { window.location.href = root.dataset.exitUrl; }
  };
  root.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function () { actions[btn.dataset.action](); });
  });
  document.addEventListener("keydown", function (e) {
    if (!e.altKey || document.querySelector("dialog[open]")) return;
    var map = { a: "add", m: "modify", d: "delete", e: "exit" };
    var btn = map[e.key.toLowerCase()] && root.querySelector('[data-action="' + map[e.key.toLowerCase()] + '"]');
    if (btn && !btn.disabled) { e.preventDefault(); btn.click(); }
  });

  render();
})();
