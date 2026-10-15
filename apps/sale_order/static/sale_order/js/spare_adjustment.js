/* Sale Order > Spare Order Adjustment: tick pending order lines of a party and mark them adjusted. */
(function () {
  "use strict";

  var root = document.querySelector("[data-spare-adjustment]");
  if (!root) return;

  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var canEdit = root.dataset.canEdit === "1";
  var tbody = root.querySelector("[data-rows]");
  var emptyNote = root.querySelector("[data-empty]");
  var partySearch = root.querySelector("[data-party-search]");
  var partyCode = root.querySelector("[data-party-code]");
  var runDate = root.querySelector("[data-run-date]");
  var toast = document.querySelector("[data-toast]");
  var initial = JSON.parse(document.getElementById("sa-initial-data").textContent);
  var lines = [];

  function showToast(message, kind) {
    toast.textContent = message;
    toast.className = "toast toast--" + (kind || "success") + " is-visible";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () { toast.classList.remove("is-visible"); }, 3500);
  }

  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (cls) td.className = cls;
    return td;
  }

  function dmy(iso) {
    if (!iso) return "";
    var p = String(iso).split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : iso;
  }

  function show() {
    if (!partyCode.value) { showToast("Select a party first.", "error"); return; }
    var params = new URLSearchParams();
    params.set("party_code", partyCode.value);
    params.set("as_on", window.DateMask.toIso(runDate.value));
    fetch(root.dataset.dataUrl + "?" + params.toString(), { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        tbody.textContent = "";
        if (!res.ok) { showToast(res.body.message || "Could not load the orders.", "error"); return; }
        lines = res.body.rows.map(function (r) { return Object.assign({ adjust: false }, r); });
        lines.forEach(function (l, i) {
          var tr = document.createElement("tr");
          var box = document.createElement("input");
          box.type = "checkbox";
          box.disabled = !canEdit;
          box.addEventListener("change", function () { lines[i].adjust = box.checked; });
          var td = document.createElement("td");
          td.appendChild(box);
          tr.append(td, cell(l.order_no, "master-table__code"), cell(dmy(l.order_date)), cell(l.item_name),
            cell(l.ordered, "num"), cell(l.issued, "num"), cell(l.pending, "num"));
          tbody.appendChild(tr);
        });
        emptyNote.hidden = lines.length > 0;
        if (!lines.length) emptyNote.textContent = "No pending order lines for this party.";
      });
  }

  function confirm() {
    var ticked = lines.filter(function (l) { return l.adjust; });
    if (!ticked.length) { showToast("Tick at least one order line.", "error"); return; }
    window.askConfirm("Are You Sure?", function () {
      fetch(root.dataset.saveUrl, {
        method: "POST", credentials: "same-origin",
        headers: { "X-CSRFToken": csrf, "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
        body: JSON.stringify({ party_code: partyCode.value, lines: lines.map(function (l) {
          return { order_no: l.order_no, div: l.div, item_code: l.item_code, adjust: l.adjust };
        }) }),
      }).then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
        .then(function (res) {
          if (!res.ok) { showToast(res.body.message || "Could not adjust.", "error"); return; }
          showToast(res.body.message);
          show();
        });
    });
  }

  window.HelpLookup.attach(partySearch, {
    endpoint: root.dataset.partiesUrl, resultsKey: "parties", valueField: "name",
    displayFields: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }],
    title: "Party",
    onSelect: function (p) { partyCode.value = p.code; partySearch.value = p.name; show(); },
  });

  runDate.value = window.DateMask.toDisplay(initial.run_date);
  root.querySelector("[data-show]").addEventListener("click", show);
  root.querySelector("[data-confirm]").addEventListener("click", confirm);
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });
})();
