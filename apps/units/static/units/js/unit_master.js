/* Unit Master — list screen + shared tiny Add/Modify/View form (old VFP "UNIT ..." window). */
(function () {
  "use strict";

  var root = document.querySelector("[data-unit-master]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var countNote = root.querySelector("[data-count]");
  var searchBox = root.querySelector("[data-search]");
  var toast = document.querySelector("[data-toast]");
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;

  var initial = JSON.parse(document.getElementById("unit-initial-data").textContent);
  var state = { units: initial.units, selectedId: null, query: "" };

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function selectedUnit() {
    return state.units.find(function (u) { return u.id === state.selectedId; }) || null;
  }

  function matches(u) {
    return !state.query || u.name.toLowerCase().indexOf(state.query) > -1;
  }

  function render() {
    var visible = state.units.filter(matches);
    tbody.textContent = "";
    visible.forEach(function (u) {
      var tr = document.createElement("tr");
      tr.dataset.id = u.id;
      tr.tabIndex = 0;
      tr.setAttribute("aria-selected", String(u.id === state.selectedId));
      if (u.id === state.selectedId) tr.classList.add("is-selected");
      var td = document.createElement("td");
      td.textContent = u.name;
      tr.appendChild(td);
      tbody.appendChild(tr);
    });
    emptyNote.hidden = state.units.length > 0;
    countNote.textContent = state.units.length
      ? visible.length + " of " + state.units.length + " units"
      : "";
    updateToolbar();
  }

  function updateToolbar() {
    var hasSelection = Boolean(selectedUnit());
    root.querySelectorAll('[data-action="modify"], [data-action="delete"], [data-action="view"]').forEach(function (btn) {
      btn.disabled = !hasSelection;
    });
  }

  function select(id) {
    state.selectedId = id;
    tbody.querySelectorAll("tr").forEach(function (tr) {
      var on = tr.dataset.id === id;
      tr.classList.toggle("is-selected", on);
      tr.setAttribute("aria-selected", String(on));
    });
    updateToolbar();
  }

  function refresh(selectId) {
    return fetch(root.dataset.listUrl, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        state.units = data.units;
        if (selectId !== undefined) state.selectedId = selectId;
        if (!selectedUnit()) state.selectedId = null;
        render();
      });
  }

  tbody.addEventListener("click", function (e) { var tr = e.target.closest("tr"); if (tr) select(tr.dataset.id); });
  tbody.addEventListener("dblclick", function (e) { var tr = e.target.closest("tr"); if (tr) { select(tr.dataset.id); openForm("view"); } });
  tbody.addEventListener("keydown", function (e) {
    var tr = e.target.closest("tr");
    if (!tr) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      var next = e.key === "ArrowDown" ? tr.nextElementSibling : tr.previousElementSibling;
      if (next) { next.focus(); select(next.dataset.id); }
    } else if (e.key === "Enter") { select(tr.dataset.id); openForm("view"); }
  });
  searchBox.addEventListener("input", function () { state.query = searchBox.value.trim().toLowerCase(); render(); });

  /* --- Form (ADD / MODIFY / VIEW) ------------------------------------------------- */

  var dialog = document.getElementById("unit-form-dialog");
  var form = dialog.querySelector("[data-unit-form]");
  var alertBox = dialog.querySelector("[data-form-alert]");
  var discard = dialog.querySelector("[data-discard]");
  var discardTitle = discard.querySelector("#unit-discard-title");
  var confirmBtn = dialog.querySelector("[data-form-confirm]");
  var nameInput = dialog.querySelector('[data-field="name"]');
  var formState = { mode: "add", unit: null, snapshot: "" };

  function clearErrors() {
    alertBox.hidden = true;
    alertBox.textContent = "";
    form.querySelectorAll("[data-error-for]").forEach(function (el) { el.textContent = ""; });
    form.querySelectorAll(".mform__field.is-invalid").forEach(function (el) { el.classList.remove("is-invalid"); });
  }

  function showErrors(errors) {
    var first = null;
    Object.keys(errors || {}).forEach(function (name) {
      var message = typeof errors[name] === "string" ? errors[name]
        : (errors[name].map ? errors[name].map(function (e) { return e.message || e; }).join(" ") : String(errors[name]));
      var target = form.querySelector('[data-error-for="' + name + '"]');
      if (target) {
        target.textContent = message;
        nameInput.closest(".mform__field").classList.add("is-invalid");
        first = first || nameInput;
      } else {
        alertBox.textContent = message;
        alertBox.hidden = false;
      }
    });
    if (first) first.focus();
  }

  var MODE_LABELS = { add: "Add", modify: "Modify", view: "View", "delete": "Delete" };

  function setMode(mode) {
    formState.mode = mode;
    dialog.dataset.mode = mode;
    dialog.querySelector("[data-mode-label]").textContent = MODE_LABELS[mode];
    nameInput.readOnly = mode === "view" || mode === "delete";
    confirmBtn.hidden = mode === "view";
    confirmBtn.textContent = mode === "delete" ? "Delete" : "Confirm";
    confirmBtn.classList.toggle("btn--danger", mode === "delete");
    confirmBtn.classList.toggle("btn--primary", mode !== "delete");
  }

  function isDirty() {
    return formState.mode !== "view" && formState.mode !== "delete" && nameInput.value.trim() !== formState.snapshot;
  }

  function close() {
    discard.hidden = true;
    dialog.close();
  }

  function requestExit() {
    close();
  }

  function performDelete() {
    var unit = formState.unit;
    if (!unit) return;
    confirmBtn.disabled = true;
    fetch(root.dataset.deleteUrl.replace("/0/", "/" + encodeURIComponent(unit.id) + "/"), {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" }
    })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (result) {
        if (result.ok) {
          close();
          state.selectedId = null;
          showToast(result.body.message);
          return refresh();
        }
        alertBox.textContent = result.body.message || "Could not delete.";
        alertBox.hidden = false;
      })
      .catch(function () {
        alertBox.textContent = "Could not reach the server. Nothing was deleted.";
        alertBox.hidden = false;
      })
      .finally(function () { confirmBtn.disabled = false; });
  }

  // The discard box is reused as a generic "are you sure?" prompt -- its own
  // title text and confirm action are swapped per use (discard unsaved
  // changes on EXIT vs delete the selected record), so there's one small
  // confirm dialog in this form, not two.
  function askDiscard(title, onConfirm) {
    discardTitle.textContent = title;
    formState.onDiscardConfirm = onConfirm;
    discard.hidden = false;
  }

  function save() {
    if (formState.mode === "delete") { askDiscard("Are you sure you want to delete this record?", performDelete); return; }
    if (formState.mode === "view") return;
    clearErrors();
    var data = new FormData();
    data.append("name", nameInput.value.trim());

    var url = formState.mode === "modify"
      ? root.dataset.updateUrl.replace("/0/", "/" + encodeURIComponent(formState.unit.id) + "/")
      : root.dataset.createUrl;

    confirmBtn.disabled = true;
    fetch(url, {
      method: "POST", body: data, credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" }
    })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; }); })
      .then(function (result) {
        if (result.ok) {
          close();
          showToast(result.body.message);
          refresh(result.body.unit.id);
        } else if (result.body.errors) {
          showErrors(result.body.errors);
        } else {
          alertBox.textContent = result.body.message || "Could not save (error " + result.status + ").";
          alertBox.hidden = false;
        }
      })
      .catch(function () {
        alertBox.textContent = "Could not reach the server. Nothing was saved.";
        alertBox.hidden = false;
      })
      .finally(function () { confirmBtn.disabled = false; });
  }

  form.addEventListener("submit", function (e) { e.preventDefault(); save(); });
  dialog.querySelectorAll("[data-form-exit]").forEach(function (b) { b.addEventListener("click", requestExit); });
  dialog.addEventListener("cancel", function (e) {
    e.preventDefault();
    if (!discard.hidden) discard.hidden = true; else requestExit();
  });
  dialog.querySelector("[data-discard-cancel]").addEventListener("click", function () { discard.hidden = true; });
  dialog.querySelector("[data-discard-confirm]").addEventListener("click", function () {
    discard.hidden = true;
    var onConfirm = formState.onDiscardConfirm || close;
    formState.onDiscardConfirm = null;
    onConfirm();
  });

  function openForm(mode) {
    var unit = mode === "add" ? null : selectedUnit();
    formState.unit = unit;
    clearErrors();
    nameInput.value = unit ? unit.name : "";
    setMode(mode);
    discard.hidden = true;
    formState.snapshot = nameInput.value.trim();
    dialog.showModal();
    (mode === "view" ? dialog.querySelector(".modal__footer [data-form-exit]")
      : mode === "delete" ? confirmBtn : nameInput).focus();
  }

  /* --- Toolbar --------------------------------------------------------------------- */

  var actions = {
    add: function () { openForm("add"); },
    modify: function () { if (selectedUnit()) openForm("modify"); },
    view: function () { if (selectedUnit()) openForm("view"); },
    "delete": function () { if (selectedUnit()) openForm("delete"); },
    exit: function () { window.location.href = root.dataset.exitUrl; }
  };
  root.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function () { actions[btn.dataset.action](); });
  });
  document.addEventListener("keydown", function (e) {
    if (!e.altKey || document.querySelector("dialog[open]")) return;
    var map = { a: "add", m: "modify", d: "delete", v: "view", e: "exit" };
    var action = map[e.key.toLowerCase()];
    var button = action && root.querySelector('[data-action="' + action + '"]');
    if (button && !button.disabled) { e.preventDefault(); button.click(); }
  });

  render();
})();
