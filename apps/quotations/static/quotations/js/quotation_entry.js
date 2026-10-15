/*
 * Quotation entry (add / modify / view).
 *
 * Amounts are calculated here only for instant feedback; the server (apps/quotations/calc.py)
 * recomputes everything on save. calcLine() mirrors calc.calc_line exactly, using integer
 * (BigInt) arithmetic with ROUND_HALF_UP so the screen and the saved quotation agree to the paisa.
 */
(function () {
  "use strict";

  // --- exact decimal helpers (values are non-negative) ---------------------------------
  var QTY_RE = /^\d{1,7}(\.\d{0,3})?$/;
  var MONEY_RE = /^\d{1,8}(\.\d{0,2})?$/;
  var PCT_RE = /^\d{1,3}(\.\d{0,2})?$/;

  function scaled(text, places) {
    var s = String(text == null ? "" : text).trim().replace(/,/g, "");
    if (s === "") s = "0";
    if (!/^\d+(\.\d*)?$/.test(s)) return null;
    var parts = s.split(".");
    var frac = (parts[1] || "").padEnd(places, "0");
    if (frac.length > places) return null;
    return BigInt(parts[0]) * (BigInt(10) ** BigInt(places)) + BigInt(frac || "0");
  }

  function roundDiv(n, d) { // half-up division for n >= 0, d > 0
    return (n * 2n + d) / (d * 2n);
  }

  function fmt(value, places) {
    places = places === undefined ? 2 : places;
    var base = BigInt(10) ** BigInt(places);
    var whole = value / base;
    var frac = (value % base).toString().padStart(places, "0");
    return places ? whole.toString() + "." + frac : whole.toString();
  }

  function fmtGrouped(cents) {
    var s = fmt(cents, 2);
    var parts = s.split(".");
    return parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",") + "." + parts[1];
  }

  /* Same rules as calc.calc_line: % wins when > 0, otherwise the entered amount (and the % is derived). */
  function calcLine(line, gstOn) {
    var qty = scaled(line.qty, 3), rate = scaled(line.rate, 2);
    var dp = scaled(line.disc_pct, 2), da = scaled(line.disc_amt, 2), gp = scaled(line.gst_pct, 2);
    if ([qty, rate, dp, da, gp].some(function (v) { return v === null; })) return null;
    var gross = roundDiv(qty * rate, 1000n);
    var discount = 0n, pct = 0n;
    if (dp > 0n) { discount = roundDiv(gross * dp, 10000n); pct = dp; }
    else if (da > 0n) { discount = da; pct = gross > 0n ? roundDiv(da * 10000n, gross) : 0n; }
    var taxable = gross - discount;
    var gst = gstOn ? roundDiv(taxable * gp, 10000n) : 0n;
    return { gross: gross, discount: discount, pct: pct, taxable: taxable, gst: gst, total: taxable + gst };
  }

  // --- page -----------------------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", function () {
    var form = document.querySelector("[data-quot-form]");
    var configEl = document.getElementById("quot-config");
    if (!form || !configEl) return;
    var config = JSON.parse(configEl.textContent);
    var q = config.quotation;
    var mode = config.mode; // add | edit | view
    var readOnly = mode === "view";
    var token = config.token;
    var csrf = form.querySelector("input[name=csrfmiddlewaretoken]").value;
    var items = (q.items || []).map(function (l) {
      return {
        item_code: l.item_code, item_name: l.item_name, unit: l.unit, currency: l.currency,
        qty: l.qty, rate: l.rate, disc_pct: l.disc_pct, disc_amt: l.disc_amt, gst_pct: l.gst_pct,
        particular: l.particular || "", held: false,
      };
    });
    var editingIndex = -1;
    var selectedIndex = -1;
    var dirty = false;
    var busy = false;
    var leaving = false;

    var $ = function (sel) { return form.querySelector(sel); };
    var field = function (name) { return form.querySelector('[data-f="' + name + '"]'); };
    var alertBox = $("[data-alert]");
    var toast = document.querySelector("[data-toast]");
    var rowsBody = $("[data-item-rows]");
    var partyInput = $("[data-party-search]");
    var itemInput = $("[data-item-search]");
    var ie = {};
    form.querySelectorAll("[data-ie]").forEach(function (el) { ie[el.dataset.ie] = el; });
    var currentItem = null; // {code, name, unit, gst_percent} picked in the entry row

    // --- fill the form -------------------------------------------------------------------
    var D = window.DateMask || { toDisplay: function (v) { return v; }, toIso: function (v) { return v; } };
    field("quot_no").value = q.quot_no || "";
    field("quot_date").value = D.toDisplay(q.quot_date);
    field("ref_no").value = q.ref_no || "";
    field("ref_date").value = D.toDisplay(q.ref_date);
    field("gst_applicable").value = q.gst_applicable === "N" ? "N" : "Y";
    field("party_code").value = q.party_code || "";
    partyInput.value = q.party_name || "";
    field("city").value = q.city || "";
    field("phone").value = q.phone || "";
    form.querySelectorAll("[data-kind]").forEach(function (el) { el.value = (q.kind_attention || [])[+el.dataset.kind] || ""; });
    field("remarks").value = q.remarks || "";
    form.querySelectorAll("[data-term]").forEach(function (el) { el.value = (q.terms || [])[+el.dataset.term] || ""; });
    form.querySelectorAll("[data-bank]").forEach(function (el) { el.value = (q.bank || [])[+el.dataset.bank] || ""; });
    showPartyCode();

    (config.currencies || []).forEach(function (c) {
      var opt = document.createElement("option");
      opt.value = c; opt.textContent = c;
      ie.currency.appendChild(opt);
    });
    items.forEach(function (l) { ensureCurrency(l.currency); });
    ie.currency.value = config.default_currency;

    if (mode !== "add") field("quot_no").readOnly = true;
    if (q.confirmed) {
      var note = $("[data-confirmed-note]");
      note.textContent = "Confirmed" + (q.confirmed_by ? " by " + q.confirmed_by : "") + (q.confirmed_at ? " on " + q.confirmed_at : "") + ".";
      note.hidden = false;
    }
    if (readOnly) {
      form.querySelectorAll("input, textarea").forEach(function (el) { if (el.type !== "hidden") el.readOnly = true; });
      form.querySelectorAll("select").forEach(function (el) { el.disabled = true; });
    }
    if (!config.can_confirm) {
      var cb = $("[data-confirm]");
      if (cb) cb.disabled = true;
    }

    function ensureCurrency(code) {
      if (!code) return;
      var exists = Array.prototype.some.call(ie.currency.options, function (o) { return o.value === code; });
      if (!exists) {
        var opt = document.createElement("option");
        opt.value = code; opt.textContent = code;
        ie.currency.appendChild(opt);
      }
    }

    function showPartyCode() {
      var code = field("party_code").value;
      $("[data-party-code-label]").textContent = code ? "Party code: " + code : (partyInput.value ? "Not selected from the Customer Master yet." : "");
    }

    // --- messages ------------------------------------------------------------------------
    function showAlert(message, kind) {
      alertBox.textContent = message;
      alertBox.className = "alert alert--" + (kind || "error");
      alertBox.hidden = !message;
      if (message) alertBox.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    function showToast(message, kind) {
      if (!toast) return;
      toast.textContent = message;
      toast.className = "toast toast--" + (kind || "success") + " is-visible";
      clearTimeout(showToast.timer);
      showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
    }

    function clearErrors() {
      form.querySelectorAll("[data-error-for]").forEach(function (el) { el.textContent = ""; });
      form.querySelectorAll(".is-invalid").forEach(function (el) { el.classList.remove("is-invalid"); });
    }

    function showErrors(errors) {
      var first = null;
      Object.keys(errors || {}).forEach(function (key) {
        var holder = form.querySelector('[data-error-for="' + key + '"]');
        if (holder) holder.textContent = errors[key];
        var wrap = form.querySelector('[data-field-wrap="' + key + '"]');
        if (wrap) {
          wrap.classList.add("is-invalid");
          if (!first) first = wrap.querySelector("input:not([type=hidden]), select, textarea");
        }
      });
      if (first && !first.readOnly) first.focus();
    }

    // --- totals ---------------------------------------------------------------------------
    function gstOn() { return field("gst_applicable").value !== "N"; }

    function recalc() {
      var t = { total: 0n, discount: 0n, gst: 0n };
      var currencies = {};
      items.forEach(function (l) {
        if (l.held) return;
        var c = calcLine(l, gstOn());
        if (!c) return;
        t.total += c.gross; t.discount += c.discount; t.gst += c.gst;
        currencies[l.currency] = true;
      });
      $('[data-total="total"]').textContent = fmtGrouped(t.total);
      $('[data-total="discount"]').textContent = fmtGrouped(t.discount);
      $('[data-total="gst"]').textContent = fmtGrouped(t.gst);
      $('[data-total="net"]').textContent = fmtGrouped(t.total - t.discount + t.gst);
      var list = Object.keys(currencies);
      var note = $("[data-currency-note]");
      note.hidden = list.length < 2;
      note.textContent = list.length > 1 ? "Items use more than one currency (" + list.join(", ") + "); totals simply add the figures." : "";
    }

    // --- grid -----------------------------------------------------------------------------
    function cell(text, cls) {
      var td = document.createElement("td");
      if (cls) td.className = cls;
      td.textContent = text;
      return td;
    }

    function renderRows(focusIndex) {
      rowsBody.innerHTML = "";
      items.forEach(function (l, i) {
        var c = calcLine(l, gstOn()) || { gross: 0n, discount: 0n, gst: 0n };
        var tr = document.createElement("tr");
        var classes = [];
        if (i === editingIndex) classes.push("is-editing");
        if (i === selectedIndex) classes.push("is-selected");
        if (l.held) classes.push("is-held");
        tr.className = classes.join(" ");
        tr.dataset.index = i;
        if (!readOnly) tr.tabIndex = 0;
        tr.appendChild(cell(String(i + 1), "num"));
        tr.appendChild(cell(l.item_code));
        var desc = cell(l.item_name);
        if (l.particular) {
          var p = document.createElement("span");
          p.className = "quot-grid__particular";
          p.textContent = l.particular;
          desc.appendChild(p);
        }
        tr.appendChild(desc);
        tr.appendChild(cell(l.currency));
        tr.appendChild(cell(l.qty, "num"));
        tr.appendChild(cell(fmtGrouped(scaled(l.rate, 2) || 0n), "num"));
        tr.appendChild(cell(fmtGrouped(c.gross), "num"));
        tr.appendChild(cell(c.discount > 0n ? fmt(c.pct) + "%" : "", "num"));
        tr.appendChild(cell(l.gst_pct, "num"));
        if (!readOnly) {
          tr.addEventListener("click", function () { selectedIndex = i; renderRows(i); });
          tr.addEventListener("dblclick", function () { if (!l.held) startEdit(i); });
        }
        rowsBody.appendChild(tr);
      });
      $("[data-items-empty]").hidden = items.length > 0;
      if (focusIndex != null) {
        var toFocus = rowsBody.querySelector('tr[data-index="' + focusIndex + '"]');
        if (toFocus) toFocus.focus();
      }
      recalc();
    }

    function toggleHeld(index) {
      var l = items[index];
      if (!l) return;
      l.held = !l.held;
      if (l.held && editingIndex === index) resetEntry();
      markDirty();
      renderRows(index);
    }

    if (!readOnly) {
      rowsBody.addEventListener("keydown", function (event) {
        if (event.key !== " " && event.key !== "Spacebar") return;
        var tr = event.target.closest("tr[data-index]");
        if (!tr) return;
        event.preventDefault();
        toggleHeld(Number(tr.dataset.index));
      });
    }

    // --- item entry row -------------------------------------------------------------------
    function entryLine() {
      return {
        item_code: currentItem ? currentItem.code : "",
        item_name: currentItem ? currentItem.name : "",
        unit: currentItem ? currentItem.unit : "",
        currency: ie.currency.value,
        qty: ie.qty.value.trim(), rate: ie.rate.value.trim(),
        disc_pct: ie.disc_pct.value.trim(), disc_amt: ie.disc_amt.value.trim(),
        gst_pct: ie.gst_pct.value.trim(),
        particular: ie.particular.value.replace(/\s+$/, ""),
      };
    }

    function updateEntryAmount() {
      var c = calcLine(entryLine(), gstOn());
      $("[data-ie-amount]").textContent = c ? fmtGrouped(c.gross) : "—";
      return c;
    }

    function setItem(item) {
      currentItem = item;
      itemInput.value = item ? item.name : "";
      $("[data-item-label]").textContent = item ? "Code " + item.code + (item.unit ? " · Unit " + item.unit : "") : "";
    }

    function resetEntry() {
      editingIndex = -1;
      setItem(null);
      ie.currency.value = config.default_currency;
      ie.qty.value = "1"; ie.rate.value = "0.00"; ie.disc_pct.value = "0.00"; ie.disc_amt.value = "0.00";
      ie.gst_pct.value = "0.00"; ie.particular.value = "";
      $("[data-item-cancel]").hidden = true;
      $("[data-item-ok]").textContent = "OK";
      $("[data-item-error]").textContent = "";
      updateEntryAmount();
    }

    function startEdit(index) {
      var l = items[index];
      editingIndex = index;
      selectedIndex = index;
      setItem({ code: l.item_code, name: l.item_name, unit: l.unit, gst_percent: l.gst_pct });
      ensureCurrency(l.currency);
      ie.currency.value = l.currency;
      ie.qty.value = l.qty; ie.rate.value = l.rate;
      var c = calcLine(l, true);
      ie.disc_pct.value = (scaled(l.disc_pct, 2) || 0n) > 0n ? l.disc_pct : "0.00";
      ie.disc_amt.value = c ? fmt(c.discount) : l.disc_amt;
      ie.gst_pct.value = l.gst_pct; ie.particular.value = l.particular;
      $("[data-item-cancel]").hidden = false;
      $("[data-item-ok]").textContent = "OK";
      $("[data-item-error]").textContent = "";
      updateEntryAmount();
      renderRows();
      itemInput.focus();
      $("[data-item-entry]").scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    function entryError(message, el) {
      $("[data-item-error]").textContent = message;
      if (el) el.focus();
      return false;
    }

    function commitEntry() {
      var l = entryLine();
      if (!currentItem) return entryError("Select an item from the Item Master (type and press Enter, or click Find).", itemInput);
      if (!QTY_RE.test(l.qty) || !(scaled(l.qty, 3) > 0n)) return entryError("Quantity must be more than 0, with up to 3 decimals.", ie.qty);
      if (!MONEY_RE.test(l.rate)) return entryError("Rate must be a number with up to 2 decimals.", ie.rate);
      if (!PCT_RE.test(l.disc_pct || "0") || scaled(l.disc_pct, 2) > 10000n) return entryError("Discount % must be between 0 and 100.", ie.disc_pct);
      if (!MONEY_RE.test(l.disc_amt || "0")) return entryError("Discount amount must be a number with up to 2 decimals.", ie.disc_amt);
      if (!PCT_RE.test(l.gst_pct || "0") || scaled(l.gst_pct, 2) > 10000n) return entryError("GST % must be between 0 and 100.", ie.gst_pct);
      var c = calcLine(l, gstOn());
      if (!c) return entryError("Check the numbers entered.");
      if (c.discount > c.gross) return entryError("Discount can't be more than the amount.", ie.disc_amt);
      l.qty = fmt(scaled(l.qty, 3), 3);
      l.rate = fmt(scaled(l.rate, 2));
      l.disc_pct = fmt(scaled(l.disc_pct, 2));
      l.disc_amt = fmt(c.discount);
      l.gst_pct = fmt(scaled(l.gst_pct, 2));
      if (editingIndex >= 0) items[editingIndex] = l; else items.push(l);
      markDirty();
      resetEntry();
      renderRows();
      clearFieldError("items");
      itemInput.focus();
      return true;
    }

    function clearFieldError(key) {
      var holder = form.querySelector('[data-error-for="' + key + '"]');
      if (holder) holder.textContent = "";
      var wrap = form.querySelector('[data-field-wrap="' + key + '"]');
      if (wrap) wrap.classList.remove("is-invalid");
    }

    ie.disc_pct.addEventListener("input", function () {
      var c = calcLine(Object.assign(entryLine(), { disc_amt: "0" }), gstOn());
      if (c && scaled(ie.disc_pct.value, 2) > 0n) ie.disc_amt.value = fmt(c.discount);
      updateEntryAmount();
    });
    ie.disc_amt.addEventListener("input", function () { ie.disc_pct.value = "0.00"; updateEntryAmount(); });
    ["qty", "rate", "gst_pct"].forEach(function (k) {
      ie[k].addEventListener("input", function () {
        if (scaled(ie.disc_pct.value, 2) > 0n) {
          var c = calcLine(Object.assign(entryLine(), { disc_amt: "0" }), gstOn());
          if (c) ie.disc_amt.value = fmt(c.discount);
        }
        updateEntryAmount();
      });
    });
    ["qty", "rate", "disc_pct", "disc_amt", "gst_pct"].forEach(function (k) {
      ie[k].addEventListener("keydown", function (event) {
        if (event.key === "Enter") { event.preventDefault(); commitEntry(); }
      });
      ie[k].addEventListener("focus", function () { ie[k].select(); });
    });
    $("[data-item-ok]").addEventListener("click", commitEntry);
    $("[data-item-cancel]").addEventListener("click", function () { resetEntry(); renderRows(); });

    itemInput.addEventListener("input", function () {
      if (currentItem && itemInput.value !== currentItem.name) {
        currentItem = null;
        $("[data-item-label]").textContent = "";
      }
    });

    // --- lookups (shared HelpLookup popup) -------------------------------------------------
    var partyLookup = {
      endpoint: config.urls.parties, resultsKey: "parties", valueField: "name", title: "Party",
      displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }, { key: "phone", label: "Phone" }],
      onSelect: function (row) {
        field("party_code").value = row.code;
        partyInput.value = row.name;
        field("city").value = (row.city || "").slice(0, 30);
        field("phone").value = (row.phone || "").slice(0, 20);
        clearFieldError("party_code");
        showPartyCode();
        markDirty();
      },
    };
    var itemLookup = {
      endpoint: config.urls.items, resultsKey: "items", valueField: "name", title: "Item",
      displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Description" }, { key: "unit", label: "Unit" }, { key: "rate", label: "Rate" }, { key: "gst_percent", label: "GST %" }],
      onSelect: function (row) {
        setItem({ code: row.code, name: row.name, unit: row.unit, gst_percent: row.gst_percent });
        ie.gst_pct.value = row.gst_percent || "0.00";
        ie.rate.value = row.rate || "0.00";
        $("[data-item-error]").textContent = "";
        updateEntryAmount();
        ie.qty.focus();
      },
    };
    if (window.HelpLookup && !readOnly) {
      window.HelpLookup.attach(partyInput, partyLookup);
      window.HelpLookup.attach(itemInput, itemLookup);
    }
    partyInput.addEventListener("input", function () {
      if (field("party_code").value) { field("party_code").value = ""; }
      showPartyCode();
    });

    // --- dirty tracking --------------------------------------------------------------------
    function markDirty() { if (!readOnly) dirty = true; }
    form.addEventListener("input", function (event) {
      if (event.target.closest("[data-item-entry]")) return; // only committed rows count
      markDirty();
    });
    form.addEventListener("change", function (event) {
      if (event.target === field("gst_applicable")) { renderRows(); updateEntryAmount(); }
      if (!event.target.closest("[data-item-entry]")) markDirty();
    });
    window.addEventListener("beforeunload", function (event) {
      if (dirty && !leaving) { event.preventDefault(); event.returnValue = ""; }
    });

    function leave(url) {
      leaving = true;
      window.location.href = url;
    }

    $("[data-exit]").addEventListener("click", function () {
      var ask = window.askConfirm || function (m, yes) { if (window.confirm(m)) yes(); };
      if (dirty) ask("Discard your unsaved changes?", function () { leave(config.urls.list); });
      else leave(config.urls.list);
    });

    // --- save / confirm / print ------------------------------------------------------------
    function payload() {
      return {
        quot_no: field("quot_no").value.trim(),
        quot_date: field("quot_date").value.trim(),
        ref_no: field("ref_no").value.trim(),
        ref_date: field("ref_date").value.trim(),
        gst_applicable: field("gst_applicable").value,
        party_code: field("party_code").value,
        city: field("city").value.trim(),
        phone: field("phone").value.trim(),
        kind_attention: Array.prototype.map.call(form.querySelectorAll("[data-kind]"), function (el) { return el.value.trim(); }),
        remarks: field("remarks").value,
        terms: Array.prototype.map.call(form.querySelectorAll("[data-term]"), function (el) { return el.value.trim(); }),
        bank: Array.prototype.map.call(form.querySelectorAll("[data-bank]"), function (el) { return el.value.trim(); }),
        items: items.filter(function (l) { return !l.held; }).map(function (l) {
          return { item_code: l.item_code, currency: l.currency, qty: l.qty, rate: l.rate, disc_pct: l.disc_pct,
                   disc_amt: l.disc_amt, gst_pct: l.gst_pct, particular: l.particular };
        }),
      };
    }

    function setBusy(state) {
      busy = state;
      form.querySelectorAll(".quot-actions .btn, [data-item-ok]").forEach(function (b) {
        if (b.hasAttribute("data-confirm") && !config.can_confirm) return;
        b.disabled = state;
      });
      form.setAttribute("aria-busy", state ? "true" : "false");
    }

    function pendingEntry() {
      return editingIndex >= 0 || currentItem !== null;
    }

    function submit(action) {
      if (busy || readOnly) return;
      clearErrors();
      showAlert("");
      if (pendingEntry()) {
        showAlert("You have an item in the entry row that isn't in the grid yet. Press OK to add it, or Cancel / clear it.");
        itemInput.focus();
        return;
      }
      if (!items.some(function (l) { return !l.held; })) {
        showErrors({ items: "Add at least one item." });
        showAlert("Add at least one active (non-held) item before saving.");
        return;
      }
      if (!field("party_code").value) {
        showErrors({ party_code: "Select a party from the Customer Master." });
        showAlert("Please correct the highlighted fields.");
        return;
      }
      setBusy(true);
      fetch(config.urls.save, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf, "X-Requested-With": "XMLHttpRequest" },
        body: JSON.stringify({ token: token, action: action, key: mode === "edit" ? q.quot_no : null, quotation: payload() }),
      }).then(function (response) {
        return response.json().catch(function () { return { ok: false, message: "Unexpected server response (" + response.status + ")." }; });
      }).then(function (data) {
        if (!data.ok) {
          setBusy(false);
          showErrors(data.errors);
          showAlert(data.message || "Could not save the quotation.");
          return;
        }
        dirty = false;
        if (action === "confirm") {
          leave(data.list_url);
          return;
        }
        token = data.next_token || token;
        if (mode === "add") {
          mode = "edit";
          q.quot_no = data.quot_no;
          field("quot_no").value = data.quot_no;
          field("quot_no").readOnly = true;
          var label = document.querySelector("[data-mode-label]");
          if (label) { label.textContent = "Modify"; label.className = "quot-mode quot-mode--edit"; }
          if (window.history && window.history.replaceState) window.history.replaceState(null, "", data.edit_url);
          document.title = document.title.replace("(new)", data.quot_no);
        }
        setBusy(false);
        showAlert(data.message + (data.replayed ? " (already saved)" : ""), "success");
        showToast(data.message);
      }).catch(function () {
        setBusy(false);
        showAlert("Network error: the quotation may not have been saved. Click Save again; it will not be saved twice.");
      });
    }

    var saveBtn = $("[data-save]");
    if (saveBtn) saveBtn.addEventListener("click", function () { submit("save"); });
    var confirmBtn = $("[data-confirm]");
    if (confirmBtn) confirmBtn.addEventListener("click", function () {
      var ask = window.askConfirm || function (m, yes) { if (window.confirm(m)) yes(); };
      ask("Are you sure? Confirm saves quotation " + (field("quot_no").value || "") + " and marks it confirmed.", function () { submit("confirm"); });
    });
    var printBtn = $("[data-print]");
    if (printBtn) printBtn.addEventListener("click", function () {
      if (mode === "add" || dirty) {
        showAlert("Save the quotation first, then print it.", "warning");
        return;
      }
      window.open(config.urls.print.replace("__NO__", encodeURIComponent(q.quot_no)), "_blank", "noopener");
    });

    resetEntry();
    renderRows();
    if (!readOnly) (mode === "add" ? partyInput : field("quot_date")).focus();
  });
})();
