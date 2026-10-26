/* Party Master — list screen: table, row selection, search, toolbar actions, delete dialog.
 * Uses window.SPPartyForm (party_master_form.js) for Add / Modify / View.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-party-master]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var countNote = root.querySelector("[data-count]");
  var searchBox = root.querySelector("[data-search]");
  var toast = document.querySelector("[data-toast]");
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;

  var initial = JSON.parse(document.getElementById("party-initial-data").textContent);
  var state = { parties: initial.parties, selectedId: null, query: "" };

  /* --- Helpers ---------------------------------------------------------------- */

  function selectedParty() {
    return state.parties.find(function (p) { return p.id === state.selectedId; }) || null;
  }

  function phone(party) {
    return party.phone_1 || party.mobile_1 || party.mobile_2 || "";
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
    if (className) td.className = className;
    return td;
  }

  function matches(party) {
    if (!state.query) return true;
    var haystack = [party.party_code, party.name, party.city, party.mobile_1, party.mobile_2,
      party.state_name, party.gst_no, party.contact_person_1, party.contact_person_2]
      .join(" ").toLowerCase();
    return haystack.indexOf(state.query) > -1;
  }

  /* --- Rendering -------------------------------------------------------------- */

  function render() {
    var visible = state.parties.filter(matches);
    tbody.textContent = "";

    visible.forEach(function (party) {
      var tr = document.createElement("tr");
      tr.dataset.id = party.id;
      tr.tabIndex = 0;
      tr.setAttribute("aria-selected", String(party.id === state.selectedId));
      if (party.id === state.selectedId) tr.classList.add("is-selected");
      if (!party.is_active) tr.classList.add("is-inactive");
      tr.append(
        cell(party.name + (party.is_active ? "" : " (inactive)")),
        cell(party.city),
        cell(phone(party)),
        cell(party.party_code, "master-table__code")
      );
      tbody.appendChild(tr);
    });

    emptyNote.hidden = state.parties.length > 0;
    countNote.textContent = state.parties.length
      ? visible.length + " of " + state.parties.length + " part" + (state.parties.length === 1 ? "y" : "ies")
      : "";
    updateToolbar();
  }

  function updateToolbar() {
    var hasSelection = Boolean(selectedParty());
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
        state.parties = data.parties;
        SPPartyForm.setSuggestions(data.suggestions);
        if (selectId !== undefined) state.selectedId = selectId;
        if (!selectedParty()) state.selectedId = null;
        render();
        var row = tbody.querySelector('tr[data-id="' + state.selectedId + '"]');
        if (row) row.scrollIntoView({ block: "nearest" });
      });
  }

  /* --- Actions ------------------------------------------------------------------ */

  var actions = {
    add: function () { SPPartyForm.open("add", null); },
    modify: function () { var p = selectedParty(); if (p) SPPartyForm.open("modify", p); },
    view: function () { var p = selectedParty(); if (p) SPPartyForm.open("view", p); },
    "delete": function () { var p = selectedParty(); if (p) SPPartyForm.open("delete", p); },
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

  SPPartyForm.init({
    createUrl: root.dataset.createUrl,
    updateUrl: root.dataset.updateUrl,
    deleteUrl: root.dataset.deleteUrl,
    csrfToken: csrfToken,
    companyStateCode: initial.company_state_code,
    nextCodeUrl: root.dataset.nextCodeUrl,
    gstinLookupUrl: root.dataset.gstinLookupUrl,
    onSaved: function (party, message) {
      showToast(message);
      refresh(party.id);
    },
    onDeleted: function (message) {
      state.selectedId = null;
      showToast(message);
      refresh();
    }
  });

  render();
})();
