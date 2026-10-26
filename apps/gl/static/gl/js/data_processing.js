/* Accounts > Final Accounts > Data Processing -- RUN DATE + OK/EXIT, matching
   the VFP form's own screenshot. OK posts to a real endpoint; see
   apps.gl.data_processing's own module docstring for why that endpoint
   currently refuses to actually write anything (the VFP "do trial with
   ..." procedure and the "trial" snapshot table's schema were never
   confirmed). */
(function () {
  "use strict";

  var root = document.querySelector("[data-data-processing]");
  if (!root) return;

  var csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;
  var runDate = root.querySelector("[data-run-date]");
  var alertBox = root.querySelector("[data-alert]");

  function show(msg, isError) {
    alertBox.textContent = msg || "";
    alertBox.hidden = !msg;
    alertBox.classList.toggle("pe-alert--ok", Boolean(msg) && !isError);
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

  root.querySelector("[data-ok]").addEventListener("click", function () {
    show("");
    fetch(root.dataset.processUrl, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrf, "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify({ run_date: dmyToIso(runDate.value) }),
    })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) { show(res.body.message || "Could not process.", !res.ok); });
  });
  root.querySelector("[data-exit]").addEventListener("click", function () { window.location.href = root.dataset.exitUrl; });

  var initial = JSON.parse(document.getElementById("dp-initial-data").textContent);
  runDate.value = dmy(initial.run_date);
})();
