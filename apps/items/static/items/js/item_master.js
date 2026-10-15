/* Item Master — list screen: table, row selection, search, toolbar actions, delete dialog.
 * Uses window.SPItemForm (item_form.js) for Add / Modify / View.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-item-master]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var countNote = root.querySelector("[data-count]");
  var searchBox = root.querySelector("[data-search]");
  var toast = document.querySelector("[data-toast]");
  var deleteDialog = document.getElementById("item-delete-dialog");
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;

  var initial = JSON.parse(document.getElementById("item-initial-data").textContent);
  var state = { items: initial.items, nextCode: initial.next_code, selectedId: null, query: "" };

  var money = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  /* --- Helpers ---------------------------------------------------------------- */

  function selectedItem() {
    return state.items.find(function (item) { return item.id === state.selectedId; }) || null;
  }

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function cell(text, className) {
    var td = document.createElement("td");
    td.textContent = text;
    if (text) td.title = text; // full value on hover, in case it's truncated by ellipsis
    if (className) td.className = className;
    return td;
  }

  function matches(item) {
    if (!state.query) return true;
    var haystack = [item.item_code, item.item_name_1, item.item_name_2, item.item_name_3]
      .join(" ").toLowerCase();
    return haystack.indexOf(state.query) > -1;
  }

  /* --- Rendering -------------------------------------------------------------- */

  function render() {
    var visible = state.items.filter(matches);
    tbody.textContent = "";

    visible.forEach(function (item) {
      var tr = document.createElement("tr");
      tr.dataset.id = item.id;
      tr.tabIndex = 0;
      tr.setAttribute("aria-selected", String(item.id === state.selectedId));
      if (item.id === state.selectedId) tr.classList.add("is-selected");
      tr.append(
        cell(item.item_name_1),
        cell(item.item_name_2),
        cell(item.item_name_3),
        cell(money.format(item.rate), "num"),
        cell(money.format(item.gst_percent), "num"),
        cell(item.item_code, "master-table__code")
      );
      tbody.appendChild(tr);
    });

    emptyNote.hidden = state.items.length > 0;
    countNote.textContent = state.items.length
      ? visible.length + " of " + state.items.length + " item" + (state.items.length === 1 ? "" : "s")
      : "";
    updateToolbar();
  }

  function updateToolbar() {
    var hasSelection = Boolean(selectedItem());
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
      .then(function (response) { return response.json(); })
      .then(function (data) {
        state.items = data.items;
        state.nextCode = data.next_code;
        if (selectId !== undefined) state.selectedId = selectId;
        if (!selectedItem()) state.selectedId = null;
        render();
        var row = tbody.querySelector('tr[data-id="' + state.selectedId + '"]');
        if (row) row.scrollIntoView({ block: "nearest" });
      });
  }

  /* --- Delete dialog ---------------------------------------------------------- */

  var DETAIL_LABELS = [
    ["item_code", "Item Code"], ["item_name_1", "Item Name 1"], ["item_name_2", "Item Name 2"],
    ["item_name_3", "Item Name 3"], ["unit", "Unit"], ["hsn_code", "HSN Code"],
    ["gst_percent", "GST %"], ["rate", "Rate"], ["opening_balance", "Op. Balance"]
  ];

  function openDelete(item) {
    var details = deleteDialog.querySelector("[data-delete-details]");
    var alertBox = deleteDialog.querySelector("[data-delete-alert]");
    details.textContent = "";
    DETAIL_LABELS.forEach(function (pair) {
      var dt = document.createElement("dt");
      var dd = document.createElement("dd");
      dt.textContent = pair[1];
      dd.textContent = item[pair[0]] || "—";
      details.append(dt, dd);
    });
    alertBox.hidden = true;
    deleteDialog.querySelector("[data-delete-confirm]").disabled = false;
    deleteDialog.showModal();
    deleteDialog.querySelector(".modal__footer [data-delete-cancel]").focus();
  }

  function confirmDelete() {
    var item = selectedItem();
    var button = deleteDialog.querySelector("[data-delete-confirm]");
    var alertBox = deleteDialog.querySelector("[data-delete-alert]");
    if (!item) return;
    button.disabled = true;

    fetch(root.dataset.deleteUrl.replace("/0/", "/" + encodeURIComponent(item.id) + "/"), {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin"
    })
      .then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (body) {
          return { ok: response.ok, body: body };
        });
      })
      .then(function (result) {
        if (result.ok) {
          deleteDialog.close();
          state.selectedId = null;
          showToast(result.body.message);
          return refresh();
        }
        alertBox.textContent = result.body.message || "The item could not be deleted.";
        alertBox.hidden = false;
      })
      .catch(function () {
        alertBox.textContent = "Could not reach the server. Please try again.";
        alertBox.hidden = false;
        button.disabled = false;
      });
  }

  /* --- Actions ------------------------------------------------------------------ */

  var actions = {
    add: function () { SPItemForm.open("add", null, state.nextCode); },
    modify: function () { var item = selectedItem(); if (item) SPItemForm.open("modify", item); },
    view: function () { var item = selectedItem(); if (item) SPItemForm.open("view", item); },
    "delete": function () { var item = selectedItem(); if (item) openDelete(item); },
    exit: function () { window.location.href = root.dataset.exitUrl; }
  };

  root.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function () { actions[btn.dataset.action](); });
  });

  tbody.addEventListener("click", function (event) {
    var row = event.target.closest("tr");
    if (row) select(row.dataset.id);
  });

  tbody.addEventListener("dblclick", function (event) {
    var row = event.target.closest("tr");
    if (row) { select(row.dataset.id); actions.view(); }
  });

  tbody.addEventListener("keydown", function (event) {
    var row = event.target.closest("tr");
    if (!row) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      select(row.dataset.id);
      if (event.key === "Enter") actions.view();
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      var next = event.key === "ArrowDown" ? row.nextElementSibling : row.previousElementSibling;
      if (next) { next.focus(); select(next.dataset.id); }
    }
  });

  searchBox.addEventListener("input", function () {
    state.query = searchBox.value.trim().toLowerCase();
    render();
  });

  // Alt + A / M / D / V / E shortcuts, matching the underlined letters.
  document.addEventListener("keydown", function (event) {
    if (!event.altKey || document.querySelector("dialog[open]")) return;
    var map = { a: "add", m: "modify", d: "delete", v: "view", e: "exit" };
    var action = map[event.key.toLowerCase()];
    var button = action && root.querySelector('[data-action="' + action + '"]');
    if (button && !button.disabled) {
      event.preventDefault();
      button.click();
    }
  });

  deleteDialog.querySelectorAll("[data-delete-cancel]").forEach(function (btn) {
    btn.addEventListener("click", function () { deleteDialog.close(); });
  });
  deleteDialog.querySelector("[data-delete-confirm]").addEventListener("click", confirmDelete);

  SPItemForm.init({
    createUrl: root.dataset.createUrl,
    updateUrl: root.dataset.updateUrl,
    csrfToken: csrfToken,
    onSaved: function (item, message) {
      showToast(message);
      refresh(item.id);
    }
  });

  render();
})();
