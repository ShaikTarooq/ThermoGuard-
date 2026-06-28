"""
ThermoGuard Enterprise v4.0
A Flask-based temperature monitoring and climate-control simulation system.

Founder: Mohammed Tarooq S

This single-file backend intentionally keeps everything readable in one place:
- SQLite persistence (readings + events)
- A background thread that simulates a live temperature feed
- Hysteresis-based fan/AC control logic (avoids rapid relay flapping)
- JSON APIs consumed by the dashboard/analytics/history pages
- Session-based login (single demo account, see README)
"""

import csv
import io
import json
import math
import random
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, flash, Response, g
)
from werkzeug.security import generate_password_hash, check_password_hash

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

APP_NAME = "ThermoGuard Enterprise"
APP_VERSION = "4.0"
FOUNDER_NAME = "Mohammed Tarooq S"

DATABASE = "thermoguard.db"
SECRET_KEY = "thermoguard-enterprise-dev-secret-change-in-production"

# Control thresholds (degrees Celsius). Hysteresis gaps prevent the
# fan/AC from switching on and off every single reading when the
# temperature hovers right at a boundary.
FAN_ON_TEMP = 28.0
FAN_OFF_TEMP = 26.0
AC_ON_TEMP = 32.0
AC_OFF_TEMP = 29.5
CRITICAL_TEMP = 38.0

SIMULATION_INTERVAL_SECONDS = 4  # how often a new reading is generated

app = Flask(__name__)
app.secret_key = SECRET_KEY

# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE, check_same_thread=False)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def get_db_standalone():
    """A connection usable from the background simulation thread
    (outside of any Flask app/request context)."""
    db = sqlite3.connect(DATABASE, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db_standalone()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            sensor_name TEXT NOT NULL,
            temperature REAL NOT NULL,
            humidity REAL NOT NULL,
            fan_status TEXT NOT NULL,
            ac_status TEXT NOT NULL,
            status_level TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            message TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    db.commit()

    # Seed a default demo user if none exists yet.
    existing = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if existing == 0:
        db.execute(
            "INSERT INTO users (username, password_hash, full_name, created_at) VALUES (?, ?, ?, ?)",
            (
                "admin",
                generate_password_hash("admin123"),
                "Administrator",
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        db.commit()

    # Seed default settings if none exist.
    default_settings = {
        "fan_on_temp": str(FAN_ON_TEMP),
        "fan_off_temp": str(FAN_OFF_TEMP),
        "ac_on_temp": str(AC_ON_TEMP),
        "ac_off_temp": str(AC_OFF_TEMP),
        "critical_temp": str(CRITICAL_TEMP),
        "sensor_name": "Server Room A",
        "auto_control_enabled": "1",
        "temp_unit": "C",
    }
    for key, value in default_settings.items():
        db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )
    db.commit()
    db.close()


def get_setting(db, key, default=None):
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(db, key, value):
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    db.commit()


# --------------------------------------------------------------------------
# Simulation engine (runs in a background thread)
# --------------------------------------------------------------------------

class ThermalSimulator:
    """
    Simulates a realistic temperature curve using a slow sinusoidal base
    (day/night-ish drift) plus random noise, occasional "heat events", and
    feedback from whether the fan/AC are currently running (cooling pulls
    the simulated temperature back down).
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.current_temp = 27.5
        self.current_humidity = 45.0
        self.fan_on = False
        self.ac_on = False
        self.running = False
        self.thread = None
        self.tick = 0
        self.heat_event_remaining = 0

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        while self.running:
            self._step()
            time.sleep(SIMULATION_INTERVAL_SECONDS)

    def _step(self):
        with self.lock:
            self.tick += 1

            # Slow sinusoidal drift to mimic ambient cycles.
            base_drift = 1.4 * math.sin(self.tick / 40.0)

            # Random walk noise.
            noise = random.uniform(-0.35, 0.35)

            # Randomly trigger a "heat event" (e.g. equipment load spike).
            if self.heat_event_remaining <= 0 and random.random() < 0.02:
                self.heat_event_remaining = random.randint(5, 12)
            heat_event_push = 0.0
            if self.heat_event_remaining > 0:
                heat_event_push = random.uniform(0.4, 0.9)
                self.heat_event_remaining -= 1

            # Cooling feedback: if AC/fan are on, pull temperature down.
            cooling_pull = 0.0
            if self.ac_on:
                cooling_pull -= random.uniform(0.6, 1.0)
            elif self.fan_on:
                cooling_pull -= random.uniform(0.2, 0.4)

            new_temp = (
                self.current_temp
                + base_drift * 0.05
                + noise
                + heat_event_push
                + cooling_pull
            )
            # Clamp to a realistic equipment-room range.
            new_temp = max(18.0, min(45.0, new_temp))
            self.current_temp = round(new_temp, 2)

            # Humidity drifts gently and inversely correlates a little with AC use.
            humidity_noise = random.uniform(-0.6, 0.6)
            humidity_pull = -0.8 if self.ac_on else 0.0
            new_humidity = self.current_humidity + humidity_noise + humidity_pull * 0.1
            new_humidity = max(20.0, min(80.0, new_humidity))
            self.current_humidity = round(new_humidity, 1)

            self._apply_control_logic()
            temp_snapshot = self.current_temp
            humidity_snapshot = self.current_humidity
            fan_snapshot = self.fan_on
            ac_snapshot = self.ac_on

        self._persist_reading(temp_snapshot, humidity_snapshot, fan_snapshot, ac_snapshot)

    def _apply_control_logic(self):
        """Hysteresis-based automatic control. Reads thresholds from the
        settings table so the Settings page can change behavior live."""
        db = get_db_standalone()
        try:
            auto_enabled = get_setting(db, "auto_control_enabled", "1") == "1"
            if not auto_enabled:
                return

            fan_on_temp = float(get_setting(db, "fan_on_temp", FAN_ON_TEMP))
            fan_off_temp = float(get_setting(db, "fan_off_temp", FAN_OFF_TEMP))
            ac_on_temp = float(get_setting(db, "ac_on_temp", AC_ON_TEMP))
            ac_off_temp = float(get_setting(db, "ac_off_temp", AC_OFF_TEMP))

            t = self.current_temp
            prev_fan, prev_ac = self.fan_on, self.ac_on

            # AC logic (checked first since AC implies stronger cooling need)
            if not self.ac_on and t >= ac_on_temp:
                self.ac_on = True
            elif self.ac_on and t <= ac_off_temp:
                self.ac_on = False

            # Fan logic
            if not self.fan_on and t >= fan_on_temp:
                self.fan_on = True
            elif self.fan_on and t <= fan_off_temp:
                self.fan_on = False

            # AC running implies fan also runs (circulation)
            if self.ac_on:
                self.fan_on = True

            if prev_fan != self.fan_on:
                self._log_event(
                    db, "FAN_ON" if self.fan_on else "FAN_OFF",
                    f"Fan turned {'ON' if self.fan_on else 'OFF'} at {t:.1f}°C",
                )
            if prev_ac != self.ac_on:
                self._log_event(
                    db, "AC_ON" if self.ac_on else "AC_OFF",
                    f"AC turned {'ON' if self.ac_on else 'OFF'} at {t:.1f}°C",
                )
            if t >= CRITICAL_TEMP:
                self._log_event(
                    db, "CRITICAL", f"Critical temperature reached: {t:.1f}°C"
                )
        finally:
            db.close()

    def _log_event(self, db, event_type, message):
        db.execute(
            "INSERT INTO events (timestamp, event_type, message) VALUES (?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), event_type, message),
        )
        db.commit()

    def _persist_reading(self, temp, humidity, fan_on, ac_on):
        db = get_db_standalone()
        try:
            status_level = self._status_level(temp)
            sensor_name = get_setting(db, "sensor_name", "Server Room A")
            db.execute(
                "INSERT INTO readings "
                "(timestamp, sensor_name, temperature, humidity, fan_status, ac_status, status_level) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now().isoformat(timespec="seconds"),
                    sensor_name,
                    temp,
                    humidity,
                    "ON" if fan_on else "OFF",
                    "ON" if ac_on else "OFF",
                    status_level,
                ),
            )
            db.commit()

            # Keep the table from growing unbounded in long-running demos.
            db.execute(
                "DELETE FROM readings WHERE id NOT IN "
                "(SELECT id FROM readings ORDER BY id DESC LIMIT 20000)"
            )
            db.commit()
        finally:
            db.close()

    @staticmethod
    def _status_level(temp):
        if temp >= CRITICAL_TEMP:
            return "critical"
        if temp >= AC_ON_TEMP:
            return "warning"
        if temp >= FAN_ON_TEMP:
            return "elevated"
        return "normal"

    def snapshot(self):
        with self.lock:
            return {
                "temperature": self.current_temp,
                "humidity": self.current_humidity,
                "fan_on": self.fan_on,
                "ac_on": self.ac_on,
                "status_level": self._status_level(self.current_temp),
            }


simulator = ThermalSimulator()


# --------------------------------------------------------------------------
# Auth helpers
# --------------------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_globals():
    return {
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "founder_name": FOUNDER_NAME,
        "current_year": datetime.now().year,
        "logged_in_user": session.get("username"),
    }


# --------------------------------------------------------------------------
# Public / marketing routes
# --------------------------------------------------------------------------

@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/features")
def features():
    return render_template("features.html")


@app.route("/applications")
def applications():
    return render_template("applications.html")


# --------------------------------------------------------------------------
# Auth routes
# --------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["full_name"] = user["full_name"]
            next_url = request.args.get("next")
            return redirect(next_url or url_for("dashboard"))

        flash("Invalid username or password.", "error")
        return render_template("login.html"), 401

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --------------------------------------------------------------------------
# App routes (require login)
# --------------------------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    sensor_name = get_setting(db, "sensor_name", "Server Room A")
    latest = db.execute(
        "SELECT * FROM readings ORDER BY id DESC LIMIT 1"
    ).fetchone()
    recent_events = db.execute(
        "SELECT * FROM events ORDER BY id DESC LIMIT 6"
    ).fetchall()

    return render_template(
        "dashboard.html",
        sensor_name=sensor_name,
        latest=dict(latest) if latest else None,
        recent_events=[dict(e) for e in recent_events],
        thresholds={
            "fan_on": get_setting(db, "fan_on_temp", FAN_ON_TEMP),
            "ac_on": get_setting(db, "ac_on_temp", AC_ON_TEMP),
            "critical": get_setting(db, "critical_temp", CRITICAL_TEMP),
        },
    )


@app.route("/analytics")
@login_required
def analytics_page():
    return render_template("analytics.html")


@app.route("/history")
@login_required
def history_page():
    return render_template("history.html")


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_page():
    db = get_db()

    if request.method == "POST":
        form_keys = [
            "sensor_name", "fan_on_temp", "fan_off_temp",
            "ac_on_temp", "ac_off_temp", "critical_temp", "temp_unit",
        ]
        try:
            fan_on = float(request.form.get("fan_on_temp"))
            fan_off = float(request.form.get("fan_off_temp"))
            ac_on = float(request.form.get("ac_on_temp"))
            ac_off = float(request.form.get("ac_off_temp"))

            if fan_off >= fan_on:
                flash("Fan OFF temperature must be lower than Fan ON temperature.", "error")
                return redirect(url_for("settings_page"))
            if ac_off >= ac_on:
                flash("AC OFF temperature must be lower than AC ON temperature.", "error")
                return redirect(url_for("settings_page"))
            if ac_on <= fan_on:
                flash("AC ON temperature should be higher than Fan ON temperature.", "error")
                return redirect(url_for("settings_page"))
        except (TypeError, ValueError):
            flash("Please enter valid numeric temperatures.", "error")
            return redirect(url_for("settings_page"))

        for key in form_keys:
            value = request.form.get(key)
            if value is not None:
                set_setting(db, key, value)

        auto_control = "1" if request.form.get("auto_control_enabled") == "on" else "0"
        set_setting(db, "auto_control_enabled", auto_control)

        flash("Settings updated successfully.", "success")
        return redirect(url_for("settings_page"))

    current_settings = {
        "sensor_name": get_setting(db, "sensor_name", "Server Room A"),
        "fan_on_temp": get_setting(db, "fan_on_temp", FAN_ON_TEMP),
        "fan_off_temp": get_setting(db, "fan_off_temp", FAN_OFF_TEMP),
        "ac_on_temp": get_setting(db, "ac_on_temp", AC_ON_TEMP),
        "ac_off_temp": get_setting(db, "ac_off_temp", AC_OFF_TEMP),
        "critical_temp": get_setting(db, "critical_temp", CRITICAL_TEMP),
        "temp_unit": get_setting(db, "temp_unit", "C"),
        "auto_control_enabled": get_setting(db, "auto_control_enabled", "1") == "1",
    }
    return render_template("settings.html", settings=current_settings)


# --------------------------------------------------------------------------
# JSON APIs (consumed by dashboard / analytics / history pages via JS)
# --------------------------------------------------------------------------

@app.route("/api/live")
@login_required
def api_live():
    """Polled by the dashboard every few seconds for the live gauge."""
    db = get_db()
    snap = simulator.snapshot()
    snap["sensor_name"] = get_setting(db, "sensor_name", "Server Room A")
    snap["timestamp"] = datetime.now().strftime("%H:%M:%S")
    snap["thresholds"] = {
        "fan_on": float(get_setting(db, "fan_on_temp", FAN_ON_TEMP)),
        "ac_on": float(get_setting(db, "ac_on_temp", AC_ON_TEMP)),
        "critical": float(get_setting(db, "critical_temp", CRITICAL_TEMP)),
    }
    return jsonify(snap)


@app.route("/api/readings")
@login_required
def api_readings():
    """Returns recent readings for charting. Accepts ?minutes=N or ?limit=N."""
    db = get_db()
    minutes = request.args.get("minutes", type=int)
    limit = request.args.get("limit", default=120, type=int)

    if minutes:
        cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")
        rows = db.execute(
            "SELECT * FROM readings WHERE timestamp >= ? ORDER BY id ASC", (cutoff,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM readings ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        rows = list(reversed(rows))

    return jsonify([dict(r) for r in rows])


@app.route("/api/stats")
@login_required
def api_stats():
    """Summary statistics for the analytics page."""
    db = get_db()
    period = request.args.get("period", default="24h")
    hours_map = {"1h": 1, "6h": 6, "24h": 24, "7d": 168, "30d": 720}
    hours = hours_map.get(period, 24)
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")

    rows = db.execute(
        "SELECT * FROM readings WHERE timestamp >= ? ORDER BY id ASC", (cutoff,)
    ).fetchall()

    if not rows:
        return jsonify({
            "count": 0, "avg_temp": None, "min_temp": None, "max_temp": None,
            "avg_humidity": None, "fan_on_pct": 0, "ac_on_pct": 0,
            "critical_count": 0, "warning_count": 0,
        })

    temps = [r["temperature"] for r in rows]
    humidities = [r["humidity"] for r in rows]
    fan_on_count = sum(1 for r in rows if r["fan_status"] == "ON")
    ac_on_count = sum(1 for r in rows if r["ac_status"] == "ON")
    critical_count = sum(1 for r in rows if r["status_level"] == "critical")
    warning_count = sum(1 for r in rows if r["status_level"] == "warning")

    return jsonify({
        "count": len(rows),
        "avg_temp": round(sum(temps) / len(temps), 2),
        "min_temp": round(min(temps), 2),
        "max_temp": round(max(temps), 2),
        "avg_humidity": round(sum(humidities) / len(humidities), 2),
        "fan_on_pct": round(100 * fan_on_count / len(rows), 1),
        "ac_on_pct": round(100 * ac_on_count / len(rows), 1),
        "critical_count": critical_count,
        "warning_count": warning_count,
    })


@app.route("/api/events")
@login_required
def api_events():
    db = get_db()
    limit = request.args.get("limit", default=20, type=int)
    rows = db.execute(
        "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/history")
@login_required
def api_history():
    """Searchable/filterable history for the History page (with pagination)."""
    db = get_db()

    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "").strip()
    date_from = request.args.get("from", "").strip()
    date_to = request.args.get("to", "").strip()
    page = request.args.get("page", default=1, type=int)
    per_page = request.args.get("per_page", default=25, type=int)

    query = "SELECT * FROM readings WHERE 1=1"
    params = []

    if search:
        query += " AND (sensor_name LIKE ? OR CAST(temperature AS TEXT) LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    if status_filter:
        query += " AND status_level = ?"
        params.append(status_filter)
    if date_from:
        query += " AND timestamp >= ?"
        params.append(date_from)
    if date_to:
        query += " AND timestamp <= ?"
        params.append(date_to + " 23:59:59")

    count_query = query.replace("SELECT *", "SELECT COUNT(*) as c", 1)
    total = db.execute(count_query, params).fetchone()["c"]

    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])
    rows = db.execute(query, params).fetchall()

    return jsonify({
        "rows": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, math.ceil(total / per_page)),
    })


@app.route("/api/history/export")
@login_required
def api_history_export():
    """CSV export honoring the same filters as the History page table."""
    db = get_db()

    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "").strip()
    date_from = request.args.get("from", "").strip()
    date_to = request.args.get("to", "").strip()

    query = "SELECT * FROM readings WHERE 1=1"
    params = []
    if search:
        query += " AND (sensor_name LIKE ? OR CAST(temperature AS TEXT) LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    if status_filter:
        query += " AND status_level = ?"
        params.append(status_filter)
    if date_from:
        query += " AND timestamp >= ?"
        params.append(date_from)
    if date_to:
        query += " AND timestamp <= ?"
        params.append(date_to + " 23:59:59")
    query += " ORDER BY id DESC"

    rows = db.execute(query, params).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Timestamp", "Sensor", "Temperature (°C)", "Humidity (%)",
        "Fan Status", "AC Status", "Status Level",
    ])
    for r in rows:
        writer.writerow([
            r["id"], r["timestamp"], r["sensor_name"], r["temperature"],
            r["humidity"], r["fan_status"], r["ac_status"], r["status_level"],
        ])

    csv_data = output.getvalue()
    filename = f"thermoguard_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/api/manual-override", methods=["POST"])
@login_required
def api_manual_override():
    """Allows toggling auto-control on/off from the dashboard quickly."""
    db = get_db()
    enabled = request.json.get("enabled", True) if request.is_json else True
    set_setting(db, "auto_control_enabled", "1" if enabled else "0")
    return jsonify({"auto_control_enabled": enabled})


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    simulator.start()
    app.run(debug=True, host="0.0.0.0", port=5000)
else:
    # Also initialize when imported by a WSGI server.
    init_db()
    simulator.start()
