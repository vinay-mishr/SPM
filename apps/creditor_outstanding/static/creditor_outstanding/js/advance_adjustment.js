/* Creditor Outstanding > Advance Adjustment: pick a party, enter amounts against pending bills, CONFIRM. */
(function () {
  "use strict";

  var root = document.querySelector("[data-aa]");
  if (!root) return;

  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var partySearch = root.querySelector("[data-party-search]");
  var partyCode = root.querySelector("[data-party-code]");
  var advance = root.querySelector("[data-advance]");
  var rows = root.querySelector("[data-rows]");
  var alertBox = root.querySelector("[data-alert]");
  var bills = [];
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

  function render() {
    rows.textContent = "";
    if (!bills.length) {
      var tr = document.createElement("tr");
      tr.className = "empty";
      var td = document.createElement("td");
      td.colSpan = 7;
      td.textContent = "No pending bill for this party.";
      tr.appendChild(td);
      rows.appendChild(tr);
      return;
    }
    bills.forEach(function (b, i) {
      var tr = document.createElement("tr");
      var adj = document.createElement("input");
      adj.className = "num";
      adj.value = b.adjusted || "";
      adj.addEventListener("input", function () {
        var v = Number(adj.value) || 0;
        if (v > Number(b.balance)) { show("Adjustment is more than the bill balance."); adj.value = ""; v = 0; }
        b.adjusted = adj.value;
      });
      tr.append(cell(i + 1), cell(b.bill_no), cell(dmy(b.bill_date)), cell(b.bill_amount, "num"),
        cell((Number(b.bill_amount) - Number(b.balance)).toFixed(2), "num"), cell(b.balance, "num"));
      var td = document.createElement("td");
      td.appendChild(adj);
      tr.appendChild(td);
      rows.appendChild(tr);
    });
  }

  function post(url, data) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrf, "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(data || {}),
    }).then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); });
  }

  function loadParty(p) {
    partyCode.value = p.code;
    partySearch.value = p.name;
    fetch(root.dataset.dataUrl + "?party_code=" + encodeURIComponent(p.code), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        advance.value = d.advance;
        bills = d.bills.map(function (b) { return Object.assign({}, b, { adjusted: "" }); });
        render();
        if (Number(d.advance) <= 0) show("No Advance Paid to this Party.");
        else if (!bills.length) show("No Pending Bill for this Party.");
      });
  }

  window.HelpLookup.attach(partySearch, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Party",
    onSelect: loadParty,
  });

  root.querySelector("[data-add]").addEventListener("click", function () {
    partySearch.value = ""; partyCode.value = ""; advance.value = "0.00";
    bills = []; render(); show("");
    root.querySelector("[data-form]").hidden = false;
    root.querySelector("[data-confirm]").hidden = false;
    root.querySelector("[data-exit]").hidden = false;
    partySearch.focus();
  });

  root.querySelector("[data-confirm]").addEventListener("click", function () {
    if (!partyCode.value) { show("Select a party first."); return; }
    var lines = bills.filter(function (b) { return Number(b.adjusted) > 0; })
      .map(function (b) { return { bill_no: b.bill_no, adjusted: b.adjusted }; });
    if (!lines.length) { show("Enter an amount to adjust."); return; }
    askConfirm("Are You Sure?", function () {
      post(root.dataset.saveUrl, { party_code: partyCode.value, lines: lines }).then(function (res) {
        if (!res.ok) { show(res.body.message || "Could not adjust the advance."); return; }
        window.alert(res.body.message);
        loadParty({ code: partyCode.value, name: partySearch.value });
      });
    });
  });

  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });
  render();
})();
