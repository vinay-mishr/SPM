/* Material Master — shared Add / Modify / View form.
 * Exposes window.SPMaterialForm.init(options) and .open(mode, material).
 * The code is auto-generated (first letter of the name + next number, e.g. A002) and
 * previewed as you type the name, like Party Master. Enter moves to Confirm (there's
 * only one field); EXIT asks before discarding changes; Django validates again.
 */
(function () {
  "use strict";

  var FIELDS = ["name"];
  var UPPERCASE_FIELDS = { name: true };
  var LABELS = { add: "Add", modify: "Modify", view: "View", "delete": "Delete" };
  var dialog, form, alertBox, discard, discardTitle, discardCancelBtn, discardConfirmBtn, confirmBtn, options;
  var state = { mode: "add", material: null, snapshot: "", saving: false };

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

  function validate(v) {
    var e = {};
    if (!v.name) e.name = ["Name is required."];
    return e;
  }

  function close() { discard.hidden = true; dialog.close(); }

  function requestExit() {
    close();
  }

  function previewCode() {
    if (state.mode !== "add") return;
    var name = input("name").value.trim();
    if (!name) { input("code").value = ""; return; }
    fetch(options.nextCodeUrl + "?name=" + encodeURIComponent(name), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) { if (state.mode === "add") input("code").value = d.code || ""; })
      .catch(function () {});
  }

  function performDelete() {
    if (state.saving || !state.material) return;
    state.saving = true;
    confirmBtn.disabled = true;
    fetch(options.deleteUrl.replace("/00/", "/" + encodeURIComponent(state.material.id) + "/"), {
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
      ? options.updateUrl.replace("/00/", "/" + encodeURIComponent(state.material.id) + "/")
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
          options.onSaved(res.body.material, res.body.message);
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
    dialog = document.getElementById("mat-form-dialog");
    form = dialog.querySelector("[data-mat-form]");
    alertBox = dialog.querySelector("[data-form-alert]");
    discard = dialog.querySelector("[data-discard]");
    discardTitle = discard.querySelector("#mat-discard-title");
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
      if (state.mode !== "view") confirmBtn.focus();
    });
    input("name").addEventListener("input", previewCode);
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

  function open(mode, material) {
    state.mode = mode;
    state.material = material || null;
    clearErrors();
    discard.hidden = true;
    dialog.dataset.mode = mode;
    dialog.querySelector("[data-mode-label]").textContent = LABELS[mode];
    input("code").value = material ? material.code : "";
    var readOnlyMode = mode === "view" || mode === "delete";
    FIELDS.forEach(function (n) {
      input(n).value = material ? material[n] || "" : "";
      input(n).readOnly = readOnlyMode;
    });
    confirmBtn.textContent = mode === "delete" ? "Delete" : "Confirm";
    confirmBtn.classList.toggle("btn--danger", mode === "delete");
    confirmBtn.classList.toggle("btn--primary", mode !== "delete");
    state.snapshot = JSON.stringify(values());
    dialog.showModal();
    (mode === "view" ? dialog.querySelector(".modal__footer [data-form-exit]") : mode === "delete" ? confirmBtn : input("name")).focus();
  }

  window.SPMaterialForm = { init: init, open: open };
})();
