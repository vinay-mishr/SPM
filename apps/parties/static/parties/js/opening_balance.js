/* Opening Balance Master — spreadsheet-like grid of party opening balances.
 * - Debit / Credit cells are editable (when the user has permission).
 *   Typing a Debit clears the Credit and vice versa (the server enforces this too).
 * - Enter moves to the next amount cell, Tab works as usual, Esc undoes the current edit.
 * - Totals are for ALL parties and update as you type.
 * - Search: All = every party, jumps to the first match; Selective = only matching parties.
 * - CONFIRM sends only the changed rows; EXIT asks before discarding unsaved changes.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-opening-balance]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var gridWrap = root.querySelector("[data-grid-wrap]");
  var totalDebit = root.querySelector("[data-total-debit]");
  var totalCredit = root.querySelector("[data-total-credit]");
  var changesNote = root.querySelector("[data-changes]");
  var confirmBtn = root.querySelector("[data-confirm]");
  var searchForm = root.querySelector("[data-search-form]");
  var searchText = root.querySelector("[data-search-text]");
  var searchHint = root.querySelector("[data-search-hint]");
  var exitDialog = document.getElementById("ob-exit-dialog");
  var toast = document.querySelector("[data-toast]");
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;

  var initial = JSON.parse(document.getElementById("ob-initial-data").textContent);
  var canEdit = initial.can_edit;
  var AMOUNT_RE = /^\d{1,11}(\.\d{1,2})?$/;
  var fmt = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  // rows: [{sno, code, id, name, gst_no, debit, credit}] with saved values as strings "0.00".
  var rows = [];
  var byId = {};
  var saving = false;
  var leaving = false;

  /* --- Helpers ------------------------------------------------------------------- */

  function toCents(text) {
    var t = String(text || "").trim();
    if (t === "") return 0;
    if (!AMOUNT_RE.test(t)) return NaN;
    var parts = t.split(".");
    return Number(parts[0]) * 100 + Number(((parts[1] || "") + "00").slice(0, 2));
  }

  function centsText(cents) {
    return (Math.floor(cents / 100)) + "." + String(cents % 100).padStart(2, "0");
  }

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 4000);
  }

  function inputsOf(tr) {
    return { debit: tr.querySelector('[data-kind="debit"]'), credit: tr.querySelector('[data-kind="credit"]') };
  }

  /* --- Rendering ------------------------------------------------------------------ */

  function cell(text, className) {
    var td = document.createElement("td");
    td.textContent = text;
    if (className) td.className = className;
    return td;
  }

  function amountCell(row, kind) {
    var td = document.createElement("td");
    td.className = "ob-cell";
    var input = document.createElement("input");
    input.className = "ob-amount";
    input.type = "text";
    input.inputMode = "decimal";
    input.autocomplete = "off";
    input.dataset.kind = kind;
    input.setAttribute("aria-label", kind + " for " + row.code);
    input.readOnly = !canEdit;
    var cents = toCents(row[kind]);
    // Like the old grid: a credit balance leaves Debit blank; otherwise Credit is blank.
    var otherCents = toCents(row[kind === "debit" ? "credit" : "debit"]);
    input.value = cents ? centsText(cents) : (kind === "debit" && !otherCents ? "0.00" : "");
    td.appendChild(input);
    return td;
  }

  function render() {
    tbody.textContent = "";
    byId = {};
    var fragment = document.createDocumentFragment();
    rows.forEach(function (row) {
      var tr = document.createElement("tr");
      tr.dataset.id = row.id;
      tr.append(
        cell(row.sno, "num"),
        cell(row.code, "master-table__code"),
        cell(row.name),
        amountCell(row, "debit"),
        amountCell(row, "credit"),
        cell(row.gst_no)
      );
      byId[row.id] = { row: row, tr: tr };
      fragment.appendChild(tr);
    });
    tbody.appendChild(fragment);
    applySearch(false);
    updateTotals();
  }

  /* --- Totals & change tracking ------------------------------------------------------------ */

  function currentCents(tr) {
    var inputs = inputsOf(tr);
    return { debit: toCents(inputs.debit.value), credit: toCents(inputs.credit.value) };
  }

  function changedRows() {
    var list = [];
    rows.forEach(function (row) {
      var tr = byId[row.id].tr;
      var now = currentCents(tr);
      if (now.debit !== toCents(row.debit) || now.credit !== toCents(row.credit)) {
        list.push({ row: row, tr: tr, now: now });
      }
    });
    return list;
  }

  function updateTotals() {
    var debit = 0, credit = 0, invalid = false;
    rows.forEach(function (row) {
      var now = currentCents(byId[row.id].tr);
      if (isNaN(now.debit) || isNaN(now.credit)) { invalid = true; return; }
      debit += now.debit;
      credit += now.credit;
    });
    totalDebit.textContent = fmt.format(debit / 100);
    totalCredit.textContent = fmt.format(credit / 100);
    var changes = changedRows();
    changes.forEach(function (c) { c.tr.classList.add("is-changed"); });
    tbody.querySelectorAll("tr.is-changed").forEach(function (tr) {
      if (!changes.some(function (c) { return c.tr === tr; })) tr.classList.remove("is-changed");
    });
    changesNote.textContent = changes.length ? changes.length + " unsaved change" + (changes.length === 1 ? "" : "s") : "";
    if (invalid) changesNote.textContent += (changes.length ? " · " : "") + "fix the red cells";
    if (canEdit) confirmBtn.disabled = saving;
  }

  /* --- Editing ----------------------------------------------------------------------------- */

  function validateInput(input) {
    var ok = !isNaN(toCents(input.value));
    input.classList.toggle("is-invalid", !ok);
    input.title = ok ? "" : "Enter an amount like 1000.50 (no letters, no minus sign).";
    return ok;
  }

  tbody.addEventListener("focusin", function (event) {
    var input = event.target.closest(".ob-amount");
    if (!input) return;
    input.dataset.before = input.value;
    selectRow(input.closest("tr"));
    if (!input.readOnly) {
      if (input.value === "0.00") input.value = "";
      else input.select();
    }
  });

  tbody.addEventListener("input", function (event) {
    var input = event.target.closest(".ob-amount");
    if (!input || input.readOnly) return;
    var inputs = inputsOf(input.closest("tr"));
    var other = input.dataset.kind === "debit" ? inputs.credit : inputs.debit;
    // Debit and Credit are mutually exclusive: a value in one clears the other.
    if (toCents(input.value) > 0 && other.value !== "") {
      other.value = "";
      other.classList.remove("is-invalid");
    }
    validateInput(input);
    updateTotals();
  });

  tbody.addEventListener("focusout", function (event) {
    var input = event.target.closest(".ob-amount");
    if (!input || input.readOnly || !validateInput(input)) return;
    var cents = toCents(input.value);
    var creditCents = toCents(inputsOf(input.closest("tr")).credit.value);
    // Show amounts with 2 decimals; a zero Debit shows 0.00 unless the row has a Credit.
    var showZero = input.dataset.kind === "debit" && !creditCents;
    input.value = cents || showZero ? centsText(cents) : "";
  });

  function amountInputs() {
    return Array.prototype.filter.call(tbody.querySelectorAll(".ob-amount"), function (el) {
      return !el.closest("tr").hidden;
    });
  }

  tbody.addEventListener("keydown", function (event) {
    var input = event.target.closest(".ob-amount");
    if (!input) return;
    if (event.key === "Enter") {
      event.preventDefault();
      var list = amountInputs();
      var next = list[list.indexOf(input) + 1];
      if (next) next.focus();
    } else if (event.key === "Escape") {
      event.preventDefault();
      input.value = input.dataset.before || "";
      validateInput(input);
      updateTotals();
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      var tr = input.closest("tr");
      var target = event.key === "ArrowDown" ? tr.nextElementSibling : tr.previousElementSibling;
      while (target && target.hidden) {
        target = event.key === "ArrowDown" ? target.nextElementSibling : target.previousElementSibling;
      }
      if (target) target.querySelector('[data-kind="' + input.dataset.kind + '"]').focus();
    }
  });

  function selectRow(tr) {
    var current = tbody.querySelector("tr.is-selected");
    if (current && current !== tr) current.classList.remove("is-selected");
    if (tr) tr.classList.add("is-selected");
  }

  tbody.addEventListener("click", function (event) {
    var tr = event.target.closest("tr");
    if (tr) selectRow(tr);
  });

  /* --- Search ------------------------------------------------------------------------------ */

  function mode() {
    return root.querySelector('input[name="mode"]:checked').value;
  }

  function matches(row, text) {
    return (row.code + " " + row.name + " " + row.gst_no).toLowerCase().indexOf(text) > -1;
  }

  function applySearch(jump) {
    var text = searchText.value.trim().toLowerCase();
    var selective = mode() === "selective" && text;
    var shown = 0, firstMatch = null;
    rows.forEach(function (row) {
      var tr = byId[row.id].tr;
      var hit = text && matches(row, text);
      tr.hidden = selective ? !hit : false;
      if (!tr.hidden) shown += 1;
      if (hit && !firstMatch) firstMatch = tr;
    });
    emptyNote.hidden = shown > 0;
    if (!text) {
      searchHint.textContent = "";
    } else if (selective) {
      searchHint.textContent = shown + " of " + rows.length + " parties";
    } else {
      searchHint.textContent = firstMatch ? "Found: row " + firstMatch.firstChild.textContent : "No records found";
      if (jump && firstMatch) {
        selectRow(firstMatch);
        firstMatch.scrollIntoView({ block: "center" });
      }
    }
  }

  searchForm.addEventListener("submit", function (event) {
    event.preventDefault();
    applySearch(true);
  });
  searchText.addEventListener("input", function () { applySearch(true); });
  root.querySelectorAll('input[name="mode"]').forEach(function (radio) {
    radio.addEventListener("change", function () { applySearch(true); });
  });

  /* --- Save --------------------------------------------------------------------------------- */

  function confirmSave() {
    if (!canEdit || saving) return;
    var invalid = tbody.querySelector(".ob-amount.is-invalid");
    if (invalid) {
      invalid.closest("tr").hidden = false;
      invalid.focus();
      showToast("Please correct the amounts marked in red.", "error");
      return;
    }
    var changes = changedRows();
    if (!changes.length) {
      showToast("No changes to save.");
      return;
    }
    var payload = changes.map(function (c) {
      return { code: c.row.id, debit: centsText(c.now.debit), credit: centsText(c.now.credit) };
    });

    saving = true;
    confirmBtn.disabled = true;
    fetch(root.dataset.saveUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin",
      body: JSON.stringify({ changes: payload })
    })
      .then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (body) {
          return { ok: response.ok, status: response.status, body: body };
        });
      })
      .then(function (result) {
        if (result.ok) {
          rows = result.body.rows;
          render();
          showToast(result.body.message);
          return;
        }
        var errors = result.body.errors || {};
        Object.keys(errors).forEach(function (code) {
          var entry = byId[code];
          if (!entry) return;
          var inputs = inputsOf(entry.tr);
          inputs.debit.classList.add("is-invalid");
          inputs.credit.classList.add("is-invalid");
          inputs.debit.title = errors[code];
        });
        var first = Object.keys(errors)[0];
        showToast((first && errors[first] ? errors[first] : result.body.message) || "Could not save (error " + result.status + ").", "error");
      })
      .catch(function () {
        showToast("Could not reach the server. Nothing was saved.", "error");
      })
      .finally(function () {
        saving = false;
        updateTotals();
      });
  }

  if (canEdit) confirmBtn.addEventListener("click", confirmSave);

  /* --- Exit ---------------------------------------------------------------------------------- */

  function leave() {
    leaving = true;
    window.location.href = root.dataset.exitUrl;
  }

  root.querySelector("[data-exit]").addEventListener("click", leave);
  exitDialog.querySelector("[data-exit-yes]").addEventListener("click", leave);
  exitDialog.querySelector("[data-exit-no]").addEventListener("click", function () { exitDialog.close(); });

  window.addEventListener("beforeunload", function (event) {
    if (!leaving && changedRows().length) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  rows = initial.rows;
  render();
  gridWrap.scrollTop = 0;
})();
