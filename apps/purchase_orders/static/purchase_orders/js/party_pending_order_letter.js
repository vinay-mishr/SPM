/* Party Pending Order Letter — read-only. Old VFP form: PARTY PENDING ORDER LETTER. */
(function () {
  "use strict";

  var root = document.querySelector("[data-pending-order-letter]");
  if (!root) return;

  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var runDate = root.querySelector("[data-run-date]");
  var partyCode = root.querySelector("[data-party-code]");
  var partySearch = root.querySelector("[data-party-search]");
  var printOptionsDialog = document.getElementById("pol-print-options-dialog");
  var toast = document.querySelector("[data-toast]");

  var initial = JSON.parse(document.getElementById("pol-initial-data").textContent);
  var currentParty = null; // last-loaded party details (name, mobile, ...), for WhatsApp
  var currentLines = []; // last-loaded pending order lines, for the WhatsApp message's order numbers
  var csrfToken = root.querySelector("input[name=csrfmiddlewaretoken]").value;

  function postJson(url, data) {
    return fetch(url, {
      method: "POST", credentials: "same-origin", body: JSON.stringify(data),
      headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json" },
    }).then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, status: r.status, body: b }; }); });
  }

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function dmy(iso) {
    if (!iso) return "";
    var p = String(iso).split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : iso;
  }

  // Old VFP: EMPTY(Party Name) -> clear Party Code.
  partySearch.addEventListener("input", function () {
    if (!partySearch.value.trim()) { partyCode.value = ""; render([]); }
  });

  if (window.HelpLookup) {
    window.HelpLookup.attach(partySearch, {
      endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
      displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }], title: "Party",
      onSelect: function (row) { partyCode.value = row.code; search(); },
    });
  }

  function cell(text, className) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (className) td.className = className;
    return td;
  }

  function render(lines, party) {
    currentParty = party || null;
    currentLines = lines || [];
    tbody.textContent = "";
    lines.forEach(function (line) {
      var tr = document.createElement("tr");
      tr.append(
        cell(line.ord_no),
        cell(dmy(line.ord_date)),
        cell(line.item_code, "master-table__code"),
        cell(line.item_name),
        cell(line.pending_qty, "num"),
        cell(dmy(line.despatch_date)),
        cell(line.delay_days == null ? "" : line.delay_days, "num")
      );
      tbody.appendChild(tr);
    });
    emptyNote.hidden = lines.length > 0;
    emptyNote.textContent = partyCode.value.trim()
      ? "No pending orders for this party."
      : "Select a party to see its pending orders.";
  }

  function currentQuery() {
    var params = new URLSearchParams();
    params.set("party_code", partyCode.value.trim());
    params.set("run_date", window.DateMask.toIso(runDate.value));
    params.set("copy", copyType());
    return params;
  }

  var copyCheckboxes = printOptionsDialog.querySelectorAll('input[name="pol-copy-type"]');
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

  function search() {
    if (!partyCode.value.trim()) { render([]); return; }
    fetch(root.dataset.dataUrl + "?" + currentQuery().toString(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        if (!res.ok) { showToast(res.body.message || "Could not load the letter.", "error"); return; }
        render(res.body.lines || [], res.body.party);
      })
      .catch(function () { showToast("Could not reach the server.", "error"); });
  }

  runDate.addEventListener("change", search);
  root.querySelector("[data-excel]").addEventListener("click", function () {
    if (!partyCode.value.trim()) { showToast("Select a party first.", "error"); return; }
    window.location.href = root.dataset.exportUrl + "?" + currentQuery().toString();
  });
  /* Print button no longer prints immediately -- it opens the VIEW / PRINT /
     PRINT PDF / WHATSAPP / EXIT dialog instead. */
  root.querySelector("[data-print]").addEventListener("click", function () {
    if (!partyCode.value.trim()) { showToast("Select a party first.", "error"); return; }
    // Every distinct order number this reminder actually covers -- there can
    // be more than one, unlike the Purchase Order screen's single PO No.
    var ordNos = currentLines.reduce(function (acc, line) {
      if (line.ord_no && acc.indexOf(line.ord_no) === -1) acc.push(line.ord_no);
      return acc;
    }, []);
    printOptionsDialog.querySelector("[data-print-ord-no]").value = ordNos.join(", ");
    printOptionsDialog.showModal();
  });

  function openPrintView() { window.open(root.dataset.printUrl + "?" + currentQuery().toString() + "&preview=1", "_blank"); }
  function openPrintDialog() { window.open(root.dataset.printUrl + "?" + currentQuery().toString(), "_blank"); }
  function openPrintPdf() { window.open(root.dataset.pdfUrl + "?" + currentQuery().toString(), "_blank"); }

  /* No WhatsApp Business API is configured in this project (no credentials in
     settings/.env), so there's no way to actually attach and send a PDF from
     the server -- doing that for real needs an approved WhatsApp Business
     integration, which is a separate setup task. Until then, this opens a
     print view the user can Save as PDF, and opens the supplier's WhatsApp
     chat with the message already filled in, and says clearly that the PDF
     still needs to be attached by hand. It never claims anything was sent. */
  var whatsappDialog = document.getElementById("pol-whatsapp-dialog");
  var whatsappParty = whatsappDialog.querySelector("[data-whatsapp-party]");
  var whatsappMobile = whatsappDialog.querySelector("[data-whatsapp-mobile]");
  var whatsappAlert = whatsappDialog.querySelector("[data-whatsapp-alert]");

  /* Opens a small dialog with the party's name and its mobile number -- fetched
     from the party record, but editable here (a different number, a typo in
     the master record, etc.), so the user confirms exactly who this goes to
     before anything opens. Clicking "Send on WhatsApp" is what actually acts. */
  function shareOnWhatsApp() {
    if (!partyCode.value.trim()) { showToast("Select a party first.", "error"); return; }
    whatsappAlert.hidden = true;
    whatsappParty.value = (currentParty && currentParty.name) || "";
    whatsappMobile.value = (currentParty && currentParty.mobile) || "";
    whatsappDialog.showModal();
    whatsappMobile.focus();
  }

  function normalizeMobile(raw) {
    var digits = (raw || "").replace(/\D/g, "");
    if (digits.length === 10) return "91" + digits; // bare 10-digit Indian number -> add the country code
    if (digits.length === 12 && digits.startsWith("91")) return digits;
    return null;
  }

  whatsappDialog.querySelector("[data-whatsapp-send]").addEventListener("click", function () {
    var mobile = normalizeMobile(whatsappMobile.value);
    if (!mobile) {
      whatsappAlert.textContent = "Enter a valid 10-digit mobile number.";
      whatsappAlert.hidden = false;
      return;
    }
    if (!currentLines.length) {
      whatsappAlert.textContent = "No pending orders to share.";
      whatsappAlert.hidden = false;
      return;
    }
    var sendBtn = whatsappDialog.querySelector("[data-whatsapp-send]");
    sendBtn.disabled = true;
    // Open the tab NOW, synchronously, inside the click -- popup blockers only
    // allow window.open() during the click itself; calling it later, once the
    // fetch below resolves, is why this was silently doing nothing.
    var waTab = window.open("", "_blank");
    // One public share link for the whole reminder letter (not one per PO) --
    // the WhatsApp message carries the reminder text plus this single PDF
    // link, same as the reminder's own "Print PDF" button would produce.
    postJson(root.dataset.shareUrl, { party_code: partyCode.value.trim(), run_date: window.DateMask.toIso(runDate.value) })
      .then(function (res) {
        sendBtn.disabled = false;
        if (!res.ok) {
          if (waTab) waTab.close();
          whatsappAlert.textContent = res.body.message || "Could not create a share link.";
          whatsappAlert.hidden = false;
          return;
        }
        var ordNos = currentLines.reduce(function (acc, line) {
          if (line.ord_no && acc.indexOf(line.ord_no) === -1) acc.push(line.ord_no);
          return acc;
        }, []);
        var lines = [
          "Dear " + (whatsappParty.value || "Sir/Madam") + ",",
          "This is a reminder for your pending purchase order(s): " + ordNos.join(", ") + ".",
          "Please find the reminder details below.",
          "Download Reminder PDF:",
          res.body.url,
          "Thank you.",
          "SP MACHINES",
        ];
        whatsappDialog.close();
        var waUrl = "https://wa.me/" + mobile + "?text=" + encodeURIComponent(lines.join("\n"));
        if (waTab) waTab.location.href = waUrl; else window.open(waUrl, "_blank");
      })
      .catch(function () {
        sendBtn.disabled = false;
        if (waTab) waTab.close();
        whatsappAlert.textContent = "Could not reach the server.";
        whatsappAlert.hidden = false;
      });
  });
  whatsappDialog.querySelector("[data-whatsapp-back]").addEventListener("click", function () { whatsappDialog.close(); });

  printOptionsDialog.querySelectorAll("[data-print-action]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var action = btn.dataset.printAction;
      if (action === "exit") { printOptionsDialog.close(); return; }
      printOptionsDialog.close();
      if (action === "preview") openPrintView();
      else if (action === "pdf") openPrintPdf();
      else if (action === "whatsapp") shareOnWhatsApp();
      else openPrintDialog();
    });
  });

  root.querySelector("[data-exit]").addEventListener("click", function () {
    window.location.href = root.dataset.exitUrl;
  });

  runDate.value = window.DateMask.toDisplay(initial.run_date);
  render([]);
  partySearch.focus();
})();
