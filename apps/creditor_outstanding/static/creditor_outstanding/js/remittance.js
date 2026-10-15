/* Creditor Outstanding > Remittance: pick a vendor, select a payment, view or print the remittance letter. */
(function () {
  "use strict";

  var root = document.querySelector("[data-rm]");
  if (!root) return;

  var partySearch = root.querySelector("[data-party-search]");
  var partyCode = root.querySelector("[data-party-code]");
  var runDate = root.querySelector("[data-run-date]");
  var rows = root.querySelector("[data-rows]");
  var letter = root.querySelector("[data-letter]");
  var alertBox = root.querySelector("[data-alert]");
  var selected = null;
  var alertTimer = null;

  function show(msg) {
    alertBox.textContent = msg || "";
    alertBox.hidden = !msg;
    clearTimeout(alertTimer);
    if (msg) alertTimer = setTimeout(function () { alertBox.hidden = true; }, 5000);
  }

  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (cls) td.className = cls;
    return td;
  }

  function dmy(iso) {
    var p = String(iso || "").split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : "";
  }

  function getJson(url) {
    return fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); });
  }

  function loadPayments() {
    selected = null;
    letter.hidden = true;
    getJson(root.dataset.listUrl + "?party_code=" + encodeURIComponent(partyCode.value)).then(function (res) {
      rows.textContent = "";
      res.body.payments.forEach(function (p) {
        var tr = document.createElement("tr");
        tr.append(cell(dmy(p.date)), cell(p.chq_no), cell(p.amount, "num"));
        tr.addEventListener("click", function () {
          rows.querySelectorAll("tr").forEach(function (x) { x.classList.remove("is-sel"); });
          tr.classList.add("is-sel");
          selected = p;
        });
        rows.appendChild(tr);
      });
      if (!res.body.payments.length) {
        var empty = document.createElement("tr");
        empty.className = "empty";
        var td = document.createElement("td");
        td.colSpan = 3;
        td.textContent = "No payments for this party.";
        empty.appendChild(td);
        rows.appendChild(empty);
      }
    });
  }

  function buildLetter(d) {
    var box = document.createElement("div");
    box.className = "rm-page";
    var head = document.createElement("div");
    head.className = "rm-head";
    head.textContent = "DATE : " + dmy(d.run_date);
    box.appendChild(head);
    var addr = [d.party_name].concat(d.address || []);
    if (d.phone) addr.push("Phone : " + d.phone);
    addr.forEach(function (a) {
      var p = document.createElement("div");
      p.textContent = a;
      box.appendChild(p);
    });
    var body = [
      "SUBJECT : REMITTANCE OF PAYMENT", "", "Dear Sirs,", "",
      "We are pleased to enclose Cheque/Draft bearing No. " + d.chq_no + " Dt. " + dmy(d.pay_date) +
        " for Rs. " + d.total + ".", d.words, "",
      "Against your following Invoices",
    ];
    body.forEach(function (line) {
      var p = document.createElement("div");
      p.textContent = line;
      box.appendChild(p);
    });
    var table = document.createElement("table");
    table.className = "rm-table";
    table.innerHTML = "<thead><tr><th>BILL NO</th><th>BILL DATE</th><th class='num'>INV. AMT</th><th class='num'>DEBIT NOTE</th><th class='num'>AMT PAID</th></tr></thead>";
    var tbody = document.createElement("tbody");
    d.bills.forEach(function (b) {
      var tr = document.createElement("tr");
      tr.append(cell(b.bill_no), cell(dmy(b.bill_date)), cell(b.bill_amount, "num"), cell(b.dr_note, "num"), cell(b.amount_paid, "num"));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    box.appendChild(table);
    var closing = ["", "Kindly acknowledge the receipt.", "Thanking you,", "", "Yours Faithfully", "For " + (root.dataset.company || ""), "", "", "Authorised Signatory", "Accounts Deptt."];
    closing.forEach(function (line) {
      var p = document.createElement("div");
      p.textContent = line;
      box.appendChild(p);
    });
    return box;
  }

  function view() {
    if (!partyCode.value) { show("Select a party first."); return; }
    if (!selected) { show("Select a payment in the list first."); return; }
    var url = root.dataset.letterUrl + "?party_code=" + encodeURIComponent(partyCode.value) +
      "&chq_no=" + encodeURIComponent(selected.chq_no) + "&run_date=" + encodeURIComponent(window.DateMask.toIso(runDate.value));
    getJson(url).then(function (res) {
      if (!res.ok) { show(res.body.message || "Could not build the letter."); return; }
      letter.textContent = "";
      letter.appendChild(buildLetter(res.body));
      letter.hidden = false;
    });
  }

  window.HelpLookup.attach(partySearch, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Party",
    onSelect: function (row) {
      partyCode.value = row.code;
      partySearch.value = row.name;
      loadPayments();
    },
  });

  root.querySelector("[data-view]").addEventListener("click", view);
  root.querySelector("[data-print]").addEventListener("click", function () {
    if (letter.hidden) { view(); return; }
    window.print();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });
  runDate.value = window.DateMask.toDisplay(new Date().toISOString().slice(0, 10));
})();
