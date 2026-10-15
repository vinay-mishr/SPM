/* Vendor Master — list screen: table, row selection, search, toolbar actions, delete dialog.
 * Uses window.SPVendorForm (vendor_form.js) for Add / Modify / View.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-vendor-master]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var countNote = root.querySelector("[data-count]");
  var searchBox = root.querySelector("[data-search]");
  var toast = document.querySelector("[data-toast]");
  var deleteDialog = document.getElementById("vendor-delete-dialog");
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;

  var initial = JSON.parse(document.getElementById("vendor-initial-data").textContent);
  var state = { vendors: initial.vendors, selectedId: null, query: "" };

  /* --- Helpers ---------------------------------------------------------------- */

  function selectedVendor() {
    return state.vendors.find(function (v) { return v.id === state.selectedId; }) || null;
  }

  function money(value) {
    var num = Number(value || 0);
    return num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function stateLabel(vendor) {
    return vendor.state_code ? vendor.state_name + " (" + vendor.state_code + ")" : "";
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

  function matches(vendor) {
    if (!state.query) return true;
    var haystack = [vendor.party_code, vendor.name, vendor.city, vendor.phone_no, vendor.mobile_1,
      vendor.state_name, vendor.gst_no, vendor.contact_person_1, vendor.contact_person_2]
      .join(" ").toLowerCase();
    return haystack.indexOf(state.query) > -1;
  }

  /* --- Rendering -------------------------------------------------------------- */

  function render() {
    var visible = state.vendors.filter(matches);
    tbody.textContent = "";

    visible.forEach(function (vendor) {
      var tr = document.createElement("tr");
      tr.dataset.id = vendor.id;
      tr.tabIndex = 0;
      tr.setAttribute("aria-selected", String(vendor.id === state.selectedId));
      if (vendor.id === state.selectedId) tr.classList.add("is-selected");
      if (!vendor.is_active) tr.classList.add("is-inactive");
      tr.append(
        cell(vendor.party_code, "master-table__code"),
        cell(vendor.name + (vendor.is_active ? "" : " (inactive)")),
        cell(vendor.city),
        cell(vendor.phone_no),
        cell(vendor.mobile_1),
        cell(vendor.gst_no),
        cell(stateLabel(vendor)),
        cell(money(vendor.opening_balance), "num"),
        cell(String(vendor.credit_days), "num")
      );
      tbody.appendChild(tr);
    });

    emptyNote.hidden = state.vendors.length > 0;
    countNote.textContent = state.vendors.length
      ? visible.length + " of " + state.vendors.length + " vendor" + (state.vendors.length === 1 ? "" : "s")
      : "";
    updateToolbar();
  }

  function updateToolbar() {
    var hasSelection = Boolean(selectedVendor());
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
        state.vendors = data.vendors;
        SPVendorForm.setSuggestions(data.suggestions);
        if (selectId !== undefined) state.selectedId = selectId;
        if (!selectedVendor()) state.selectedId = null;
        render();
        var row = tbody.querySelector('tr[data-id="' + state.selectedId + '"]');
        if (row) row.scrollIntoView({ block: "nearest" });
      });
  }

  /* --- Delete dialog ---------------------------------------------------------- */

  function details(vendor) {
    var address = [vendor.address_1, vendor.address_2, vendor.address_3].filter(Boolean).join(", ");
    return [
      ["Vendor Code", vendor.party_code], ["Name", vendor.name], ["Address", address],
      ["City", vendor.city + (vendor.pin ? " - " + vendor.pin : "")], ["State", stateLabel(vendor)],
      ["GST No.", vendor.gst_no], ["GST Category", vendor.gst_category],
      ["Phone", vendor.phone_no], ["Mobile 1", vendor.mobile_1],
      ["Opening Balance", vendor.opening_balance], ["Transport", vendor.transport],
      ["Con. Person 1", vendor.contact_person_1], ["Mobile Person 1", vendor.mobile_person_1],
      ["Con. Person 2", vendor.contact_person_2], ["Mobile Person 2", vendor.mobile_person_2],
      ["Email", vendor.email], ["Cr Days", vendor.credit_days], ["Association", vendor.association],
      ["Grade", vendor.grade],
      ["W / I", vendor.supply_type === "W" ? "Within" : vendor.supply_type === "I" ? "Interstate" : ""],
      ["Active", vendor.is_active ? "Yes" : "No"]
    ];
  }

  function openDelete(vendor) {
    var list = deleteDialog.querySelector("[data-delete-details]");
    var alertBox = deleteDialog.querySelector("[data-delete-alert]");
    list.textContent = "";
    details(vendor).forEach(function (pair) {
      var dt = document.createElement("dt");
      var dd = document.createElement("dd");
      dt.textContent = pair[0];
      dd.textContent = pair[1] || "—";
      list.append(dt, dd);
    });
    alertBox.hidden = true;
    deleteDialog.querySelector("[data-delete-confirm]").disabled = false;
    deleteDialog.showModal();
    deleteDialog.querySelector(".modal__footer [data-delete-cancel]").focus();
  }

  function confirmDelete() {
    var vendor = selectedVendor();
    var button = deleteDialog.querySelector("[data-delete-confirm]");
    var alertBox = deleteDialog.querySelector("[data-delete-alert]");
    if (!vendor) return;
    button.disabled = true;

    fetch(root.dataset.deleteUrl.replace("/0/", "/" + encodeURIComponent(vendor.id) + "/"), {
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
        alertBox.textContent = result.body.message || "The vendor could not be deleted.";
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
    add: function () { SPVendorForm.open("add", null); },
    modify: function () { var v = selectedVendor(); if (v) SPVendorForm.open("modify", v); },
    view: function () { var v = selectedVendor(); if (v) SPVendorForm.open("view", v); },
    "delete": function () { var v = selectedVendor(); if (v) openDelete(v); },
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

  SPVendorForm.init({
    createUrl: root.dataset.createUrl,
    updateUrl: root.dataset.updateUrl,
    csrfToken: csrfToken,
    companyStateCode: initial.company_state_code,
    nextCodeUrl: root.dataset.nextCodeUrl,
    onSaved: function (vendor, message) {
      showToast(message);
      refresh(vendor.id);
    }
  });

  render();
})();
