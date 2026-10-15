/* Marketing Manager — shared Add / Modify / View form.
 * Exposes window.SPManagerForm.init(options) and .open(mode, manager).
 * Enter moves to the next field; EXIT asks before discarding changes; Django validates again.
 */
(function () {
  "use strict";

  var FIELDS = ["name", "address_1", "address_2", "mobile"];
  var LABELS = { add: "Add", modify: "Modify", view: "View" };
  var dialog, form, alertBox, discard, confirmBtn, options;
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

  function save() {
    if (state.saving || state.mode === "view") return;
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
    confirmBtn = dialog.querySelector("[data-form-confirm]");

    form.addEventListener("submit", function (e) { e.preventDefault(); save(); });
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
    dialog.querySelector("[data-discard-confirm]").addEventListener("click", close);
  }

  function open(mode, manager) {
    state.mode = mode;
    state.manager = manager || null;
    clearErrors();
    discard.hidden = true;
    dialog.dataset.mode = mode;
    dialog.querySelector("[data-mode-label]").textContent = LABELS[mode];
    input("code").value = manager ? manager.code : "";
    FIELDS.forEach(function (n) {
      input(n).value = manager ? manager[n] || "" : "";
      input(n).readOnly = mode === "view";
    });
    if (mode === "add") {
      fetch(options.nextCodeUrl, { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (d) { if (state.mode === "add") input("code").value = d.code || ""; })
        .catch(function () {});
    }
    state.snapshot = JSON.stringify(values());
    dialog.showModal();
    (mode === "view" ? dialog.querySelector(".modal__footer [data-form-exit]") : input("name")).focus();
  }

  window.SPManagerForm = { init: init, open: open };
})();
