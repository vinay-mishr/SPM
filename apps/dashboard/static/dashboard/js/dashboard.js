(function () {
  "use strict";

  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  // Draws each bar's value centred just above it -- avoids pulling in a plugin
  // for one label, and the dashboard hides the Y axis so this is the only way
  // to read a bar's value at a glance.
  var barValueLabels = {
    id: "barValueLabels",
    afterDatasetsDraw: function (chart) {
      var ctx = chart.ctx;
      ctx.save();
      ctx.font = "600 12px " + (css("--font-body") || "sans-serif");
      ctx.fillStyle = css("--text-primary") || "#172B35";
      ctx.textAlign = "center";
      ctx.textBaseline = "bottom";
      chart.data.datasets.forEach(function (dataset, i) {
        var meta = chart.getDatasetMeta(i);
        meta.data.forEach(function (bar, j) {
          var value = dataset.data[j];
          if (value) ctx.fillText(value, bar.x, bar.y - 6);
        });
      });
      ctx.restore();
    },
  };

  function renderOrdersOverview() {
    var canvas = document.getElementById("ordersOverviewChart");
    if (!canvas || !window.Chart) return;
    fetch(canvas.dataset.url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        new Chart(canvas, {
          type: "bar",
          plugins: [barValueLabels],
          data: {
            labels: data.labels,
            datasets: [{
              label: "Orders",
              data: data.values,
              backgroundColor: css("--primary-dark") || "#6FA982",
              borderRadius: 4,
              maxBarThickness: 36,
            }],
          },
          options: {
            responsive: true,
            layout: { padding: { top: 20 } },
            plugins: {
              legend: { display: false },
              tooltip: { callbacks: { label: function (ctx) { return ctx.parsed.y + " order" + (ctx.parsed.y === 1 ? "" : "s"); } } },
            },
            scales: {
              y: { display: false, beginAtZero: true },
              x: { grid: { display: false }, ticks: { font: { size: 10 }, maxRotation: 0, autoSkip: false } },
            },
          },
        });
      })
      .catch(function () { /* chart left blank on failure */ });
  }

  document.addEventListener("DOMContentLoaded", function () {
    renderOrdersOverview();
  });
})();
