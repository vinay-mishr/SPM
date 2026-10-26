(function () {
  "use strict";

  const root = document.querySelector("[data-rate-modification]");
  if (!root) return;

  const dataUrl = root.dataset.dataUrl;
  const saveUrl = root.dataset.saveUrl;
  const exitUrl = root.dataset.exitUrl;
  const canEdit = !document.querySelector("[data-confirm]").hasAttribute("disabled");

  const tbody = root.querySelector("[data-rows]");
  const emptyMsg = root.querySelector("[data-empty]");
  const changesEl = root.querySelector("[data-changes]");
  const toast = document.querySelector("[data-toast]");
  const confirmBtn = root.querySelector("[data-confirm]");
  const exitBtn = root.querySelector("[data-exit]");
  const exitDialog = document.getElementById("rm-exit-dialog");
  const exitYes = document.getElementById("rm-exit-yes") || document.querySelector("[data-exit-yes]");
  const exitNo = document.querySelector("[data-exit-no]");

  const searchForm = root.querySelector("[data-search-form]");
  const searchText = root.querySelector("[data-search-text]");
  const searchHint = root.querySelector("[data-search-hint]");

  const csrfToken = (root.querySelector("input[name=csrfmiddlewaretoken]") || {}).value || "";

  // Editable fields: key in the row data -> { decimals: null for text fields, or
  // number of decimal places for numeric ones; uppercase: true for text fields that
  // should be forced uppercase as you type.
  const FIELDS = {
    rate: { decimals: 4 },
    opening_stock: { decimals: 3 },
    current_stock: { decimals: 0 },
    gst_percent: { decimals: 2 },
    location: { decimals: null, uppercase: true },
  };

  let rows = [];
  const original = new Map(); // code -> { rate, opening_stock, current_stock, gst_percent, location }
  const changed = new Map(); // code -> { field: newValue, ... } (only edited fields)

  function readInitial() {
    const el = document.getElementById("rm-initial-data");
    if (!el) return { rows: [], can_edit: canEdit };
    try {
      return JSON.parse(el.textContent);
    } catch (err) {
      return { rows: [], can_edit: canEdit };
    }
  }

  function showToast(message, kind) {
    if (!toast) return;
    toast.textContent = message;
    toast.className = "toast" + (kind ? " toast--" + kind : "") + " is-visible";
    window.clearTimeout(showToast._t);
    showToast._t = window.setTimeout(function () {
      toast.classList.remove("is-visible");
    }, 3200);
  }

  function fmt(value, decimals) {
    const num = Number(value);
    return Number.isFinite(num) ? num.toFixed(decimals) : Number(0).toFixed(decimals);
  }

  function rowValue(row, field) {
    const edits = changed.get(row.code);
    if (edits && Object.prototype.hasOwnProperty.call(edits, field)) return edits[field];
    return row[field];
  }

  function updateChangesLabel() {
    const n = changed.size;
    changesEl.textContent = n === 0 ? "" : n + " row" + (n === 1 ? "" : "s") + " changed";
  }

  function render(list) {
    tbody.innerHTML = "";
    emptyMsg.hidden = list.length !== 0;
    list.forEach(function (row) {
      const tr = document.createElement("tr");
      tr.dataset.code = row.code;
      if (changed.has(row.code)) tr.classList.add("is-changed");

      tr.innerHTML =
        "<td>" + escapeHtml(row.code) + "</td>" +
        "<td>" + escapeHtml(row.name) + "</td>" +
        "<td class=\"rm-cell\" data-cell=\"rate\"></td>" +
        "<td class=\"rm-cell num\" data-cell=\"opening_stock\"></td>" +
        "<td class=\"rm-cell num\" data-cell=\"current_stock\"></td>" +
        "<td class=\"rm-cell num\" data-cell=\"gst_percent\"></td>" +
        "<td class=\"rm-cell\" data-cell=\"location\"></td>";

      Object.keys(FIELDS).forEach(function (field) {
        const spec = FIELDS[field];
        const cell = tr.querySelector('[data-cell="' + field + '"]');
        const input = document.createElement("input");
        input.type = "text";
        input.inputMode = spec.decimals === null ? "text" : "decimal";
        input.className = "rm-rate";
        input.value = rowValue(row, field);
        input.dataset.code = row.code;
        input.dataset.field = field;
        if (!canEdit) input.readOnly = true;
        cell.appendChild(input);
      });

      tbody.appendChild(tr);
    });
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function parseNumeric(text) {
    const cleaned = String(text || "").trim().replace(/,/g, "");
    if (cleaned === "") return null;
    const num = Number(cleaned);
    return Number.isFinite(num) ? num : NaN;
  }

  function onFieldInput(event) {
    const input = event.target;
    if (!input.classList.contains("rm-rate")) return;
    const code = input.dataset.code;
    const field = input.dataset.field;
    const spec = FIELDS[field];
    const row = rows.find(function (r) { return r.code === code; });
    if (!row) return;

    let raw = input.value;
    let invalid = false;

    if (spec.uppercase && raw !== raw.toUpperCase()) {
      const pos = input.selectionStart;
      raw = input.value = raw.toUpperCase();
      input.setSelectionRange(pos, pos);
    }

    if (spec.decimals === null) {
      invalid = false; // text field (location): nothing to validate client-side
    } else {
      const parsed = parseNumeric(raw);
      invalid = raw.trim() === "" || Number.isNaN(parsed) || parsed < 0
        || (field === "gst_percent" && parsed > 100);
    }
    input.classList.toggle("is-invalid", invalid);

    const originalRow = original.get(code) || {};
    const isTextSame = spec.decimals === null && raw === (originalRow[field] || "");
    const isNumSame = spec.decimals !== null && !invalid && fmt(parseNumeric(raw), spec.decimals) === fmt(originalRow[field], spec.decimals);

    let edits = changed.get(code);
    if (invalid || !(isTextSame || isNumSame)) {
      if (!edits) { edits = {}; changed.set(code, edits); }
      edits[field] = raw;
    } else if (edits) {
      delete edits[field];
      if (Object.keys(edits).length === 0) changed.delete(code);
    }

    const tr = input.closest("tr");
    if (tr) tr.classList.toggle("is-changed", changed.has(code));
    updateChangesLabel();
  }

  function loadRows() {
    return fetch(dataUrl, { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        rows = data.rows || [];
        original.clear();
        rows.forEach(function (row) {
          original.set(row.code, {
            rate: row.rate, opening_stock: row.opening_stock, current_stock: row.current_stock,
            gst_percent: row.gst_percent, location: row.location,
          });
        });
        changed.clear();
        updateChangesLabel();
        applySearch();
      });
  }

  function applySearch() {
    const mode = (searchForm.querySelector("input[name=mode]:checked") || {}).value || "all";
    const text = (searchText.value || "").trim().toLowerCase();

    if (mode === "selective" && text) {
      const filtered = rows.filter(function (row) {
        return row.code.toLowerCase().indexOf(text) !== -1 || row.name.toLowerCase().indexOf(text) !== -1;
      });
      render(filtered);
      searchHint.textContent = filtered.length + " match" + (filtered.length === 1 ? "" : "es");
      return;
    }

    render(rows);

    if (mode === "all" && text) {
      const match = rows.find(function (row) {
        return row.code.toLowerCase().indexOf(text) !== -1 || row.name.toLowerCase().indexOf(text) !== -1;
      });
      if (match) {
        const tr = tbody.querySelector('tr[data-code="' + cssEscape(match.code) + '"]');
        if (tr) {
          tr.classList.add("is-selected");
          tr.scrollIntoView({ block: "center" });
        }
        searchHint.textContent = "";
      } else {
        searchHint.textContent = "No match found";
      }
    } else {
      searchHint.textContent = "";
    }
  }

  function cssEscape(value) {
    return window.CSS && CSS.escape ? CSS.escape(value) : String(value).replace(/["\\]/g, "\\$&");
  }

  function hasUnsaved() {
    return changed.size > 0;
  }

  function doExit() {
    window.location.href = exitUrl;
  }

  function onExitClick() {
    doExit();
  }

  function onConfirmClick() {
    if (!canEdit) return;
    if (changed.size === 0) {
      showToast("No changes to save.");
      return;
    }

    const invalidInput = tbody.querySelector(".rm-rate.is-invalid");
    if (invalidInput) {
      showToast("Fix the highlighted value(s) before saving.", "error");
      invalidInput.focus();
      return;
    }

    const payload = [];
    changed.forEach(function (edits, code) {
      payload.push(Object.assign({ code: code }, edits));
    });

    confirmBtn.disabled = true;
    fetch(saveUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ changes: payload }),
    })
      .then(function (resp) {
        return resp.json().then(function (data) { return { status: resp.status, data: data }; });
      })
      .then(function (result) {
        if (result.status >= 400) {
          const errors = result.data.errors || {};
          const firstKey = Object.keys(errors)[0];
          const detail = firstKey ? errors[firstKey] : result.data.message;
          showToast(detail || result.data.message || "Could not save changes.", "error");
          return;
        }
        rows = result.data.rows || rows;
        original.clear();
        rows.forEach(function (row) {
          original.set(row.code, {
            rate: row.rate, opening_stock: row.opening_stock, current_stock: row.current_stock,
            gst_percent: row.gst_percent, location: row.location,
          });
        });
        changed.clear();
        updateChangesLabel();
        applySearch();
        showToast(result.data.message || "Saved.", "success");
      })
      .catch(function () {
        showToast("Could not reach the server. Nothing was saved.", "error");
      })
      .finally(function () {
        confirmBtn.disabled = !canEdit;
      });
  }

  tbody.addEventListener("input", onFieldInput);

  tbody.addEventListener("focusin", function (event) {
    const input = event.target;
    if (!input.classList || !input.classList.contains("rm-rate") || input.readOnly) return;
    const spec = FIELDS[input.dataset.field];
    if (spec && spec.decimals !== null && parseNumeric(input.value) === 0) input.value = "";
  });

  tbody.addEventListener("focusout", function (event) {
    const input = event.target;
    if (!input.classList || !input.classList.contains("rm-rate") || input.readOnly) return;
    const spec = FIELDS[input.dataset.field];
    if (spec && spec.decimals !== null && input.value.trim() === "") {
      input.value = Number(0).toFixed(spec.decimals);
      onFieldInput(event);
    }
  });
  if (canEdit) confirmBtn.addEventListener("click", onConfirmClick);
  exitBtn.addEventListener("click", onExitClick);
  if (exitYes) exitYes.addEventListener("click", doExit);
  if (exitNo) exitNo.addEventListener("click", function () { exitDialog.close(); });
  searchForm.addEventListener("submit", function (e) { e.preventDefault(); applySearch(); });
  searchForm.addEventListener("change", applySearch);
  searchText.addEventListener("input", applySearch);

  const initial = readInitial();
  rows = initial.rows || [];
  rows.forEach(function (row) {
    original.set(row.code, {
      rate: row.rate, opening_stock: row.opening_stock, current_stock: row.current_stock,
      gst_percent: row.gst_percent, location: row.location,
    });
  });
  render(rows);
  updateChangesLabel();
})();
