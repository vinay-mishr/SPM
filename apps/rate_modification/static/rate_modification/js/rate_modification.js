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

  let rows = [];
  const original = new Map(); // code -> original rate string
  const changed = new Map(); // code -> new rate string

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

  function fmt(value) {
    const num = Number(value);
    return Number.isFinite(num) ? num.toFixed(2) : "0.00";
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

      const rateValue = changed.has(row.code) ? changed.get(row.code) : row.rate;

      tr.innerHTML =
        "<td>" + escapeHtml(row.code) + "</td>" +
        "<td>" + escapeHtml(row.name) + "</td>" +
        "<td class=\"rm-cell\"></td>" +
        "<td class=\"num\">" + escapeHtml(fmt(row.opening_stock)) + "</td>" +
        "<td class=\"num\">" + escapeHtml(fmt(row.current_stock)) + "</td>" +
        "<td class=\"num\">" + escapeHtml(fmt(row.gst_percent)) + "</td>" +
        "<td>" + escapeHtml(row.location) + "</td>";

      const cell = tr.querySelector(".rm-cell");
      const input = document.createElement("input");
      input.type = "text";
      input.inputMode = "decimal";
      input.className = "rm-rate";
      input.value = rateValue;
      input.dataset.code = row.code;
      if (!canEdit) input.readOnly = true;
      cell.appendChild(input);

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

  function onRateInput(event) {
    const input = event.target;
    if (!input.classList.contains("rm-rate")) return;
    const code = input.dataset.code;
    const row = rows.find(function (r) { return r.code === code; });
    if (!row) return;

    const raw = input.value;
    const parsed = parseNumeric(raw);
    const invalid = raw.trim() === "" || Number.isNaN(parsed) || parsed < 0;
    input.classList.toggle("is-invalid", invalid);

    const original_ = original.get(code);
    if (invalid) {
      // Keep tracked as changed only if it already differs textually; still invalid blocks save.
      changed.set(code, raw);
    } else if (fmt(parsed) === fmt(original_)) {
      changed.delete(code);
    } else {
      changed.set(code, raw);
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
        rows.forEach(function (row) { original.set(row.code, row.rate); });
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
      showToast("Fix the highlighted rate(s) before saving.", "error");
      invalidInput.focus();
      return;
    }

    const payload = [];
    changed.forEach(function (rate, code) {
      payload.push({ code: code, rate: rate });
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
        rows.forEach(function (row) { original.set(row.code, row.rate); });
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

  tbody.addEventListener("input", onRateInput);

  tbody.addEventListener("focusin", function (event) {
    const input = event.target;
    if (!input.classList || !input.classList.contains("rm-rate") || input.readOnly) return;
    if (parseNumeric(input.value) === 0) input.value = "";
  });

  tbody.addEventListener("focusout", function (event) {
    const input = event.target;
    if (!input.classList || !input.classList.contains("rm-rate") || input.readOnly) return;
    if (input.value.trim() === "") { input.value = "0.00"; onRateInput(event); }
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
  rows.forEach(function (row) { original.set(row.code, row.rate); });
  render(rows);
  updateChangesLabel();
})();
