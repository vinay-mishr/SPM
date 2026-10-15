/* Part Master — list screen: grid, selection, search, toolbar and delete dialog.
 * Uses window.SPPartForm (part_master_form.js) for Add / Modify / View.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-part-master]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var countNote = root.querySelector("[data-count]");
  var searchBox = root.querySelector("[data-search]");
  var toast = document.querySelector("[data-toast]");
  var delDialog = document.getElementById("part-delete-dialog");
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var initial = JSON.parse(document.getElementById("part-initial-data").textContent);
  var money = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  var state = { parts: initial.parts, selected: null, query: "" };

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function selected() {
    return state.parts.find(function (p) { return p.id === state.selected; }) || null;
  }

  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text;
    if (cls) td.className = cls;
    return td;
  }

  function matches(p) {
    if (!state.query) return true;
    return [p.part_number, p.description_1, p.description_2, p.drawing_no, p.hsn_code, p.unit]
      .join(" ").toLowerCase().indexOf(state.query) > -1;
  }

  function render() {
    var visible = state.parts.filter(matches);
    tbody.textContent = "";
    visible.forEach(function (p) {
      var tr = document.createElement("tr");
      tr.dataset.id = p.id;
      tr.tabIndex = 0;
      if (p.id === state.selected) tr.classList.add("is-selected");
      tr.append(
        cell(p.part_number, "master-table__code"),
        cell(p.description_1),
        cell(p.drawing_no),
        cell(p.hsn_code),
        cell(p.unit),
        cell(money.format(Number(p.gst_percent)), "num"),
        cell(money.format(Number(p.purchase_rate)), "num"),
        cell(money.format(Number(p.sale_rate)), "num"),
        cell(p.sub_assembly ? "Y" : "", "part-table__sa")
      );
      tbody.appendChild(tr);
    });
    emptyNote.hidden = visible.length > 0;
    countNote.textContent = visible.length + " of " + state.parts.length + " part" + (state.parts.length === 1 ? "" : "s");
    updateToolbar();
  }

  function updateToolbar() {
    var has = Boolean(selected());
    ["modify", "delete", "view"].forEach(function (a) {
      root.querySelector('[data-action="' + a + '"]').disabled = !has;
    });
  }

  function select(id) {
    state.selected = id;
    tbody.querySelectorAll("tr").forEach(function (tr) { tr.classList.toggle("is-selected", tr.dataset.id === id); });
    updateToolbar();
  }

  function refresh(selectId) {
    return fetch(root.dataset.listUrl, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        state.parts = data.parts;
        if (selectId !== undefined) state.selected = selectId;
        if (!selected()) state.selected = null;
        render();
        var row = tbody.querySelector('tr[data-id="' + CSS.escape(state.selected || "") + '"]');
        if (row) row.scrollIntoView({ block: "nearest" });
      });
  }

  var DETAIL_LABELS = [["part_number", "Part No"], ["description_1", "Description"], ["description_2", "Description 2"],
    ["drawing_no", "Drawing No"], ["gauge", "Gauge"], ["grade", "Grade"], ["material", "Material"],
    ["location", "Location"], ["unit", "Unit"], ["hsn_code", "HSN Code"], ["part_type", "Part Type"],
    ["sub_assembly", "Sub Assembly"], ["gst_percent", "GST %"],
    ["purchase_rate", "Purchase Rate"], ["sale_rate", "Sale Rate"],
    ["rate_1", "Rate 1"], ["rate_2", "Rate 2"], ["rate_3", "Rate 3"], ["rate_4", "Rate 4"],
    ["supplier_1", "Supplier 1"], ["supplier_2", "Supplier 2"], ["supplier_3", "Supplier 3"], ["supplier_4", "Supplier 4"],
    ["packing", "Packing"], ["gross_weight", "Gross Weight"], ["weight_by_100", "Weight / 100"],
    ["quantity_in_order", "Qty in Order"], ["opening_stock", "Opening Stock"],
    ["current_stock", "Current Stock"], ["reorder_qty", "Reorder Qty"]];

  function openDelete(p) {
    var dl = delDialog.querySelector("[data-delete-details]");
    dl.textContent = "";
    DETAIL_LABELS.forEach(function (pair) {
      var dt = document.createElement("dt"), dd = document.createElement("dd");
      dt.textContent = pair[1]; dd.textContent = p[pair[0]] || "—";
      dl.append(dt, dd);
    });
    delDialog.querySelector("[data-delete-alert]").hidden = true;
    delDialog.querySelector("[data-delete-confirm]").disabled = false;
    delDialog.showModal();
    delDialog.querySelector(".modal__footer [data-delete-cancel]").focus();
  }

  function confirmDelete() {
    var p = selected();
    var btn = delDialog.querySelector("[data-delete-confirm]");
    var alertBox = delDialog.querySelector("[data-delete-alert]");
    if (!p) return;
    btn.disabled = true;
    fetch(root.dataset.deleteUrl.replace("/0/", "/" + encodeURIComponent(p.id) + "/"), {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" }
    })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        if (res.ok) {
          delDialog.close();
          state.selected = null;
          showToast(res.body.message);
          return refresh();
        }
        alertBox.textContent = res.body.message || "The part could not be deleted.";
        alertBox.hidden = false;
      })
      .catch(function () {
        alertBox.textContent = "Could not reach the server. Please try again.";
        alertBox.hidden = false;
        btn.disabled = false;
      });
  }

  var actions = {
    add: function () { SPPartForm.open("add", null); },
    modify: function () { var p = selected(); if (p) SPPartForm.open("modify", p); },
    view: function () { var p = selected(); if (p) SPPartForm.open("view", p); },
    "delete": function () { var p = selected(); if (p) openDelete(p); },
    exit: function () { window.location.href = root.dataset.exitUrl; }
  };

  root.querySelectorAll("[data-action]").forEach(function (b) {
    b.addEventListener("click", function () { actions[b.dataset.action](); });
  });
  tbody.addEventListener("click", function (e) { var tr = e.target.closest("tr"); if (tr) select(tr.dataset.id); });
  tbody.addEventListener("dblclick", function (e) { var tr = e.target.closest("tr"); if (tr) { select(tr.dataset.id); actions.view(); } });
  tbody.addEventListener("keydown", function (e) {
    var tr = e.target.closest("tr");
    if (!tr) return;
    if (e.key === "Enter") { select(tr.dataset.id); actions.view(); }
    else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      var next = e.key === "ArrowDown" ? tr.nextElementSibling : tr.previousElementSibling;
      if (next) { next.focus(); select(next.dataset.id); }
    }
  });
  searchBox.addEventListener("input", function () { state.query = searchBox.value.trim().toLowerCase(); render(); });
  document.addEventListener("keydown", function (e) {
    if (!e.altKey || document.querySelector("dialog[open]")) return;
    var map = { a: "add", m: "modify", d: "delete", v: "view", x: "exit" };
    var btn = map[e.key.toLowerCase()] && root.querySelector('[data-action="' + map[e.key.toLowerCase()] + '"]');
    if (btn && !btn.disabled) { e.preventDefault(); btn.click(); }
  });
  delDialog.querySelectorAll("[data-delete-cancel]").forEach(function (b) { b.addEventListener("click", function () { delDialog.close(); }); });
  delDialog.querySelector("[data-delete-confirm]").addEventListener("click", confirmDelete);

  SPPartForm.init({
    createUrl: root.dataset.createUrl,
    updateUrl: root.dataset.updateUrl,
    partiesUrl: root.dataset.partiesUrl,
    csrfToken: csrfToken,
    onSaved: function (p, message) { showToast(message); refresh(p.id); }
  });

  render();
})();
