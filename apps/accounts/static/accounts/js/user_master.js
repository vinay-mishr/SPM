/* User Master — list screen + Add/Modify/View form, two profiles (Admin / Sales). */
(function () {
  "use strict";

  var root = document.querySelector("[data-user-master]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var countNote = root.querySelector("[data-count]");
  var searchBox = root.querySelector("[data-search]");
  var toast = document.querySelector("[data-toast]");
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;

  var initial = JSON.parse(document.getElementById("user-initial-data").textContent);
  var state = { users: initial.users, selectedId: null, query: "" };

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function selectedUser() {
    return state.users.find(function (u) { return u.id === state.selectedId; }) || null;
  }

  function matches(u) {
    if (!state.query) return true;
    var q = state.query;
    return u.username.toLowerCase().indexOf(q) > -1 || u.name.toLowerCase().indexOf(q) > -1;
  }

  function render() {
    var visible = state.users.filter(matches);
    tbody.textContent = "";
    visible.forEach(function (u) {
      var tr = document.createElement("tr");
      tr.dataset.id = u.id;
      tr.tabIndex = 0;
      tr.setAttribute("aria-selected", String(u.id === state.selectedId));
      if (u.id === state.selectedId) tr.classList.add("is-selected");
      [u.username + (u.is_you ? " (you)" : ""), u.name, u.role_label, u.is_active ? "Yes" : "No"].forEach(function (text) {
        var td = document.createElement("td");
        td.textContent = text;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    emptyNote.hidden = state.users.length > 0;
    countNote.textContent = state.users.length
      ? visible.length + " of " + state.users.length + " users"
      : "";
    updateToolbar();
  }

  function updateToolbar() {
    var user = selectedUser();
    root.querySelectorAll('[data-action="modify"], [data-action="view"]').forEach(function (btn) {
      btn.disabled = !user;
    });
    // Can't delete your own account while signed in as it -- services.delete()
    // refuses this server-side too, this just saves the round trip.
    root.querySelector('[data-action="delete"]').disabled = !user || user.is_you;
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
        state.users = data.users;
        if (selectId !== undefined) state.selectedId = selectId;
        if (!selectedUser()) state.selectedId = null;
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

  var dialog = document.getElementById("user-form-dialog");
  var form = dialog.querySelector("[data-user-form]");
  var alertBox = dialog.querySelector("[data-form-alert]");
  var discard = dialog.querySelector("[data-discard]");
  var discardTitle = discard.querySelector("#user-discard-title");
  var confirmBtn = dialog.querySelector("[data-form-confirm]");
  var usernameInput = dialog.querySelector('[data-field="username"]');
  var roleInput = dialog.querySelector('[data-field="role"]');
  var activeInput = dialog.querySelector('[data-field="is_active"]');
  var passwordInput = dialog.querySelector('[data-field="password"]');
  var activeRows = dialog.querySelectorAll('[data-active-row]');
  var passwordHint = dialog.querySelector('[data-password-hint]');
  var formState = { mode: "add", user: null, snapshot: "" };

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
      var field = form.querySelector('[data-field="' + name + '"]');
      if (target) {
        target.textContent = message;
        if (field) {
          field.closest(".mform__field").classList.add("is-invalid");
          first = first || field;
        }
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
    var readOnly = mode === "view" || mode === "delete";
    usernameInput.readOnly = readOnly || mode === "modify"; // username never changes once created
    roleInput.disabled = readOnly;
    activeInput.disabled = readOnly;
    passwordInput.readOnly = readOnly;
    confirmBtn.hidden = mode === "view";
    confirmBtn.textContent = mode === "delete" ? "Delete" : "Confirm";
    confirmBtn.classList.toggle("btn--danger", mode === "delete");
    confirmBtn.classList.toggle("btn--primary", mode !== "delete");
    // Active/password only matter once an account exists.
    activeRows.forEach(function (el) { el.hidden = mode === "add"; });
    passwordHint.hidden = mode !== "modify";
    passwordInput.required = mode === "add";
  }

  function isDirty() {
    if (formState.mode === "view" || formState.mode === "delete") return false;
    return usernameInput.value.trim() + "|" + roleInput.value + "|" + activeInput.checked + "|" + passwordInput.value
      !== formState.snapshot;
  }

  function close() {
    discard.hidden = true;
    dialog.close();
  }

  function requestExit() {
    if (isDirty()) { askDiscard("Discard unsaved changes?", close); return; }
    close();
  }

  function performDelete() {
    var user = formState.user;
    if (!user) return;
    confirmBtn.disabled = true;
    fetch(root.dataset.deleteUrl.replace("/0/", "/" + encodeURIComponent(user.id) + "/"), {
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

  function askDiscard(title, onConfirm) {
    discardTitle.textContent = title;
    formState.onDiscardConfirm = onConfirm;
    discard.hidden = false;
  }

  function save() {
    if (formState.mode === "delete") { askDiscard("Are you sure you want to delete this user?", performDelete); return; }
    if (formState.mode === "view") return;
    clearErrors();
    var data = new FormData();
    data.append("username", usernameInput.value.trim());
    data.append("role", roleInput.value);
    if (formState.mode === "modify") {
      data.append("is_active", activeInput.checked ? "1" : "0");
    }
    if (passwordInput.value) data.append("password", passwordInput.value);

    var url = formState.mode === "modify"
      ? root.dataset.updateUrl.replace("/0/", "/" + encodeURIComponent(formState.user.id) + "/")
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
          refresh(result.body.user.id);
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
    var user = mode === "add" ? null : selectedUser();
    formState.user = user;
    clearErrors();
    usernameInput.value = user ? user.username : "";
    roleInput.value = user ? user.role : (initial.roles[0] ? initial.roles[0][0] : "SALES");
    activeInput.checked = user ? user.is_active : true;
    passwordInput.value = "";
    setMode(mode);
    discard.hidden = true;
    formState.snapshot = usernameInput.value.trim() + "|" + roleInput.value + "|" + activeInput.checked + "|";
    dialog.showModal();
    (mode === "view" ? dialog.querySelector(".modal__footer [data-form-exit]")
      : mode === "delete" ? confirmBtn : usernameInput).focus();
  }

  /* --- Toolbar --------------------------------------------------------------------- */

  var actions = {
    add: function () { openForm("add"); },
    modify: function () { if (selectedUser()) openForm("modify"); },
    view: function () { if (selectedUser()) openForm("view"); },
    "delete": function () { var u = selectedUser(); if (u && !u.is_you) openForm("delete"); },
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
