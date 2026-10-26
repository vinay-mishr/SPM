/*
 * HelpLookup — universal Help / Lookup popup (keyboard-driven, like the old VFP "Help" key).
 *
 * Attach it to any text input that should offer a searchable lookup grid, backed by a
 * server endpoint:
 *
 *   HelpLookup.attach(document.querySelector('#supplier1'), {
 *     endpoint: '/masters/parts/api/parties/',   // JSON endpoint; called as endpoint?q=<text>
 *     resultsKey: 'parties',                     // key in the JSON response holding the array
 *                                                 // (omit this if the response IS the array)
 *     valueField: 'code',                        // property copied into the field on selection
 *     displayFields: [                           // popup grid columns, in order
 *       { key: 'code', label: 'Code' },
 *       { key: 'name', label: 'Name' },
 *       { key: 'city', label: 'City' }           // any extra columns are just for display
 *     ],
 *     searchParam: 'q',                          // query-string param name (default 'q')
 *     minChars: 0,                                // characters needed before searching (default 0)
 *     maxResults: 50,                             // trims the rendered list (default: show all returned)
 *     title: 'Supplier',                          // popup heading, shown upper-cased as "SUPPLIER HELP"
 *                                                 // (default: the field's aria-label / placeholder / name)
 *     filters: { group: 'S002' },                // extra static query-string params sent with every search
 *     onSelect: function (row, field) {}          // optional: called after the value is filled in
 *   });
 *
 * Or back it with a small, already-known list of choices (no server round-trip) --
 * pass `data` (an array) instead of `endpoint`; typing filters it locally:
 *
 *   HelpLookup.attach(document.querySelector('#gst_category'), {
 *     data: [{ value: 'REGULAR', label: 'Regular' }, { value: 'COMPOSITION', label: 'Composition' }],
 *     valueField: 'value',
 *     displayFields: [{ key: 'label', label: 'Category' }]
 *   });
 *
 * For a plain <select>, HelpLookup.attachSelect() builds that `data` list for you from the
 * element's own <option>s, so any dropdown gets the same Enter -> searchable-grid behavior
 * with one line and no extra config:
 *
 *   HelpLookup.attachSelect(document.querySelector('#gst_category'), { title: 'GST Category' });
 *
 * User experience:
 *   - Focus the field, press ENTER once  -> popup opens (seeded with whatever the field already has typed).
 *   - Type to filter (server-side, debounced) -- no separate Search button.
 *   - Arrow Up / Down moves the highlighted row, Home / End jump to the first / last row.
 *   - ENTER on a highlighted row selects it: fills the field, closes the popup, returns focus to the field.
 *   - ESC closes the popup without changing the field.
 *   - Clicking a row selects it immediately, same as pressing Enter on it.
 *
 * One popup <dialog> is created lazily and reused for every field on the page.
 */
