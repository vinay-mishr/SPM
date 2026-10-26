/* Purchase Order Master — list screen + shared Add/Modify/View form.
 * Old VFP form: PURCHASE ORDER FORM (po1). Header = pord_mst, lines = order table.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-po-master]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var searchBox = root.querySelector("[data-search]");
  var startDate = root.querySelector("[data-start-date]");
  var endDate = root.querySelector("[data-end-date]");
  var statusRadios = root.querySelectorAll('input[name="po-status"]');
  var toast = document.querySelector("[data-toast]");
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;

  var initial = JSON.parse(document.getElementById("po-initial-data").textContent);
  var state = { orders: initial.orders, selectedKey: null, query: "", status: "all" };

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function post(url, data) {
    var body = new URLSearchParams();
    Object.keys(data || {}).forEach(function (k) { body.append(k, data[k] == null ? "" : data[k]); });
    return fetch(url, {
      method: "POST", credentials: "same-origin", body: body,
      headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" },
    }).then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; }); });
  }

  function postJson(url, data) {
    return fetch(url, {
      method: "POST", credentials: "same-origin", body: JSON.stringify(data),
      headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json" },
    }).then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; }); });
  }

  function fetchJson(url) {
    return fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; }); });
  }

  function dmy(iso) {
    if (!iso) return "";
    var p = String(iso).split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : iso;
  }

  function cell(text, className) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (className) td.className = className;
    return td;
  }

  /* --- Rendering -------------------------------------------------------------- */

  function selectedOrder() {
    return state.orders.find(function (o) { return o.key === state.selectedKey; }) || null;
  }

  /* A filter date only counts once it is a complete dd/mm/yyyy -- a half-typed one
     (e.g. "02/10/20") would otherwise compare as a wrong ISO string. */
  function filterIso(input) {
    var v = input.value.trim();
    return /^\d{2}\/\d{2}\/\d{4}$/.test(v) ? window.DateMask.toIso(v) : "";
  }

  function matches(order) {
    var text = state.query;
    var inRange = true;
    var start = filterIso(startDate);
    var end = filterIso(endDate);
    if (start && order.order_date && order.order_date < start) inRange = false;
    if (end && order.order_date && order.order_date > end) inRange = false;
    if (!inRange) return false;
    if (state.status !== "all" && order.status !== state.status) return false;
    if (!text) return true;
    return [order.po_no, order.party_code, order.party_name, order.city].join(" ").toLowerCase().indexOf(text) > -1;
  }

  function render() {
    var visible = state.orders.filter(matches);
    tbody.textContent = "";
    visible.forEach(function (order) {
      var tr = document.createElement("tr");
      tr.dataset.key = order.key;
      tr.tabIndex = 0;
      tr.setAttribute("aria-selected", String(order.key === state.selectedKey));
      if (order.key === state.selectedKey) tr.classList.add("is-selected");
      tr.append(
        cell(order.po_no, "master-table__code"),
        cell(dmy(order.order_date)),
        cell(order.party_name || order.party_code),
        cell(order.city),
        cell(order.net_amount, "num"),
        cell(order.uname)
      );
      tbody.appendChild(tr);
    });
    emptyNote.hidden = visible.length > 0;
    updateToolbar();
  }

  function updateToolbar() {
    var hasSelection = Boolean(selectedOrder());
    root.querySelectorAll('[data-action="modify"], [data-action="delete"], [data-action="view"], [data-action="print"]').forEach(function (btn) {
      btn.disabled = !hasSelection;
    });
  }

  function select(key) {
    state.selectedKey = key;
    tbody.querySelectorAll("tr").forEach(function (tr) {
      var on = tr.dataset.key === key;
      tr.classList.toggle("is-selected", on);
      tr.setAttribute("aria-selected", String(on));
    });
    updateToolbar();
  }

  tbody.addEventListener("click", function (e) {
    var tr = e.target.closest("tr[data-key]");
    if (tr) select(tr.dataset.key);
  });

  searchBox.addEventListener("input", function () {
    state.query = searchBox.value.trim().toLowerCase();
    render();
  });
  // All / Pending / Completed Orders -- was dead markup with no listener at all,
  // so picking any of the three did nothing. Each order's status (set server-side
  // in services.list_orders()) is "pending" when it still has an open line (adj
  // blank AND stk_qty - rec_qty > 0, same rule as the Pending P.O. report), else
  // "completed".
  statusRadios.forEach(function (radio) {
    radio.addEventListener("change", function () {
      if (radio.checked) { state.status = radio.value; render(); }
    });
  });
  /* Start / End Date default to today; the grid re-filters as soon as a date is
     complete (or cleared), not only when the field loses focus. */
  (function () {
    var d = new Date();
    var today = String(d.getDate()).padStart(2, "0") + "/" + String(d.getMonth() + 1).padStart(2, "0") + "/" + d.getFullYear();
    startDate.value = today;
    endDate.value = today;
  })();
  [startDate, endDate].forEach(function (input) {
    input.addEventListener("change", render);
    input.addEventListener("input", function () {
      var v = input.value.trim();
      if (!v || v.length === 10) render();
    });
  });

  function refresh(selectKey) {
    return fetchJson(root.dataset.listUrl).then(function (res) {
      state.orders = res.body.orders || [];
      if (selectKey !== undefined) state.selectedKey = selectKey;
      if (!selectedOrder()) state.selectedKey = null;
      render();
    });
  }

  /* --- Delete dialog ------------------------------------------------------------ */

  var deleteDialog = document.getElementById("po-delete-dialog");
  function openDelete(order) {
    var list = deleteDialog.querySelector("[data-delete-details]");
    var alertBox = deleteDialog.querySelector("[data-delete-alert]");
    list.textContent = "";
    [["PO No", order.po_no], ["Date", dmy(order.order_date)], ["Party", order.party_name || order.party_code], ["PO Amount", order.net_amount]]
      .forEach(function (p) {
        var dt = document.createElement("dt"), dd = document.createElement("dd");
        dt.textContent = p[0]; dd.textContent = p[1];
        list.append(dt, dd);
      });
    alertBox.hidden = true;
    deleteDialog.querySelector("[data-delete-yes]").disabled = false;
    deleteDialog.showModal();
    deleteDialog.querySelector("[data-delete-no]").focus();
  }
  deleteDialog.querySelector("[data-delete-no]").addEventListener("click", function () { deleteDialog.close(); });
  deleteDialog.querySelector("[data-delete-yes]").addEventListener("click", function () {
    var order = selectedOrder();
    var button = deleteDialog.querySelector("[data-delete-yes]");
    var alertBox = deleteDialog.querySelector("[data-delete-alert]");
    if (!order) return;
    button.disabled = true;
    post(root.dataset.deleteUrl, { key: order.key }).then(function (res) {
      if (res.ok) {
        deleteDialog.close();
        showToast(res.body.message);
        refresh(null);
      } else {
        alertBox.textContent = res.body.message || "Could not delete (error " + res.status + ").";
        alertBox.hidden = false;
        button.disabled = false;
      }
    });
  });

  /* --- Toolbar actions ----------------------------------------------------------- */

  var printOptionsDialog = document.getElementById("po-print-options-dialog");
  var copyCheckboxes = printOptionsDialog.querySelectorAll('input[name="po-copy-type"]');
  // Only one copy type makes sense at a time (same as the reference's checkbox
  // group, which only ever shows one ticked) -- checking one unchecks the rest.
  copyCheckboxes.forEach(function (box) {
    box.addEventListener("change", function () {
      if (box.checked) copyCheckboxes.forEach(function (other) { if (other !== box) other.checked = false; });
      else box.checked = true; // always exactly one selected, never zero
    });
  });
  function copyType() {
    var checked = Array.prototype.find.call(copyCheckboxes, function (b) { return b.checked; });
    return checked ? checked.value : "";
  }

  function printUrl(o, preview) {
    var url = root.dataset.printUrlTemplate.replace("__DIV__", encodeURIComponent(o.div)).replace("__PONO__", encodeURIComponent(o.po_no));
    var params = new URLSearchParams();
    if (preview) params.set("preview", "1");
    params.set("copy", copyType());
    return url + "?" + params.toString();
  }

  function pdfUrl(o) {
    var url = root.dataset.pdfUrlTemplate.replace("__DIV__", encodeURIComponent(o.div)).replace("__PONO__", encodeURIComponent(o.po_no));
    return url + "?copy=" + encodeURIComponent(copyType());
  }

  var whatsappDialog = document.getElementById("po-whatsapp-dialog");
  var whatsappParty = whatsappDialog.querySelector("[data-whatsapp-party]");
  var whatsappMobile = whatsappDialog.querySelector("[data-whatsapp-mobile]");
  var whatsappAlert = whatsappDialog.querySelector("[data-whatsapp-alert]");
  var whatsappOrder = null; // the order + its party_mobile, fetched fresh each time the dialog opens

  function normalizeMobile(raw) {
    var digits = (raw || "").replace(/\D/g, "");
    if (digits.length === 10) return "91" + digits;
    if (digits.length === 12 && digits.startsWith("91")) return digits;
    return null;
  }

  /* The list rows (selectedOrder()) don't carry the party's mobile number --
     only the full order detail does -- so this re-fetches it fresh each time,
     same endpoint the form's own "Modify"/"View" already use. */
  function openWhatsAppDialog() {
    var o = selectedOrder();
    if (!o) return;
    whatsappAlert.hidden = true;
    whatsappParty.value = o.party_name || o.party_code || "";
    whatsappMobile.value = "";
    whatsappOrder = o;
    var url = root.dataset.detailUrlTemplate.replace("__DIV__", encodeURIComponent(o.div)).replace("__PONO__", encodeURIComponent(o.po_no));
    fetchJson(url).then(function (res) {
      if (res.ok && whatsappOrder === o) whatsappMobile.value = res.body.party_mobile || "";
    });
    whatsappDialog.showModal();
    whatsappMobile.focus();
  }

  whatsappDialog.querySelector("[data-whatsapp-send]").addEventListener("click", function () {
    var mobile = normalizeMobile(whatsappMobile.value);
    if (!mobile) {
      whatsappAlert.textContent = "Enter a valid 10-digit mobile number.";
      whatsappAlert.hidden = false;
      return;
    }
    var o = whatsappOrder;
    var shareUrl = root.dataset.shareUrlTemplate.replace("__DIV__", encodeURIComponent(o.div)).replace("__PONO__", encodeURIComponent(o.po_no));
    var sendBtn = whatsappDialog.querySelector("[data-whatsapp-send]");
    sendBtn.disabled = true;
    // Open the tab NOW, synchronously, inside the click -- popup blockers only
    // allow window.open() during the click itself; calling it later, after the
    // fetch below resolves, is why this was silently doing nothing. Point this
    // tab at the real wa.me URL once the link is ready.
    var waTab = window.open("", "_blank");
    postJson(shareUrl, {}).then(function (res) {
      sendBtn.disabled = false;
      if (!res.ok) {
        if (waTab) waTab.close();
        whatsappAlert.textContent = res.body.message || "Could not create a share link for this order.";
        whatsappAlert.hidden = false;
        return;
      }
      var message = "Dear " + (whatsappParty.value || "Sir/Madam") + ",\n" +
        "Please find your purchase order below.\n" +
        "Purchase Order No: " + o.po_no + "\n" +
        "Download Purchase Order PDF:\n" + res.body.url + "\n" +
        "Thank you.\nSP MACHINES";
      whatsappDialog.close();
      var waUrl = "https://wa.me/" + mobile + "?text=" + encodeURIComponent(message);
      if (waTab) waTab.location.href = waUrl; else window.open(waUrl, "_blank");
    }).catch(function () {
      sendBtn.disabled = false;
      if (waTab) waTab.close();
      whatsappAlert.textContent = "Could not reach the server.";
      whatsappAlert.hidden = false;
    });
  });
  whatsappDialog.querySelector("[data-whatsapp-back]").addEventListener("click", function () { whatsappDialog.close(); });

  var actions = {
    add: function () { window.SPPurchaseOrderForm.open("add", null); },
    modify: function () { var o = selectedOrder(); if (o) window.SPPurchaseOrderForm.open("modify", o); },
    view: function () { var o = selectedOrder(); if (o) window.SPPurchaseOrderForm.open("view", o); },
    "delete": function () { var o = selectedOrder(); if (o) openDelete(o); },
    /* No longer prints immediately -- opens the VIEW / PRINT / PRINT PDF /
       WHATSAPP / EXIT dialog instead. */
    print: function () {
      var o = selectedOrder();
      if (!o) return;
      printOptionsDialog.querySelector("[data-print-po-no]").value = o.po_no;
      printOptionsDialog.querySelector("[data-print-po-amount]").value = o.net_amount;
      printOptionsDialog.showModal();
    },
    exit: function () { window.location.href = root.dataset.exitUrl; },
  };
  root.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function (e) { var fn = actions[btn.dataset.action]; if (fn) fn(e); });
  });
  printOptionsDialog.querySelectorAll("[data-print-action]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var action = btn.dataset.printAction;
      if (action === "exit") { printOptionsDialog.close(); return; }
      var o = selectedOrder();
      if (!o) return;
      printOptionsDialog.close();
      if (action === "whatsapp") openWhatsAppDialog();
      else if (action === "pdf") window.open(pdfUrl(o), "_blank");
      else window.open(printUrl(o, action === "preview"), "_blank");
    });
  });

  window.SPPurchaseOrderMaster = {
    refresh: refresh, post: post, postJson: postJson, fetchJson: fetchJson, dmy: dmy, showToast: showToast,
    // Opens the VIEW / PRINT / PRINT PDF / WHATSAPP / EXIT dialog for whichever
    // order is currently selected -- used right after Add/Modify saves so the
    // print options come up immediately instead of requiring a separate click.
    printSelected: function () { actions.print(); },
  };

  render();
})();
