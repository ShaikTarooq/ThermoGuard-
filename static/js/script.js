/**
 * ThermoGuard Enterprise v4.0
 * Shared front-end behavior: sidebar toggle for mobile/responsive nav.
 * Page-specific logic lives in dashboard.js / analytics.js / history.js.
 */

(function () {
  const toggle = document.getElementById("sidebarToggle");
  const sidebar = document.getElementById("sidebar");

  if (toggle && sidebar) {
    toggle.addEventListener("click", function () {
      sidebar.classList.toggle("open");
    });

    document.addEventListener("click", function (e) {
      const isNarrow = window.innerWidth <= 860;
      if (!isNarrow) return;
      if (sidebar.classList.contains("open") &&
          !sidebar.contains(e.target) &&
          !toggle.contains(e.target)) {
        sidebar.classList.remove("open");
      }
    });
  }
})();

/* Shared formatting helpers used across dashboard/analytics/history scripts */
function formatStatusLabel(level) {
  const labels = {
    normal: "Normal",
    elevated: "Elevated",
    warning: "Warning",
    critical: "Critical",
  };
  return labels[level] || level;
}

function formatTimestamp(ts) {
  if (!ts) return "—";
  // SQLite ISO-ish string -> readable
  const d = new Date(ts.replace(" ", "T"));
  if (isNaN(d.getTime())) return ts;
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}
