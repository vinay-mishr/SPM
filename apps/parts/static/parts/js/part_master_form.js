/* Part Master — shared Add / Modify / View form.
 * Exposes window.SPPartForm.init(options) and .open(mode, part).
 * - Part No. is fixed (read-only) once a part exists (MODIFY / VIEW).
 * - The 4 SUPPLIER fields search the real Party Master by code or name.
 * - Enter moves to the next field; EXIT asks before discarding changes; Django validates again.
 */
(function () {
  "use strict";

  var TEXT_FIELDS = ["part_number", "drawing_no", "description_1", "description_2", "gauge", "grade",
    "material", "location", "unit", "hsn_code", "supplier_1", "supplier_2", "supplier_3", "supplier_4"];
  var NUM_FIELDS = ["packing", "gross_weight", "quantity_in_order", "purchase_rate", "sale_rate", "gst_percent",
    "opening_stock", "reorder_qty", "current_stock", "weight_by_100", "rate_1", "rate_2", "rate_3", "rate_4"];
  var ALL_FIELDS = TEXT_FIELDS.concat(NUM_FIELDS, ["part_type", "sub_assembly"]);
  var LABELS = { add: "Add", modify: "Modify", view: "View" };

  var dialog, form, alertBox, discard, confirmBtn, options;
  var state = { mode: "add", part: null, snapshot: "", saving: false, parties: {} };

  function input(name) { return form.querySelector('[data-field="' + name + '"]'); }

  function values() {
    var v = {};
    TEXT_FIELDS.concat(NUM_FIELDS, ["part_type"]).forEach(function (n) { v[n] = input(n).value.trim(); });
    v.sub_assembly = input("sub_assembly").checked ? "true" : "false";
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
        first = first || input(name);
      } else {
        alertBox.textContent = msg;
        alertBox.hidden = false;
      }
    });
    if (first) first.focus();
  }

  function isNum(text) {
    return text === "" || /^\d+(\.\d+)?$/.test(text);
  }

  function validate(v) {
    var e = {};
    if (!v.part_number) e.part_number = ["Part No. is required."];
    NUM_FIELDS.forEach(function (name) {
      if (!isNum(v[name])) e[name] = ["Enter a number (no letters or minus sign)."];
    });
    if (v.gst_percent && isNum(v.gst_percent) && Number(v.gst_percent) > 100) e.gst_percent = ["GST % cannot be more than 100."];
    ["supplier_1", "supplier_2", "supplier_3", "supplier_4"].forEach(function (name) {
      var code = v[name].toUpperCase();
      if (code && !state.parties[code]) e[name] = ["Select a party from the Party Master."];
    });
    return e;
  }

  function close() { discard.hidden = true; dialog.close(); }

  function requestExit() {
    close();
  }

  function save() {
    if (state.saving || state.mode === "view") return;
    clearErrors();
    var v = values();
    var errs = validate(v);
    if (Object.keys(errs).length) { showErrors(errs); return; }

    var body = new FormData();
    ALL_FIELDS.forEach(function (n) { body.append(n, v[n]); });

    var url = state.mode === "modify"
      ? options.updateUrl.replace("/0/", "/" + encodeURIComponent(state.part.id) + "/")
      : options.createUrl;

    state.saving = true;
    confirmBtn.disabled = true;
    fetch(url, {
      method: "POST", body: body, credentials: "same-origin",
      headers: { "X-CSRFToken": options.csrfToken, "X-Requested-With": "XMLHttpRequest" }
    })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; });
      })
      .then(function (res) {
        if (res.ok) {
          close();
          options.onSaved(res.body.part, res.body.message);
        } else if (res.body.errors) {
          showErrors(res.body.errors);
        } else {
          alertBox.textContent = res.body.message || "Could not save (error " + res.status + ").";
          alertBox.hidden = false;
        }
      })
      .catch(function () {
        alertBox.textContent = "Could not reach the server. Nothing was saved.";
        alertBox.hidden = false;
      })
      .finally(function () { state.saving = false; confirmBtn.disabled = false; });
  }

  /* --- Supplier party search (4 fields share one datalist) ------------------------- */

  var partyList, searchTimer;

  function fillPartyList(parties) {
    partyList.textContent = "";
    parties.forEach(function (p) {
      state.parties[p.code] = p.name;
      var option = document.createElement("option");
      option.value = p.code;
      option.label = p.name;
      option.textContent = p.name;
      partyList.appendChild(option);
    });
  }

  function loadParties(term) {
    if (!term) return;
    fetch(options.partiesUrl + "?q=" + encodeURIComponent(term), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) { fillPartyList(data.parties); })
      .catch(function () {});
  }

  function wireSupplierSearch(n) {
    var code = input("supplier_" + n);
    var search = form.querySelector('[data-party-search="' + n + '"]');
    // Search-by-name is only for *finding* a supplier -- once Code has a value it's a
    // read-back and gets skipped by Enter-to-advance (readonly fields are excluded from
    // that list below), so focus goes straight from Code to Rate.
    function syncReadonly() { search.readOnly = Boolean(code.value.trim()); }

    // Universal Help/Lookup: focus the code field, press Enter, pick a supplier from a
    // searchable grid (arrow keys + Enter), same as the old VFP Help key.
    if (window.HelpLookup) {
      window.HelpLookup.attach(code, {
        endpoint: options.partiesUrl,
        resultsKey: "parties",
        valueField: "code",
        displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }],
        title: "Supplier " + n,
        onSelect: function (row) {
          state.parties[row.code] = row.name;
          search.value = row.name;
          syncReadonly();
        },
      });
    }

    search.addEventListener("input", function () {
      var term = search.value.trim();
      if (state.parties[term.toUpperCase()] !== undefined) {
        code.value = term.toUpperCase();
        search.value = state.parties[code.value];
        syncReadonly();
        return;
      }
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () { loadParties(term); }, 200);
    });
    code.addEventListener("input", syncReadonly);
    code.addEventListener("change", function () {
      var value = code.value.trim().toUpperCase();
      code.value = value;
      syncReadonly();
      if (!value) { search.value = ""; return; }
      fetch(options.partiesUrl + "?q=" + encodeURIComponent(value), { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          fillPartyList(data.parties);
          var hit = data.parties.find(function (p) { return p.code === value; });
          search.value = hit ? hit.name : "";
        });
    });
  }

  /* --- Fill / mode ------------------------------------------------------------------ */

  // A blank/zero numeric field defaults to "0" formatted to that field's own precision
  // (data-decimal, same attribute the focusout handler below formats typed values with) --
  // e.g. "0.000" for Qty in Order / Weight/100, "0.00" for Sale Rate / GST%, plain "0"
  // for fields with no configured precision (Packing, Current Stock).
  function defaultNumValue(name) {
    var decimals = input(name).dataset.decimal;
    return decimals !== undefined ? Number(0).toFixed(Number(decimals)) : "0";
  }

  function fill(part) {
    input("part_number").value = part ? part.part_number : "";
    TEXT_FIELDS.slice(1).forEach(function (n) { input(n).value = part ? part[n] || "" : ""; });
    NUM_FIELDS.forEach(function (n) { input(n).value = (part && part[n]) || defaultNumValue(n); });
    input("part_type").value = part ? part.part_type || "" : "";
    input("sub_assembly").checked = Boolean(part && part.sub_assembly);
    ["1", "2", "3", "4"].forEach(function (n) {
      var code = part ? part["supplier_" + n] || "" : "";
      var search = form.querySelector('[data-party-search="' + n + '"]');
      if (code) { state.parties[code] = state.parties[code] || code; search.value = state.parties[code]; }
      else search.value = "";
    });
  }

  function setMode(mode) {
    state.mode = mode;
    dialog.dataset.mode = mode;
    dialog.querySelector("[data-mode-label]").textContent = LABELS[mode];
    var readOnly = mode === "view";
    TEXT_FIELDS.concat(NUM_FIELDS).forEach(function (n) { input(n).readOnly = readOnly; });
    input("part_number").readOnly = readOnly || mode === "modify"; // protected once created
    input("part_type").disabled = readOnly;
    input("sub_assembly").disabled = readOnly;
    ["1", "2", "3", "4"].forEach(function (n) {
      // Editable-mode search boxes stay readonly once their Code is already filled in
      // (see fill()/wireSupplierSearch's syncReadonly) -- View mode always wins.
      form.querySelector('[data-party-search="' + n + '"]').readOnly =
        readOnly || Boolean(input("supplier_" + n).value.trim());
    });
  }

  function open(mode, part) {
    state.part = part || null;
    clearErrors();
    fill(part);
    setMode(mode);
    discard.hidden = true;
    state.snapshot = JSON.stringify(values());
    dialog.showModal();
    (mode === "view" ? dialog.querySelector(".modal__footer [data-form-exit]")
      : mode === "add" ? input("part_number") : input("description_1")).focus();
  }

  function init(opts) {
    options = opts;
    dialog = document.getElementById("part-form-dialog");
    form = dialog.querySelector("[data-part-form]");
    alertBox = dialog.querySelector("[data-form-alert]");
    discard = dialog.querySelector("[data-discard]");
    confirmBtn = dialog.querySelector("[data-form-confirm]");
    partyList = dialog.querySelector("[data-party-list]");

    ["1", "2", "3", "4"].forEach(wireSupplierSearch);
    if (window.HelpLookup) {
      window.HelpLookup.attachDatalist(input("unit"), { title: "Unit" });
      window.HelpLookup.attachSelect(input("part_type"), { title: "Part Type" });
    }

    form.addEventListener("submit", function (e) { e.preventDefault(); save(); });
    form.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" || (e.target.tagName !== "INPUT" && e.target.tagName !== "SELECT")) return;
      e.preventDefault();
      if (e.target.type === "checkbox") { input("supplier_1").focus(); return; }
      var list = form.querySelectorAll("input:not([readonly]):not([type=checkbox]), select:not([disabled])");
      var i = Array.prototype.indexOf.call(list, e.target);
      if (i > -1 && i < list.length - 1) {
        // HelpLookup.attachSelect() hides the real <select> (Part Type) and puts a
        // focusable proxy <input> right after it -- focus that, not the hidden select.
        var next = list[i + 1];
        if (next.dataset.helpSelectProxied === "1") next = next.nextElementSibling || next;
        next.focus();
      } else if (state.mode !== "view") confirmBtn.focus();
    });
    form.addEventListener("focusout", function (e) {
      var el = e.target;
      if (el.dataset && el.dataset.decimal && el.value.trim() !== "" && isNum(el.value)) {
        el.value = Number(el.value).toFixed(Number(el.dataset.decimal));
      }
    });
    form.addEventListener("input", function (e) {
      var name = e.target.dataset.field;
      var holder = e.target.closest(".mform__field");
      if (name && holder && holder.classList.contains("is-invalid")) {
        holder.classList.remove("is-invalid");
        var err = form.querySelector('[data-error-for="' + name + '"]');
        if (err) err.textContent = "";
      }
    });

    dialog.querySelectorAll("[data-form-exit]").forEach(function (b) { b.addEventListener("click", requestExit); });
    dialog.addEventListener("cancel", function (e) {
      e.preventDefault();
      if (!discard.hidden) discard.hidden = true; else requestExit();
    });
    dialog.querySelector("[data-discard-cancel]").addEventListener("click", function () { discard.hidden = true; });
    dialog.querySelector("[data-discard-confirm]").addEventListener("click", close);
  }

  window.SPPartForm = { init: init, open: open };
})();
