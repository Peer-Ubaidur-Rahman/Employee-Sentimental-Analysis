/* dashboard_charts.js - renders Chart.js charts from server-provided JSON (#chart-data).
   No numbers are hard-coded here: everything comes from MySQL via the Flask view. */
(function () {
  "use strict";
  var node = document.getElementById("chart-data");
  if (!node || typeof Chart === "undefined") return;
  var data = JSON.parse(node.textContent);
  var C = { pos: "#16845B", neu: "#9A6B13", neg: "#C53E4D", grid: "#E4E8EF", text: "#687386" };
  Chart.defaults.font.family = '"Inter", system-ui, sans-serif';
  Chart.defaults.font.size = 12;
  Chart.defaults.color = C.text;

  var dist = document.getElementById("distChart");
  if (dist && data.distribution) {
    new Chart(dist, {
      type: "doughnut",
      data: { labels: ["Positive", "Neutral", "Negative"],
              datasets: [{ data: data.distribution, backgroundColor: [C.pos, C.neu, C.neg], borderColor: "#fff", borderWidth: 3 }] },
      options: { maintainAspectRatio: false, cutout: "68%", plugins: { legend: { position: "bottom", labels: { usePointStyle: true } } } }
    });
  }

  var trend = document.getElementById("trendChart");
  if (trend && data.trend) {
    var line = function (label, key, color) {
      return { label: label, data: data.trend[key], borderColor: color, backgroundColor: color, tension: 0.3,
               borderWidth: 2, pointRadius: data.trend.labels.length > 45 ? 0 : 3 };
    };
    new Chart(trend, {
      type: "line",
      data: { labels: data.trend.labels,
              datasets: [line("Positive", "positive", C.pos), line("Neutral", "neutral", C.neu), line("Negative", "negative", C.neg)] },
      options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
                 plugins: { legend: { position: "bottom", labels: { usePointStyle: true } } },
                 scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } },
                           y: { beginAtZero: true, grid: { color: C.grid }, ticks: { precision: 0 } } } }
    });
  }

  var dept = document.getElementById("deptChart");
  if (dept && data.departments && data.departments.length) {
    var d = data.departments;
    new Chart(dept, {
      type: "bar",
      data: { labels: d.map(function (x) { return x.name; }),
              datasets: [{ label: "Positive %", data: d.map(function (x) { return x.pos; }), backgroundColor: C.pos },
                         { label: "Neutral %", data: d.map(function (x) { return x.neu; }), backgroundColor: C.neu },
                         { label: "Negative %", data: d.map(function (x) { return x.neg; }), backgroundColor: C.neg }] },
      options: { indexAxis: "y", maintainAspectRatio: false, plugins: { legend: { position: "bottom", labels: { usePointStyle: true } } },
                 scales: { x: { stacked: true, max: 100, grid: { color: C.grid } }, y: { stacked: true, grid: { display: false } } } }
    });
  }
})();
