/* Vendor Master — shared Add / Modify / View form.
 * Exposes window.SPVendorForm.init(options), .open(mode, vendor) and .setSuggestions(map).
 * - Picking a STATE sets W/I (Within if it's the company's state).
 * - Enter moves to the next field (never submits by accident); Enter on Confirm saves.
 * - CLEAR empties the form and keeps it open; EXIT asks before discarding changes.
 * - Quick checks here; Django validates everything again on save.
 */
(function () {
  "use strict";

  var FIELDS = [
    "name", "mobile_1", "opening_balance", "address_1", "address_2", "address_3", "city", "pin",
    "gst_no", "gst_category", "state_code", "transport",
    "contact_person_1", "mobile_person_1", "contact_person_2", "mobile_person_2", "email",
    "credit_days", "association", "grade", "supply_type", "is_active"
  ];
  var DEFAULTS = {
    gst_category: "REGULAR", credit_days: "0", opening_balance: "0",
    is_active: "true", supply_type: ""
  };
  var MODE_LABELS = { add: "Add", modify: "Modify", view: "View" };
  var GSTIN_RE = /^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;
  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  var dialog, form, alertBox, discard, confirmBtn, stateCodeBox, options;
  var state = { mode: "add", vendor: null, snapshot: "", saving: false };

  function input(name) {
    return form.querySelector('[data-field="' + name + '"]');
  }

  function values() {
    var data = {};
    FIELDS.forEach(function (name) { data[name] = input(name).value.trim(); });
    return data;
  }

  /* --- Errors ------------------------------------------------------------------ */

  function clearErrors() {
    alertBox.hidden = true;
    alertBox.textContent = "";
    form.querySelectorAll("[data-error-for]").forEach(function (el) { el.textContent = ""; });
    form.querySelectorAll(".mform__field.is-invalid").forEach(function (el) { el.classList.remove("is-invalid"); });
    form.querySelectorAll("[aria-invalid]").forEach(function (el) { el.removeAttribute("aria-invalid"); });
  }

  function showFieldError(name, message) {
    var target = form.querySelector('[data-error-for="' + name + '"]');
    var field = input(name);
    if (!target || !field) return false;
    target.textContent = message;
    target.id = target.id || "verr-" + name;
    field.closest(".mform__field").classList.add("is-invalid");
    field.setAttribute("aria-invalid", "true");
    field.setAttribute("aria-describedby", target.id);
    return true;
  }

  function showErrors(errors) {
    var first = null;
    var names = Object.keys(errors).sort(function (a, b) { return FIELDS.indexOf(a) - FIELDS.indexOf(b); });
    names.forEach(function (name) {
      var message = errors[name].map(function (e) { return e.message || e; }).join(" ");
      if (showFieldError(name, message)) {
        first = first || input(name);
      } else {
        alertBox.textContent = message;
        alertBox.hidden = false;
      }
    });
    if (first) focusable(first).focus();
  }

  function mobileDigits(value) {
    var digits = value.replace(/[\s\-()]/g, "");
    if (digits.indexOf("+91") === 0) digits = digits.slice(3);
    else if (digits.indexOf("91") === 0 && digits.length === 12) digits = digits.slice(2);
    else if (digits.indexOf("0") === 0 && digits.length === 11) digits = digits.slice(1);
    return digits;
  }

  /* True when the user typed something different from the stored value (always true for ADD). */
  function changed(name, value) {
    return !state.vendor || String(state.vendor[name] == null ? "" : state.vendor[name]) !== value;
  }

  function validate() {
    var v = values();
    var errors = {};
    if (!v.name) errors.name = ["Vendor name is required."];
    if (v.pin && changed("pin", v.pin) && !/^\d{6}$/.test(v.pin)) errors.pin = ["PIN must be exactly 6 digits."];
    ["mobile_1", "mobile_person_1", "mobile_person_2"].forEach(function (name) {
      if (v[name] && changed(name, v[name]) && !/^\d{10}$/.test(mobileDigits(v[name]))) {
        errors[name] = ["Mobile number must be 10 digits."];
      }
    });
    if (v.email && changed("email", v.email) && !EMAIL_RE.test(v.email)) {
      errors.email = ["Enter a valid email address (e.g. name@company.com)."];
    }
    var gst = v.gst_no.replace(/\s/g, "").toUpperCase();
    var stateGst = selectedStateGst();
    if (gst && (changed("gst_no", gst) || changed("state_code", v.state_code))) {
      if (gst.length !== 15) errors.gst_no = ["GST no. must be exactly 15 characters."];
      else if (!GSTIN_RE.test(gst)) errors.gst_no = ["GST no. format is invalid (e.g. 03ABCDE1234F1Z5)."];
      else if (stateGst && gst.slice(0, 2) !== stateGst) {
        errors.gst_no = ["GST no. starts with " + gst.slice(0, 2) + ", but the selected state's code is " + stateGst + "."];
      }
    }
    if (v.credit_days !== "" && !/^\d+$/.test(v.credit_days)) errors.credit_days = ["Credit days must be a whole number (0 or more)."];
    if (v.opening_balance !== "" && Number.isNaN(Number(v.opening_balance))) errors.opening_balance = ["Opening balance must be a number."];
    return errors;
  }

  /* --- State → W/I ------------------------------------------------------------- */

  function selectedStateGst() {
    var option = input("state_code").selectedOptions[0];
    return option ? option.dataset.gst || "" : "";
  }

  function syncState(updateSupplyType) {
    var gst = selectedStateGst();
    stateCodeBox.value = gst;
    if (updateSupplyType && gst) {
      input("supply_type").value = gst === options.companyStateCode ? "W" : "I";
    }
  }

  /* When a valid GSTIN is typed and no state is chosen yet, pick the state from it. */
  function stateFromGst() {
    var gst = input("gst_no").value.replace(/\s/g, "").toUpperCase();
    input("gst_no").value = gst;
    var select = input("state_code");
    var option = gst.length >= 2 && select.querySelector('option[data-gst="' + gst.slice(0, 2) + '"]');
    if (!select.value && option) {
      select.value = option.value;
      syncState(true);
    }
  }

  /* --- Fill / mode ---------------------------------------------------------------- */

  function previewCode() {
    if (state.mode !== "add" || !options.nextCodeUrl) return;
    var name = input("name").value.trim();
    if (!name) { input("party_code").value = ""; return; }
    fetch(options.nextCodeUrl + "?name=" + encodeURIComponent(name), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) { if (state.mode === "add") input("party_code").value = data.code || ""; })
      .catch(function () {});
  }

  function fill(vendor) {
    input("party_code").value = vendor ? vendor.party_code : "";
    FIELDS.forEach(function (name) {
      var value;
      if (vendor) {
        value = vendor[name];
        if (typeof value === "boolean") value = value ? "true" : "false";
      } else {
        value = DEFAULTS[name] || "";
      }
      value = value == null ? "" : String(value);
      var el = input(name);
      if (el.tagName === "SELECT" && value && !el.querySelector('option[value="' + CSS.escape(value) + '"]')) {
        var option = document.createElement("option");
        option.value = value;
        option.textContent = value + " (not in list)";
        el.appendChild(option);
      }
      el.value = value;
    });
    syncState(false);
  }

  function setMode(mode) {
    state.mode = mode;
    dialog.dataset.mode = mode;
    dialog.querySelector("[data-mode-label]").textContent = MODE_LABELS[mode];
    FIELDS.forEach(function (name) {
      var el = input(name);
      if (el.tagName === "SELECT") el.disabled = mode === "view";
      else el.readOnly = mode === "view";
    });
  }

  function isDirty() {
    return state.mode !== "view" && JSON.stringify(values()) !== state.snapshot;
  }

  function close() {
    discard.hidden = true;
    dialog.close();
  }

  function requestExit() {
    close();
  }

  /* --- Save ------------------------------------------------------------------------ */

  function save() {
    if (state.saving || state.mode === "view") return;
    clearErrors();

    var clientErrors = validate();
    if (Object.keys(clientErrors).length) {
      showErrors(clientErrors);
      return;
    }

    var data = new FormData();
    var current = values();
    FIELDS.forEach(function (name) {
      var value = current[name];
      if (name === "credit_days" && value === "") value = "0";
      if (name === "opening_balance" && value === "") value = "0";
      if (name === "gst_no") value = value.replace(/\s/g, "").toUpperCase();
      data.append(name, value);
    });

    var url = state.mode === "modify"
      ? options.updateUrl.replace("/0/", "/" + encodeURIComponent(state.vendor.id) + "/")
      : options.createUrl;

    state.saving = true;
    confirmBtn.disabled = true;

    fetch(url, {
      method: "POST",
      body: data,
      headers: { "X-CSRFToken": options.csrfToken, "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin"
    })
      .then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (body) {
          return { ok: response.ok, status: response.status, body: body };
        });
      })
      .then(function (result) {
        if (result.ok) {
          close();
          options.onSaved(result.body.vendor, result.body.message);
        } else if (result.body.errors) {
          showErrors(result.body.errors);
        } else if (result.body.message) {
          alertBox.textContent = result.body.message;
          alertBox.hidden = false;
        } else {
          alertBox.textContent = "Could not save the vendor (error " + result.status + "). Please try again.";
          alertBox.hidden = false;
        }
      })
      .catch(function () {
        alertBox.textContent = "Could not reach the server. Check your connection and try again.";
        alertBox.hidden = false;
      })
      .finally(function () {
        state.saving = false;
        confirmBtn.disabled = false;
      });
  }

  /* Enter moves to the next field; on the last field it moves to Confirm. */
  /* HelpLookup.attachSelect() hides the real <select> (data-field stays on it so
   * values()/fill() keep working) and puts a focusable proxy <input> right after it --
   * that proxy, not the hidden select, is what focus has to land on. */
  function focusable(el) {
    return el.dataset.helpSelectProxied === "1" ? (el.nextElementSibling || el) : el;
  }

  function handleEnter(event) {
    var tag = event.target.tagName;
    if (event.key !== "Enter" || (tag !== "INPUT" && tag !== "SELECT")) return;
    event.preventDefault();
    var order = FIELDS.map(input).filter(function (el) { return !el.readOnly && !el.disabled; });
    var index = order.indexOf(event.target);
    if (index > -1 && index < order.length - 1) {
      var next = focusable(order[index + 1]);
      next.focus();
      if (next.select) next.select();
    } else if (state.mode !== "view") {
      confirmBtn.focus();
    }
  }

  function setSuggestions(map) {
    Object.keys(map || {}).forEach(function (field) {
      var list = dialog.querySelector('[data-suggestions="' + field + '"]');
      if (!list) return;
      list.textContent = "";
      map[field].forEach(function (value) {
        var option = document.createElement("option");
        option.value = value;
        list.appendChild(option);
      });
    });
  }

  function init(opts) {
    options = opts;
    dialog = document.getElementById("vendor-form-dialog");
    form = dialog.querySelector("[data-vendor-form]");
    alertBox = dialog.querySelector("[data-form-alert]");
    discard = dialog.querySelector("[data-discard]");
    confirmBtn = dialog.querySelector("[data-form-confirm]");
    stateCodeBox = dialog.querySelector("[data-state-code-display]");

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      save();
    });
    form.addEventListener("keydown", handleEnter);

    // Universal Help/Lookup: focus any of these, press Enter, pick from a searchable
    // grid (arrow keys + Enter) instead of the native <select> list / plain datalist.
    if (window.HelpLookup) {
      [
        ["gst_category", "GST Category"], ["state_code", "GST State"],
        ["supply_type", "Within / Interstate"], ["is_active", "Active"],
      ].forEach(function (pair) {
        window.HelpLookup.attachSelect(input(pair[0]), { title: pair[1] });
      });
      window.HelpLookup.attachDatalist(input("transport"), { title: "Transport" });
      window.HelpLookup.attachDatalist(input("association"), { title: "Association" });
    }
    input("state_code").addEventListener("change", function () { syncState(true); });
    input("gst_no").addEventListener("change", stateFromGst);
    input("name").addEventListener("change", previewCode);
    form.addEventListener("input", function (event) {
      var name = event.target.dataset.field;
      var holder = event.target.closest(".mform__field");
      if (name && holder && holder.classList.contains("is-invalid")) {
        holder.classList.remove("is-invalid");
        event.target.removeAttribute("aria-invalid");
        var err = form.querySelector('[data-error-for="' + name + '"]');
        if (err) err.textContent = "";
      }
    });

    dialog.querySelectorAll("[data-form-exit]").forEach(function (btn) {
      btn.addEventListener("click", requestExit);
    });
    dialog.addEventListener("cancel", function (event) {
      event.preventDefault();
      if (!discard.hidden) discard.hidden = true;
      else requestExit();
    });
    dialog.querySelector("[data-discard-cancel]").addEventListener("click", function () {
      discard.hidden = true;
    });
    dialog.querySelector("[data-discard-confirm]").addEventListener("click", close);
  }

  function open(mode, vendor) {
    state.vendor = vendor || null;
    clearErrors();
    fill(vendor);
    setMode(mode);
    discard.hidden = true;
    state.snapshot = JSON.stringify(values());
    dialog.showModal();
    var first = mode === "view" ? dialog.querySelector(".modal__footer [data-form-exit]") : input("name");
    first.focus();
  }

  window.SPVendorForm = { init: init, open: open, setSuggestions: setSuggestions };
})();
