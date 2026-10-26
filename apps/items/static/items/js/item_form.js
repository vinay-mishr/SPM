/* Item Master — shared Add / Modify / View form.
 * Exposes window.SPItemForm.init(options) and window.SPItemForm.open(mode, item, nextCode).
 * - Enter moves to the next field (never submits by accident); Enter on Confirm saves.
 * - Exit asks "Discard unsaved changes?" when something was typed.
 * - Field errors from Django are shown next to each field.
 */
(function () {
  "use strict";

  var FIELDS = [
    "item_name_1", "item_name_2", "item_name_3",
    "unit", "hsn_code", "gst_percent", "rate", "opening_balance"
  ];
  var NUMERIC = { gst_percent: "GST %", rate: "Rate", opening_balance: "Opening balance" };
  var UPPERCASE_FIELDS = { item_name_1: true, item_name_2: true, item_name_3: true, unit: true, hsn_code: true };
  var MODE_LABELS = { add: "Add", modify: "Modify", view: "View", "delete": "Delete" };

  var dialog, form, alertBox, discard, discardTitle, discardCancelBtn, discardConfirmBtn, confirmBtn, options;
  var state = { mode: "add", item: null, snapshot: "", saving: false };

  function input(name) {
    return form.querySelector('[data-field="' + name + '"]');
  }

  function values() {
    var data = {};
    FIELDS.forEach(function (name) { data[name] = input(name).value.trim(); });
    return data;
  }

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
    field.closest(".mform__field").classList.add("is-invalid");
    field.setAttribute("aria-invalid", "true");
    field.setAttribute("aria-describedby", target.id || (target.id = "err-" + name));
    return true;
  }

  function showErrors(errors) {
    var first = null;
    Object.keys(errors).forEach(function (name) {
      var message = errors[name].map(function (e) { return e.message || e; }).join(" ");
      if (showFieldError(name, message)) {
        first = first || input(name);
      } else {
        alertBox.textContent = message;
        alertBox.hidden = false;
      }
    });
    if (first) first.focus();
  }

  /* Quick client-side checks; Django validates again on save. */
  function validate() {
    var errors = {};
    Object.keys(NUMERIC).forEach(function (name) {
      var el = input(name);
      var raw = el.value.trim();
      if (raw === "" && el.validity.badInput) {
        errors[name] = [NUMERIC[name] + " must be a number."];
      } else if (raw !== "" && isNaN(Number(raw))) {
        errors[name] = [NUMERIC[name] + " must be a number."];
      } else if (Number(raw) < 0 && name !== "opening_balance") {
        errors[name] = [NUMERIC[name] + " cannot be negative."];
      } else if (name === "gst_percent" && Number(raw) > 100) {
        errors[name] = ["GST % cannot be more than 100."];
      }
    });
    return errors;
  }

  function fill(item, nextCode) {
    input("item_code").value = item ? item.item_code : nextCode || "";
    FIELDS.forEach(function (name) {
      var value = item ? item[name] : "";
      if (!item && NUMERIC[name]) value = "0.00";
      input(name).value = value == null ? "" : value;
    });
  }

  function setMode(mode) {
    state.mode = mode;
    dialog.dataset.mode = mode;
    dialog.querySelector("[data-mode-label]").textContent = MODE_LABELS[mode];
    var readOnlyMode = mode === "view" || mode === "delete";
    FIELDS.forEach(function (name) { input(name).readOnly = readOnlyMode; });
    confirmBtn.textContent = mode === "delete" ? "Delete" : "Confirm";
    confirmBtn.classList.toggle("btn--danger", mode === "delete");
    confirmBtn.classList.toggle("btn--primary", mode !== "delete");
  }

  function isDirty() {
    return state.mode !== "view" && state.mode !== "delete" && JSON.stringify(values()) !== state.snapshot;
  }

  function close() {
    discard.hidden = true;
    dialog.close();
  }

  function requestExit() {
    close();
  }

  function performDelete() {
    if (state.saving || !state.item) return;
    state.saving = true;
    confirmBtn.disabled = true;
    fetch(options.deleteUrl.replace("/0/", "/" + encodeURIComponent(state.item.id) + "/"), {
      method: "POST",
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
          options.onDeleted(result.body.message);
        } else {
          alertBox.textContent = result.body.message || "Could not delete.";
          alertBox.hidden = false;
        }
      })
      .catch(function () {
        alertBox.textContent = "Could not reach the server. Nothing was deleted.";
        alertBox.hidden = false;
      })
      .finally(function () {
        state.saving = false;
        confirmBtn.disabled = false;
      });
  }

  // The discard box is reused as a generic "are you sure?" prompt -- its own
  // title text, button labels and confirm action are swapped per use (discard
  // unsaved changes on EXIT vs delete the selected record), so there's one
  // small confirm dialog in this form, not two.
  function askDiscard(title, onConfirm, labels) {
    discardTitle.textContent = title;
    discardCancelBtn.textContent = labels ? labels.cancel : "Cancel";
    discardConfirmBtn.textContent = labels ? labels.confirm : "Exit";
    state.onDiscardConfirm = onConfirm;
    discard.hidden = false;
  }

  function save() {
    if (state.saving) return;
    if (state.mode === "delete") {
      askDiscard("Are you sure you want to delete this item?", performDelete, { cancel: "No", confirm: "Yes" });
      return;
    }
    if (state.mode === "view") return;
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
      if (NUMERIC[name] && value === "") value = "0";
      data.append(name, value);
    });

    var url = state.mode === "modify"
      ? options.updateUrl.replace("/0/", "/" + encodeURIComponent(state.item.id) + "/")
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
          options.onSaved(result.body.item, result.body.message);
        } else if (result.body.errors) {
          showErrors(result.body.errors);
        } else if (result.body.message) {
          alertBox.textContent = result.body.message;
          alertBox.hidden = false;
        } else {
          alertBox.textContent = "Could not save the item (error " + result.status + "). Please try again.";
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
  function handleEnter(event) {
    if (event.key !== "Enter" || event.target.tagName !== "INPUT") return;
    event.preventDefault();
    var order = FIELDS.map(input).filter(function (el) { return !el.readOnly; });
    var index = order.indexOf(event.target);
    if (index > -1 && index < order.length - 1) {
      order[index + 1].focus();
      order[index + 1].select();
    } else if (state.mode !== "view") {
      confirmBtn.focus();
    }
  }

  function formatDecimals(event) {
    var el = event.target;
    if (!el.dataset.decimal) return;
    if (el.value.trim() === "") {
      el.value = Number(0).toFixed(Number(el.dataset.decimal));
      return;
    }
    if (isNaN(Number(el.value))) return;
    el.value = Number(el.value).toFixed(Number(el.dataset.decimal));
  }

  /* Clear a "0.00" placeholder value when the field is focused, so typing
   * doesn't have to delete it first; formatDecimals restores it on blur
   * if the field is left empty. */
  function clearZeroOnFocus(event) {
    var el = event.target;
    if (el.dataset.field !== "gst_percent" && el.dataset.field !== "rate") return;
    if (Number(el.value) === 0) el.value = "";
  }

  function init(opts) {
    options = opts;
    dialog = document.getElementById("item-form-dialog");
    form = dialog.querySelector("[data-item-form]");
    alertBox = dialog.querySelector("[data-form-alert]");
    discard = dialog.querySelector("[data-discard]");
    discardTitle = discard.querySelector("#discard-title");
    discardCancelBtn = dialog.querySelector("[data-discard-cancel]");
    discardConfirmBtn = dialog.querySelector("[data-discard-confirm]");
    confirmBtn = dialog.querySelector("[data-form-confirm]");

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      save();
    });
    form.addEventListener("keydown", handleEnter);

    // Universal Help/Lookup: focus Unit, press Enter, pick from a searchable grid
    // instead of the browser's plain <datalist> suggestions.
    if (window.HelpLookup) {
      window.HelpLookup.attachDatalist(input("unit"), { title: "Unit" });
    }

    form.addEventListener("focusout", formatDecimals);
    form.addEventListener("focusin", clearZeroOnFocus);
    form.addEventListener("input", function (event) {
      var field = event.target;
      if (UPPERCASE_FIELDS[field.dataset.field] && field.value !== field.value.toUpperCase()) {
        var pos = field.selectionStart;
        field.value = field.value.toUpperCase();
        field.setSelectionRange(pos, pos);
      }
    });
    form.addEventListener("input", function (event) {
      var name = event.target.dataset.field;
      var holder = event.target.closest(".mform__field");
      if (name && holder && holder.classList.contains("is-invalid")) {
        holder.classList.remove("is-invalid");
        event.target.removeAttribute("aria-invalid");
        form.querySelector('[data-error-for="' + name + '"]').textContent = "";
      }
    });

    dialog.querySelectorAll("[data-form-exit]").forEach(function (btn) {
      btn.addEventListener("click", requestExit);
    });
    // Esc key: route through the same unsaved-changes check.
    dialog.addEventListener("cancel", function (event) {
      event.preventDefault();
      if (!discard.hidden) {
        discard.hidden = true;
      } else {
        requestExit();
      }
    });
    dialog.querySelector("[data-discard-cancel]").addEventListener("click", function () {
      discard.hidden = true;
    });
    dialog.querySelector("[data-discard-confirm]").addEventListener("click", function () {
      discard.hidden = true;
      var onConfirm = state.onDiscardConfirm || close;
      state.onDiscardConfirm = null;
      onConfirm();
    });
  }

  function open(mode, item, nextCode) {
    state.item = item || null;
    clearErrors();
    fill(item, nextCode);
    setMode(mode);
    discard.hidden = true;
    state.snapshot = JSON.stringify(values());
    dialog.showModal();
    var first = mode === "view" ? dialog.querySelector("[data-form-exit].btn") : mode === "delete" ? confirmBtn : input("item_name_1");
    first.focus();
  }

  window.SPItemForm = { init: init, open: open };
})();
