/* Marketing Manager — shared Add / Modify / View form.
 * Exposes window.SPManagerForm.init(options) and .open(mode, manager).
 * Enter moves to the next field; EXIT asks before discarding changes; Django validates again.
 */
(function () {
  "use strict";

  var FIELDS = ["name", "address_1", "address_2", "mobile"];
  var UPPERCASE_FIELDS = { name: true, address_1: true, address_2: true };
  var LABELS = { add: "Add", modify: "Modify", view: "View", "delete": "Delete" };
  var dialog, form, alertBox, discard, discardTitle, discardCancelBtn, discardConfirmBtn, confirmBtn, options;
  var state = { mode: "add", manager: null, snapshot: "", saving: false };

  function input(name) { return form.querySelector('[data-field="' + name + '"]'); }

  function values() {
    var v = {};
    FIELDS.forEach(function (n) { v[n] = input(n).value.trim(); });
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

  function mobileDigits(value) {
    var d = value.replace(/[\s\-()]/g, "");
    if (d.indexOf("+91") === 0) d = d.slice(3);
    else if (d.indexOf("91") === 0 && d.length === 12) d = d.slice(2);
    else if (d.indexOf("0") === 0 && d.length === 11) d = d.slice(1);
    return d;
  }

  function validate(v) {
    var e = {};
    if (!v.name) e.name = ["Manager name is required."];
    if (v.mobile && !/^\d{10}$/.test(mobileDigits(v.mobile))) e.mobile = ["Mobile number must be 10 digits."];
    return e;
  }

  function close() { discard.hidden = true; dialog.close(); }

  function requestExit() {
    close();
  }

  function performDelete() {
    if (state.saving || !state.manager) return;
    state.saving = true;
    confirmBtn.disabled = true;
    fetch(options.deleteUrl.replace("/00/", "/" + encodeURIComponent(state.manager.id) + "/"), {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": options.csrfToken, "X-Requested-With": "XMLHttpRequest" }
    })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; });
      })
      .then(function (res) {
        if (res.ok) {
          close();
          options.onDeleted(res.body.message);
        } else {
          alertBox.textContent = res.body.message || "Could not delete.";
          alertBox.hidden = false;
        }
      })
      .catch(function () {
        alertBox.textContent = "Could not reach the server. Nothing was deleted.";
        alertBox.hidden = false;
      })
      .finally(function () { state.saving = false; confirmBtn.disabled = false; });
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
      askDiscard("Are you sure you want to delete this record?", performDelete, { cancel: "No", confirm: "Yes" });
      return;
    }
    if (state.mode === "view") return;
    clearErrors();
    var v = values();
    var errs = validate(v);
    if (Object.keys(errs).length) { showErrors(errs); return; }

    var body = new FormData();
    FIELDS.forEach(function (n) { body.append(n, v[n]); });
    var url = state.mode === "modify"
      ? options.updateUrl.replace("/00/", "/" + encodeURIComponent(state.manager.id) + "/")
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
          options.onSaved(res.body.manager, res.body.message);
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

  function init(opts) {
    options = opts;
    dialog = document.getElementById("mm-form-dialog");
    form = dialog.querySelector("[data-mm-form]");
    alertBox = dialog.querySelector("[data-form-alert]");
    discard = dialog.querySelector("[data-discard]");
    discardTitle = discard.querySelector("#mm-discard-title");
    discardCancelBtn = dialog.querySelector("[data-discard-cancel]");
    discardConfirmBtn = dialog.querySelector("[data-discard-confirm]");
    confirmBtn = dialog.querySelector("[data-form-confirm]");

    form.addEventListener("submit", function (e) { e.preventDefault(); save(); });
    form.addEventListener("input", function (e) {
      var field = e.target;
      if (UPPERCASE_FIELDS[field.dataset.field] && field.value !== field.value.toUpperCase()) {
        var pos = field.selectionStart;
        field.value = field.value.toUpperCase();
        field.setSelectionRange(pos, pos);
      }
    });
    form.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" || e.target.tagName !== "INPUT") return;
      e.preventDefault();
      var list = FIELDS.map(input).filter(function (el) { return !el.readOnly; });
      var i = list.indexOf(e.target);
      if (i > -1 && i < list.length - 1) list[i + 1].focus();
      else if (state.mode !== "view") confirmBtn.focus();
    });
    dialog.querySelectorAll("[data-form-exit]").forEach(function (b) { b.addEventListener("click", requestExit); });
    dialog.addEventListener("cancel", function (e) {
      e.preventDefault();
      if (!discard.hidden) discard.hidden = true; else requestExit();
    });
    dialog.querySelector("[data-discard-cancel]").addEventListener("click", function () { discard.hidden = true; });
    dialog.querySelector("[data-discard-confirm]").addEventListener("click", function () {
      discard.hidden = true;
      var onConfirm = state.onDiscardConfirm || close;
      state.onDiscardConfirm = null;
      onConfirm();
    });
  }

  function open(mode, manager) {
    state.mode = mode;
    state.manager = manager || null;
    clearErrors();
    discard.hidden = true;
    dialog.dataset.mode = mode;
    dialog.querySelector("[data-mode-label]").textContent = LABELS[mode];
    input("code").value = manager ? manager.code : "";
    var readOnlyMode = mode === "view" || mode === "delete";
    FIELDS.forEach(function (n) {
      input(n).value = manager ? manager[n] || "" : "";
      input(n).readOnly = readOnlyMode;
    });
    confirmBtn.textContent = mode === "delete" ? "Delete" : "Confirm";
    confirmBtn.classList.toggle("btn--danger", mode === "delete");
    confirmBtn.classList.toggle("btn--primary", mode !== "delete");
    if (mode === "add") {
      fetch(options.nextCodeUrl, { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (d) { if (state.mode === "add") input("code").value = d.code || ""; })
        .catch(function () {});
    }
    state.snapshot = JSON.stringify(values());
    dialog.showModal();
    (mode === "view" ? dialog.querySelector(".modal__footer [data-form-exit]") : mode === "delete" ? confirmBtn : input("name")).focus();
  }

  window.SPManagerForm = { init: init, open: open };
})();
