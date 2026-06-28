/**
 * ThermoGuard Enterprise v4.0 — History logic
 * Debounced search + filters against /api/history, client-side
 * pagination controls, and a CSV export that honors active filters.
 */

(function () {
  let currentPage = 1;
  let debounceTimer = null;

  const searchInput = document.getElementById("searchInput");
  const statusFilter = document.getElementById("statusFilter");
  const fromDate = document.getElementById("fromDate");
  const toDate = document.getElementById("toDate");
  const tbody = document.getElementById("historyTbody");
  const resultsSummary = document.getElementById("resultsSummary");
  const pagination = document.getElementById("pagination");

  function buildParams(page) {
    const params = new URLSearchParams();
    if (searchInput.value.trim()) params.set("search", searchInput.value.trim());
    if (statusFilter.value) params.set("status", statusFilter.value);
    if (fromDate.value) params.set("from", fromDate.value);
    if (toDate.value) params.set("to", toDate.value);
    params.set("page", page);
    params.set("per_page", 25);
    return params;
  }

  function statusChip(level) {
    return `<span class="status-chip ${level}">${formatStatusLabel(level)}</span>`;
  }

  function onoffChip(value) {
    const cls = value === "ON" ? "on" : "off";
    return `<span class="onoff-chip ${cls}">${value}</span>`;
  }

  async function loadHistory(page = 1) {
    currentPage = page;
    tbody.innerHTML = `<tr><td colspan="7" class="table-loading">Loading readings…</td></tr>`;

    try {
      const params = buildParams(page);
      const res = await fetch(`/api/history?${params.toString()}`);
      const data = await res.json();

      if (data.rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="table-empty">No readings match these filters.</td></tr>`;
        resultsSummary.textContent = "0 results";
        pagination.innerHTML = "";
        return;
      }

      tbody.innerHTML = data.rows.map(r => `
        <tr>
          <td>${formatTimestamp(r.timestamp)}</td>
          <td>${escapeHtml(r.sensor_name)}</td>
          <td>${r.temperature.toFixed(1)}</td>
          <td>${r.humidity.toFixed(1)}</td>
          <td>${onoffChip(r.fan_status)}</td>
          <td>${onoffChip(r.ac_status)}</td>
          <td>${statusChip(r.status_level)}</td>
        </tr>
      `).join("");

      const start = (data.page - 1) * data.per_page + 1;
      const end = Math.min(data.page * data.per_page, data.total);
      resultsSummary.textContent = `Showing ${start}–${end} of ${data.total} readings`;

      renderPagination(data.page, data.total_pages);
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="7" class="table-empty">Could not load history. Please try again.</td></tr>`;
    }
  }

  function renderPagination(page, totalPages) {
    let html = "";
    html += `<button class="page-btn" id="prevPageBtn" ${page <= 1 ? "disabled" : ""}>‹</button>`;

    const windowSize = 5;
    let start = Math.max(1, page - Math.floor(windowSize / 2));
    let end = Math.min(totalPages, start + windowSize - 1);
    start = Math.max(1, end - windowSize + 1);

    for (let p = start; p <= end; p++) {
      html += `<button class="page-btn ${p === page ? "active" : ""}" data-page="${p}">${p}</button>`;
    }
    html += `<button class="page-btn" id="nextPageBtn" ${page >= totalPages ? "disabled" : ""}>›</button>`;
    pagination.innerHTML = html;

    pagination.querySelectorAll("[data-page]").forEach(btn => {
      btn.addEventListener("click", () => loadHistory(parseInt(btn.dataset.page, 10)));
    });
    const prevBtn = document.getElementById("prevPageBtn");
    const nextBtn = document.getElementById("nextPageBtn");
    if (prevBtn) prevBtn.addEventListener("click", () => loadHistory(page - 1));
    if (nextBtn) nextBtn.addEventListener("click", () => loadHistory(page + 1));
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function debouncedReload() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => loadHistory(1), 350);
  }

  searchInput.addEventListener("input", debouncedReload);
  statusFilter.addEventListener("change", () => loadHistory(1));
  fromDate.addEventListener("change", () => loadHistory(1));
  toDate.addEventListener("change", () => loadHistory(1));

  document.getElementById("clearFiltersBtn").addEventListener("click", () => {
    searchInput.value = "";
    statusFilter.value = "";
    fromDate.value = "";
    toDate.value = "";
    loadHistory(1);
  });

  document.getElementById("exportCsvBtn").addEventListener("click", () => {
    const params = buildParams(1);
    params.delete("page");
    params.delete("per_page");
    window.location.href = `/api/history/export?${params.toString()}`;
  });

  loadHistory(1);
})();
