/* Accounts > Data Entry > Voucher Printing: renders one saved voucher
   (CV/BV/JV) as a traditional two-column accounting voucher -- direct port
   of the VFP "VOUCHER PRINTING" report. */
(function () {
  "use strict";

  var root = document.querySelector("[data-voucher-printing]");
  if (!root) return;

  var ttype = root.querySelector("[data-ttype]");
  var voucherDate = root.querySelector("[data-voucher-date]");
  var voucherNo = root.querySelector("[data-voucher-no]");
  var alertBox = root.querySelector("[data-alert]");
  var result = root.querySelector("[data-result]");
  var rows = root.querySelector("[data-r-rows]");

  function show(msg) {
    alertBox.textContent = msg || "";
    alertBox.hidden = !msg;
  }
  function cell(text, cls) {
    var td = document.createElement("td");
    td.textContent = text == null ? "" : text;
    if (cls) td.className = cls;
    return td;
  }
  function dmyToIso(d) {
    var p = String(d || "").split(/[-/]/);
    return p.length === 3 ? p[2] + "-" + p[1] + "-" + p[0] : d;
  }
  function dmy(iso) {
    var p = String(iso || "").split("-");
    return p.length === 3 ? p[2] + "-" + p[1] + "-" + p[0] : "";
  }
  root.querySelectorAll("[data-date-mask]").forEach(function (input) {
    input.addEventListener("input", function () {
      var digits = input.value.replace(/\D/g, "").slice(0, 8);
      var out = digits.slice(0, 2);
      if (digits.length > 2) out += "-" + digits.slice(2, 4);
      if (digits.length > 4) out += "-" + digits.slice(4, 8);
      input.value = out;
    });
  });

  function query() {
    var params = new URLSearchParams();
    params.set("ttype", ttype.value);
    params.set("voucher_date", dmyToIso(voucherDate.value));
    params.set("voucher_no", voucherNo.value.trim());
    return params.toString();
  }

  var printBtn = root.querySelector("[data-print]");

  function view() {
    show("");
    printBtn.disabled = true;
    if (!voucherNo.value.trim()) { show("Enter a Voucher No."); return; }
    fetch(root.dataset.dataUrl + "?" + query(), { credentials: "same-origin" })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        if (!res.ok) { show(res.body.message || "Could not load the voucher."); result.hidden = true; return; }
        var d = res.body;
        root.querySelector("[data-r-date]").textContent = dmy(d.voucher_date);
        root.querySelector("[data-r-no]").textContent = d.voucher_no;
        root.querySelector("[data-r-label]").textContent = d.label;
        root.querySelector("[data-r-total-debit]").textContent = d.total_debit;
        root.querySelector("[data-r-total-credit]").textContent = d.total_credit;
        rows.textContent = "";
        d.lines.forEach(function (l) {
          var tr = document.createElement("tr");
          tr.append(cell(l.code), cell(l.scode), cell(l.account), cell(l.debit, "num"), cell(l.credit, "num"));
          rows.appendChild(tr);
          var prefix = l.dc === "D" ? "TO " : "BY ";
          var ntr = document.createElement("tr");
          ntr.className = "vp-narration";
          var ntd = document.createElement("td");
          ntd.colSpan = 5;
          ntd.textContent = prefix + l.narration1 + (l.narration2 ? " " + l.narration2 : "");
          ntr.appendChild(ntd);
          rows.appendChild(ntr);
        });
        result.hidden = false;
        printBtn.disabled = false;
      });
  }

  root.querySelector("[data-view]").addEventListener("click", view);
  printBtn.addEventListener("click", function () { window.print(); });
  root.querySelector("[data-excel]").addEventListener("click", function () {
    if (!voucherNo.value.trim()) { show("Enter a Voucher No."); return; }
    window.location.href = root.dataset.exportUrl + "?" + query();
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  voucherDate.value = new Date().toLocaleDateString("en-GB").split("/").join("-");
})();
