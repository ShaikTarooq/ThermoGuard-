/**
 * ThermoGuard Enterprise v4.0
 * Dashboard Script
 */

(function () {

    const POLL_MS = 4000;

    const liveTempEl = document.getElementById("liveTemp");
    const liveHumidityEl = document.getElementById("liveHumidity");
    const lastUpdatedEl = document.getElementById("lastUpdated");
    const statusBadge = document.getElementById("statusBadge");

    const thermoFill = document.getElementById("thermoFill");
    const thermoBulb = document.getElementById("thermoBulb");

    const fanItem = document.getElementById("fanControlItem");
    const acItem = document.getElementById("acControlItem");

    const fanState = document.getElementById("fanState");
    const acState = document.getElementById("acState");

    const fanIcon = document.getElementById("fanIcon");

    const TEMP_MIN = 15;
    const TEMP_MAX = 45;
    const TUBE_TOP = 25;
    const TUBE_BOTTOM = 190;

    const STATUS_COLORS = {
        normal: "#5FCF6F",
        elevated: "#2B95E9",
        warning: "#F2C037",
        critical: "#F1707A"
    };

    function formatStatusLabel(status) {
        return status.charAt(0).toUpperCase() + status.slice(1);
    }

    function tempToY(temp) {

        temp = Math.max(TEMP_MIN, Math.min(TEMP_MAX, temp));

        const ratio =
            (temp - TEMP_MIN) /
            (TEMP_MAX - TEMP_MIN);

        return TUBE_BOTTOM -
            ratio * (TUBE_BOTTOM - TUBE_TOP);
    }

    function updateGauge(data) {

        const color =
            STATUS_COLORS[data.status_level] ||
            STATUS_COLORS.normal;

        liveTempEl.textContent =
            data.temperature.toFixed(1);

        liveTempEl.style.color = color;

        liveHumidityEl.textContent =
            data.humidity.toFixed(0) + "%";

        lastUpdatedEl.textContent =
            "Updated " + data.timestamp;

        statusBadge.textContent =
            formatStatusLabel(data.status_level);

        statusBadge.className =
            "badge badge-status level-" +
            data.status_level;

        const y = tempToY(data.temperature);

        thermoFill.setAttribute("y", y);
        thermoFill.setAttribute(
            "height",
            TUBE_BOTTOM - y + 12
        );

        thermoFill.setAttribute("fill", color);
        thermoBulb.setAttribute("fill", color);

        fanItem.classList.toggle("is-on", data.fan_on);
        acItem.classList.toggle("is-on", data.ac_on);

        fanState.textContent =
            data.fan_on ? "ON" : "OFF";

        acState.textContent =
            data.ac_on ? "ON" : "OFF";

        fanIcon.classList.toggle(
            "spin",
            data.fan_on
        );
    }

    async function pollLive() {

        try {

            const res =
                await fetch("/api/live");

            const data =
                await res.json();

            updateGauge(data);

        } catch (e) {

            console.log(e);

        }

    }

    /* ---------------- CHART ---------------- */

    const canvas =
        document.getElementById("liveTrendChart");

    const ctx =
        canvas.getContext("2d");

    const trendChart = new Chart(ctx, {

        type: "line",

        data: {

            labels: [],

            datasets: [

                {

                    data: [],

                    borderColor: "#2B95E9",

                    backgroundColor:
                        "rgba(43,149,233,.15)",

                    fill: true,

                    tension: .35,

                    pointRadius: 0,

                    borderWidth: 3

                }

            ]

        },

        options: {

            responsive: true,

            maintainAspectRatio: false,

            interaction: {

                intersect: false,

                mode: "index"

            },

            plugins: {

                legend: {

                    display: false

                }

            },

            scales: {

                x: {

                    grid: {

                        display: false

                    },

                    ticks: {

                        color: "#8A8A8A"

                    }

                },

                y: {

                    beginAtZero: false,

                    grid: {

                        color: "#333"

                    },

                    ticks: {

                        color: "#8A8A8A"

                    }

                }

            }

        }

    });

    async function loadTrendChart() {

        try {

            const response =
                await fetch("/api/readings?limit=60");

            const rows =
                await response.json();

            trendChart.data.labels =
                rows.map(r => {

                    return new Date(r.timestamp)
                        .toLocaleTimeString([], {

                            hour: "2-digit",

                            minute: "2-digit"

                        });

                });

            trendChart.data.datasets[0].data =
                rows.map(r => r.temperature);

            trendChart.update();

        } catch (e) {

            console.log(e);

        }

    }

    pollLive();
    loadTrendChart();

    setInterval(pollLive, POLL_MS);
    setInterval(loadTrendChart, POLL_MS);

})();