(function (window, document) {
  "use strict";

  if (window.HelpLookup) return; // already loaded

  var DEBOUNCE_MS = 200;

  var dialog, titleEl, searchInput, tableBody, emptyNote, theadEl;
  var state = {
    config: null,
    field: null,
    rows: [],
    selectedIndex: -1,
    requestToken: 0,
    debounceTimer: null,
  };

  function ensureDialog() {
    if (dialog) return;

    dialog = document.createElement("dialog");
    dialog.className = "help-lookup-dialog";
    dialog.innerHTML =
      '<div class="help-lookup">' +
      '  <header class="help-lookup__header">' +
      '    <h2 class="help-lookup__title" data-help-title>Help</h2>' +
      '    <button type="button" class="help-lookup__close" data-help-close aria-label="Close">&times;</button>' +
      "  </header>" +
      '  <div class="help-lookup__body">' +
      '    <input type="text" class="help-lookup__search" data-help-search autocomplete="off" placeholder="Type to search…" aria-label="Search">' +
      '    <div class="help-lookup__grid-wrap">' +
      '      <table class="help-lookup__grid"><thead data-help-thead></thead><tbody data-help-rows></tbody></table>' +
      '      <p class="help-lookup__empty" data-help-empty hidden>No matches</p>' +
      "    </div>" +
      "  </div>" +
      "</div>";
    document.body.appendChild(dialog);

    titleEl = dialog.querySelector("[data-help-title]");
    searchInput = dialog.querySelector("[data-help-search]");
    tableBody = dialog.querySelector("[data-help-rows]");
    emptyNote = dialog.querySelector("[data-help-empty]");
    theadEl = dialog.querySelector("[data-help-thead]");

    dialog.querySelector("[data-help-close]").addEventListener("click", cancel);
    dialog.addEventListener("cancel", function (event) {
      event.preventDefault();
      cancel();
    });
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) cancel(); // click on the backdrop
    });

    searchInput.addEventListener("input", function () {
      clearTimeout(state.debounceTimer);
      state.debounceTimer = setTimeout(runSearch, DEBOUNCE_MS);
    });
    searchInput.addEventListener("keydown", handleKeydown);
    tableBody.addEventListener("click", function (event) {
      var tr = event.target.closest("tr[data-index]");
      if (!tr) return;
      state.selectedIndex = Number(tr.dataset.index);
      confirmSelection();
    });
  }

  function fieldLabel(field) {
    return field.getAttribute("aria-label") || field.placeholder || field.name || "value";
  }

  function buildQueryString(term) {
    var config = state.config;
    var params = new URLSearchParams();
    params.set(config.searchParam || "q", term);
    if (config.filters) {
      Object.keys(config.filters).forEach(function (key) {
        params.set(key, config.filters[key]);
      });
    }
    return params.toString();
  }

  function extractRows(data) {
    var config = state.config;
    if (Array.isArray(data)) return data;
    if (config.resultsKey && Array.isArray(data[config.resultsKey])) return data[config.resultsKey];
    // Fall back to the first array found in the response.
    for (var key in data) {
      if (Array.isArray(data[key])) return data[key];
    }
    return [];
  }

  /* Local (no server) filtering for config.data: substring match, case-insensitive,
   * across searchFields (default: every displayFields key) plus valueField. */
  function filterLocal(term) {
    var config = state.config;
    var rows = typeof config.data === "function" ? config.data() : config.data;
    if (!term) return rows;
    var fields = config.searchFields || config.displayFields.map(function (c) { return c.key; }).concat([config.valueField]);
    var needle = term.toLowerCase();
    return rows.filter(function (row) {
      return fields.some(function (key) {
        return row[key] != null && String(row[key]).toLowerCase().indexOf(needle) > -1;
      });
    });
  }

  function runSearch() {
    var config = state.config;
    var term = searchInput.value.trim();
    if (term.length < (config.minChars || 0)) {
      renderRows([]);
      return;
    }

    if (config.data) {
      var rows = filterLocal(term);
      if (config.maxResults) rows = rows.slice(0, config.maxResults);
      renderRows(rows);
      return;
    }

    var token = ++state.requestToken;
    var url = config.endpoint + (config.endpoint.indexOf("?") > -1 ? "&" : "?") + buildQueryString(term);
    fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (token !== state.requestToken) return; // a newer search has already started
        var rows = extractRows(data);
        if (config.maxResults) rows = rows.slice(0, config.maxResults);
        renderRows(rows);
      })
      .catch(function () {
        if (token === state.requestToken) renderRows([]);
      });
  }

  function cell(text) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : String(text);
    return td;
  }

  function renderHeader(config) {
    var tr = document.createElement("tr");
    config.displayFields.forEach(function (column) {
      var th = document.createElement("th");
      th.scope = "col";
      th.textContent = column.label || column.key;
      tr.appendChild(th);
    });
    theadEl.textContent = "";
    theadEl.appendChild(tr);
  }

  function renderRows(rows) {
    state.rows = rows;
    state.selectedIndex = rows.length ? 0 : -1;
    tableBody.textContent = "";
    rows.forEach(function (row, index) {
      var tr = document.createElement("tr");
      tr.dataset.index = String(index);
      state.config.displayFields.forEach(function (column) {
        tr.appendChild(cell(row[column.key]));
      });
      tableBody.appendChild(tr);
    });
    emptyNote.hidden = rows.length !== 0;
    highlightSelected();
  }

  function highlightSelected() {
    tableBody.querySelectorAll("tr").forEach(function (tr) {
      var on = Number(tr.dataset.index) === state.selectedIndex;
      tr.classList.toggle("is-selected", on);
      if (on) tr.scrollIntoView({ block: "nearest" });
    });
  }

  function move(delta) {
    if (!state.rows.length) return;
    var next = state.selectedIndex + delta;
    if (next < 0) next = 0;
    if (next > state.rows.length - 1) next = state.rows.length - 1;
    state.selectedIndex = next;
    highlightSelected();
  }

  function jumpTo(edge) {
    if (!state.rows.length) return;
    state.selectedIndex = edge === "home" ? 0 : state.rows.length - 1;
    highlightSelected();
  }

  /* After a selection, move focus on to the next logical field in the same form/dialog
   * (matching each module's own "Enter moves to the next field" convention), falling
   * back to the Confirm button when the selected field was the last one. */
  function focusNext(field) {
    var scope = field.closest("form") || field.closest("dialog") || field.ownerDocument;
    var candidates = Array.prototype.slice.call(
      scope.querySelectorAll(
        "input:not([type=hidden]):not([readonly]):not([disabled]), " +
        "select:not([disabled]), textarea:not([readonly]):not([disabled])"
      )
    ).filter(function (el) { return el.offsetParent !== null; }); // skip hidden fields
    var index = candidates.indexOf(field);
    if (index > -1 && index < candidates.length - 1) {
      candidates[index + 1].focus();
      if (candidates[index + 1].select) candidates[index + 1].select();
      return;
    }
    var confirmBtn = scope.querySelector("[data-form-confirm]");
    if (confirmBtn) confirmBtn.focus();
    else field.focus();
  }

  function confirmSelection() {
    if (state.selectedIndex < 0 || state.selectedIndex >= state.rows.length) return;
    var row = state.rows[state.selectedIndex];
    var config = state.config;
    var field = state.field;
    var value = row[config.valueField];
    field.value = value == null ? "" : String(value);
    field.dispatchEvent(new Event("input", { bubbles: true }));
    field.dispatchEvent(new Event("change", { bubbles: true }));
    close_();
    if (typeof config.onSelect === "function") config.onSelect(row, field);
    focusNext(field);
  }

  function cancel() {
    close_();
    if (state.field) state.field.focus();
  }

  function close_() {
    if (dialog && dialog.open) dialog.close();
    clearTimeout(state.debounceTimer);
    state.requestToken++; // invalidate any in-flight search
  }

  function handleKeydown(event) {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        move(1);
        break;
      case "ArrowUp":
        event.preventDefault();
        move(-1);
        break;
      case "Home":
        event.preventDefault();
        jumpTo("home");
        break;
      case "End":
        event.preventDefault();
        jumpTo("end");
        break;
      case "Enter":
        event.preventDefault();
        confirmSelection();
        break;
      case "Escape":
        // Handled explicitly (rather than relying on <dialog>'s native "cancel" event):
        // this popup often opens on top of another already-open modal (e.g. an Add/Modify
        // form), and Escape's implicit dialog-cancel behavior is unreliable with two
        // stacked native <dialog> elements.
        event.preventDefault();
        event.stopPropagation();
        cancel();
        break;
    }
  }

  function open(field, config) {
    ensureDialog();
    state.config = config;
    state.field = field;
    dialog.classList.toggle("help-lookup-dialog--wide", config.displayFields.length > 1);
    dialog.classList.toggle("help-lookup-dialog--xwide", config.displayFields.length > 3);
    titleEl.textContent = ((config.title || fieldLabel(field)) + " Help").toUpperCase();
    searchInput.value = (config.seedText ? config.seedText(field) : field.value) || "";
    renderHeader(config);
    renderRows([]);
    dialog.showModal();
    searchInput.focus();
    searchInput.select();
    runSearch();
  }

  function attach(field, config) {
    if (!field || !config || !(config.endpoint || config.data) || !config.valueField || !config.displayFields) {
      throw new Error("HelpLookup.attach: field, (endpoint or data), valueField and displayFields are required.");
    }
    field.addEventListener("keydown", function (event) {
      if (event.key !== "Enter") return;
      if (field.readOnly) return; // e.g. a form in View mode -- nothing here should be editable
      if (dialog && dialog.open) return; // popup already handles its own Enter
      event.preventDefault();
      // Stop this Enter from also reaching the surrounding form's own "move to the
      // next field" handler -- without this, both fire (open the popup AND jump focus).
      event.stopPropagation();
      open(field, config);
    });
  }

  /* Convenience for a plain <select>: builds the lookup list from its own <option>s
   * (skipping a blank/placeholder option) instead of requiring separate config.
   *
   * The native <select> is hidden (never rendered) and a plain text input takes its
   * place visually -- a real <select> always opens the browser's own dropdown on
   * click / Space / Alt+Down / F4, in every browser, with no reliable cross-browser
   * way to suppress just that while keeping it keyboard-usable. The hidden select
   * stays the single source of truth (same id, same data-field, same <option>s --
   * so any code elsewhere that reads/sets `.value`/`.disabled` or adds an extra
   * "(not in list)" <option> keeps working unmodified): its `value` and `disabled`
   * IDL properties are overridden on this one element instance so that setting them
   * from anywhere automatically keeps the visible proxy text (and its enabled state)
   * in sync, with no other file needing to know a proxy exists.
   *
   * The proxy is deliberately NOT marked `readonly`: this app's own "move to the next
   * field" logic (both Enter-to-advance and HelpLookup's own post-selection
   * focusNext()) explicitly skips `[readonly]` fields, which would make every one of
   * these fields unreachable by keyboard -- reachable only by clicking with the
   * mouse. Direct typing is blocked a different way (snapped back to the current
   * label on every `input` event) so the field still behaves read-only to the user
   * without being excluded from keyboard navigation. */
  function attachSelect(select, extra) {
    extra = extra || {};
    if (select.dataset.helpSelectProxied === "1") return; // already wired

    var proxy = document.createElement("input");
    proxy.type = "text";
    proxy.className = select.className;
    proxy.autocomplete = "off";
    var blank = select.querySelector('option[value=""]');
    if (blank && blank.textContent.trim()) proxy.placeholder = blank.textContent.trim();
    if (select.id) { proxy.id = select.id; select.removeAttribute("id"); }
    select.hidden = true;
    select.tabIndex = -1;
    select.dataset.helpSelectProxied = "1";
    select.parentNode.insertBefore(proxy, select.nextSibling);

    // A function (re-read every time the popup opens), not a frozen snapshot: some
    // selects gain an extra "(not in list)" <option> later (see party_master_form.js's
    // fill()), and the lookup should still offer whatever the field can actually hold.
    function readOptions() {
      var options = Array.prototype.slice.call(select.options)
        .filter(function (o) { return o.value !== ""; })
        .map(function (o) { return { value: o.value, label: o.textContent.trim() }; });
      // e.g. State: once a value is already selected (say, filled in from a GSTIN),
      // show that one first instead of making the user hunt for it in the full list.
      if (extra.selectedFirst && select.value) {
        var index = options.findIndex(function (o) { return o.value === select.value; });
        if (index > 0) options.unshift(options.splice(index, 1)[0]);
      }
      return options;
    }
    function labelFor(value) {
      if (!value) return ""; // blank/placeholder option -> show the placeholder, not its own text
      var match = Array.prototype.slice.call(select.options).filter(function (o) { return o.value === value; })[0];
      return match ? match.textContent.trim() : "";
    }
    // Typing directly into the proxy can't change the real value (there's no search-
    // as-you-type here, only the Enter popup) -- snap any edit straight back.
    proxy.addEventListener("input", function () { proxy.value = labelFor(select.value); });

    var valueDesc = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value");
    Object.defineProperty(select, "value", {
      configurable: true,
      get: function () { return valueDesc.get.call(select); },
      set: function (v) { valueDesc.set.call(select, v); proxy.value = labelFor(select.value); },
    });
    var disabledDesc = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "disabled");
    Object.defineProperty(select, "disabled", {
      configurable: true,
      get: function () { return disabledDesc.get.call(select); },
      set: function (v) {
        disabledDesc.set.call(select, v);
        proxy.classList.toggle("is-disabled", Boolean(v));
        proxy.tabIndex = v ? -1 : 0;
      },
    });
    proxy.value = labelFor(select.value);

    attach(proxy, Object.assign({
      valueField: "value",
      displayFields: [{ key: "label", label: extra.title || "Value" }],
      // Show the full option list on open rather than pre-filtering down to whatever
      // is already selected (a select usually already has some default value).
      seedText: function () { return ""; },
    }, extra, {
      data: readOptions, // `data` always wins: always read fresh from the <select>
      onSelect: function (row) {
        select.value = row.value; // through the intercepted setter above -> proxy syncs itself
        select.dispatchEvent(new Event("change", { bubbles: true }));
        if (typeof extra.onSelect === "function") extra.onSelect(row);
      },
    }));
  }

  /* Convenience for a text input that already offers suggestions via a <datalist>
   * (list="..."): builds the lookup list from that datalist's own <option>s, so any
   * existing type-ahead field gets the same Enter -> searchable-grid popup for free. */
  function attachDatalist(field, extra) {
    extra = extra || {};
    var datalist = field.list; // the <datalist> the input's list="" attribute points to
    function readOptions() {
      if (!datalist) return [];
      return Array.prototype.slice.call(datalist.options)
        .filter(function (o) { return o.value !== ""; })
        .map(function (o) { return { value: o.value, label: (o.label || o.textContent || o.value).trim() }; });
    }
    attach(field, Object.assign({
      valueField: "value",
      displayFields: [{ key: "label", label: extra.title || "Value" }],
      seedText: function () { return ""; },
    }, extra, { data: readOptions }));
  }

  window.HelpLookup = { attach: attach, attachSelect: attachSelect, attachDatalist: attachDatalist, open: open };
})(window, document);
