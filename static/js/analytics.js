/**
 * ThermoGuard Enterprise v4.0 — Analytics logic
 * Loads summary stats + chart data for a selected time period and
 * renders three Chart.js visualizations: temperature line, humidity
 * line, and a status-breakdown doughnut.
 */

(function () {
  let currentPeriod = "24h";
  let tempChart = null;
  let humidityChart = null;
  let statusDoughnut = null;

  const periodMinutesMap = {
    "1h": 60, "6h": 360, "24h": 1440, "7d": 10080, "30d": 43200,
  };

  function setActivePill(period) {
    document.querySelectorAll(".period-pill").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.period === period);
    });
  }

  async function loadStats(period) {
    const res = await fetch(`/api/stats?period=${period}`);
    const stats = await res.json();

    document.getElementById("statAvgTemp").textContent =
      stats.avg_temp !== null ? `${stats.avg_temp}°C` : "—";
    document.getElementById("statMinMax").textContent =
      stats.min_temp !== null ? `${stats.min_temp}° / ${stats.max_temp}°` : "— / —";
    document.getElementById("statAvgHumidity").textContent =
      stats.avg_humidity !== null ? `${stats.avg_humidity}%` : "—";
    document.getElementById("statFanPct").textContent = `${stats.fan_on_pct}%`;
    document.getElementById("statAcPct").textContent = `${stats.ac_on_pct}%`;
    document.getElementById("statCritical").textContent = stats.critical_count;

    return stats;
  }

  async function loadCharts(period) {
    const minutes = periodMinutesMap[period] || 1440;
    const res = await fetch(`/api/readings?minutes=${minutes}`);
    const rows = await res.json();

    const sampleRate = Math.max(1, Math.floor(rows.length / 200));
    const sampled = rows.filter((_, i) => i % sampleRate === 0);

    const labels = sampled.map(r => {
      const d = new Date(r.timestamp.replace(" ", "T"));
      if (isNaN(d.getTime())) return r.timestamp;
      if (minutes > 1440) {
        return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
      }
      return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
    });
    const temps = sampled.map(r => r.temperature);
    const humidity = sampled.map(r => r.humidity);

    renderTempChart(labels, temps);
    renderHumidityChart(labels, humidity);
    renderStatusDoughnut(rows);
  }

  function renderTempChart(labels, temps) {
    const ctx = document.getElementById("tempHistoryChart");
    const config = {
      type: "line",
      data: {
        labels: labels,
        datasets: [{
          label: "Temperature (°C)",
          data: temps,
          borderColor: "#2B95E9",
          backgroundColor: "rgba(43,149,233,0.12)",
          fill: true,
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { maxTicksLimit: 10, color: "#7D8389", font: { size: 11 } } },
          y: { grid: { color: "#33383D" }, ticks: { color: "#7D8389", font: { size: 11 } } },
        },
      },
    };
    if (tempChart) { tempChart.destroy(); }
    tempChart = new Chart(ctx, config);
  }

  function renderHumidityChart(labels, humidity) {
    const ctx = document.getElementById("humidityChart");
    const config = {
      type: "line",
      data: {
        labels: labels,
        datasets: [{
          label: "Humidity (%)",
          data: humidity,
          borderColor: "#5FCF6F",
          backgroundColor: "rgba(95,207,111,0.12)",
          fill: true,
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { maxTicksLimit: 8, color: "#7D8389", font: { size: 11 } } },
          y: { grid: { color: "#33383D" }, ticks: { color: "#7D8389", font: { size: 11 } } },
        },
      },
    };
    if (humidityChart) { humidityChart.destroy(); }
    humidityChart = new Chart(ctx, config);
  }

  function renderStatusDoughnut(rows) {
    const counts = { normal: 0, elevated: 0, warning: 0, critical: 0 };
    rows.forEach(r => { if (counts[r.status_level] !== undefined) counts[r.status_level]++; });

    const ctx = document.getElementById("statusDoughnut");
    const config = {
      type: "doughnut",
      data: {
        labels: ["Normal", "Elevated", "Warning", "Critical"],
        datasets: [{
          data: [counts.normal, counts.elevated, counts.warning, counts.critical],
          backgroundColor: ["#5FCF6F", "#2B95E9", "#F2C037", "#F1707A"],
          borderWidth: 0,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom", labels: { color: "#B7BCC1", font: { size: 12 }, boxWidth: 12 } },
        },
        cutout: "65%",
      },
    };
    if (statusDoughnut) { statusDoughnut.destroy(); }
    statusDoughnut = new Chart(ctx, config);
  }

  async function refreshAll(period) {
    currentPeriod = period;
    setActivePill(period);
    await Promise.all([loadStats(period), loadCharts(period)]);
  }

  document.getElementById("periodPills").addEventListener("click", (e) => {
    const btn = e.target.closest(".period-pill");
    if (!btn) return;
    refreshAll(btn.dataset.period);
  });

  refreshAll(currentPeriod);
  setInterval(() => refreshAll(currentPeriod), 30000);
})();
