from __future__ import annotations

from .energy import get_tariff

DEVICE_DEFAULTS = [
    {"id": "ac", "name": "AC Unit", "room": "Bedroom", "power_kw": 1.5, "is_on": False, "scheduled_hours": 4.0, "baseline_hours": 3.0, "icon": "snowflake"},
    {"id": "lights", "name": "Living Room", "room": "Living room", "power_kw": 0.1, "is_on": True, "scheduled_hours": 5.0, "baseline_hours": 4.0, "icon": "lightbulb"},
    {"id": "fridge", "name": "Kitchen Fridge", "room": "Kitchen", "power_kw": 0.2, "is_on": True, "scheduled_hours": 24.0, "baseline_hours": 24.0, "icon": "refrigerator"},
    {"id": "ev", "name": "EV Charger", "room": "Garage", "power_kw": 7.4, "is_on": False, "scheduled_hours": 1.0, "baseline_hours": 1.0, "icon": "plug"},
    {"id": "theatre", "name": "Home Theater", "room": "Living room", "power_kw": 0.4, "is_on": False, "scheduled_hours": 2.0, "baseline_hours": 1.0, "icon": "tv"},
    {"id": "heater", "name": "Water Heater", "room": "Bathroom", "power_kw": 1.8, "is_on": True, "scheduled_hours": 1.0, "baseline_hours": 0.7, "icon": "waves"},
]


def ensure_simulator(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS virtual_appliances (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, room TEXT NOT NULL,
            power_kw REAL NOT NULL, is_on INTEGER NOT NULL DEFAULT 0,
            scheduled_hours REAL NOT NULL DEFAULT 0,
            baseline_hours REAL NOT NULL DEFAULT 0, icon TEXT NOT NULL DEFAULT 'plug'
        )
    """)
    count = conn.execute("SELECT COUNT(*) FROM virtual_appliances").fetchone()[0]
    if count == 0:
        conn.executemany(
            """INSERT INTO virtual_appliances
            (id,name,room,power_kw,is_on,scheduled_hours,baseline_hours,icon)
            VALUES (:id,:name,:room,:power_kw,:is_on,:scheduled_hours,:baseline_hours,:icon)""",
            [{**d, "is_on": int(d["is_on"])} for d in DEVICE_DEFAULTS],
        )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS simulator_runtime (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            elapsed_minutes INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("INSERT OR IGNORE INTO simulator_runtime (singleton, elapsed_minutes) VALUES (1, 0)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS simulator_energy (
            appliance_id TEXT PRIMARY KEY,
            accumulated_kwh REAL NOT NULL DEFAULT 0,
            simulated_minutes INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.executemany(
        "INSERT OR IGNORE INTO simulator_energy (appliance_id, accumulated_kwh, simulated_minutes) VALUES (?, 0, 0)",
        [(d["id"],) for d in DEVICE_DEFAULTS],
    )
    conn.commit()


def get_simulator_state(conn):
    ensure_simulator(conn)
    rows = conn.execute("SELECT * FROM virtual_appliances ORDER BY id").fetchall()
    runtime = conn.execute("SELECT elapsed_minutes FROM simulator_runtime WHERE singleton=1").fetchone()
    elapsed_minutes = int(runtime["elapsed_minutes"]) if runtime else 0
    energy_rows = {r["appliance_id"]: dict(r) for r in conn.execute("SELECT * FROM simulator_energy").fetchall()}
    tariff = get_tariff(conn)
    devices = []
    for row in rows:
        d = dict(row)
        d["is_on"] = bool(d["is_on"])
        # Scheduled hours model a full day; current switch state determines
        # whether the schedule contributes to the projected daily total.
        d["projected_daily_kwh"] = round(d["power_kw"] * d["scheduled_hours"] if d["is_on"] else 0.0, 3)
        d["baseline_daily_kwh"] = round(d["power_kw"] * d["baseline_hours"], 3)
        d["additional_kwh"] = round(max(0.0, d["projected_daily_kwh"] - d["baseline_daily_kwh"]), 3)
        d["estimated_daily_cost"] = round(d["projected_daily_kwh"] * tariff["rate_per_kwh"], 2)
        d["estimated_additional_cost"] = round(d["additional_kwh"] * tariff["rate_per_kwh"], 2)
        energy = energy_rows.get(d["id"], {"accumulated_kwh": 0.0, "simulated_minutes": 0})
        d["accumulated_kwh"] = round(float(energy["accumulated_kwh"]), 4)
        d["simulated_minutes"] = int(energy["simulated_minutes"])
        devices.append(d)
    total_kwh = round(sum(d["projected_daily_kwh"] for d in devices), 3)
    baseline_kwh = round(sum(d["baseline_daily_kwh"] for d in devices), 3)
    alerts = []
    for d in devices:
        threshold = d["baseline_daily_kwh"]
        observed = d["projected_daily_kwh"]
        extra = round(observed - threshold, 3)
        # Shared alert policy: any positive projected excess qualifies when the appliance is on.
        if d["is_on"] and extra > 0:
            alerts.append({
                "id": f"{d['id']}:above-baseline",
                "appliance_id": d["id"],
                "appliance": d["name"],
                "severity": "high" if extra >= 2.0 else "moderate",
                "observed_kwh_day": observed,
                "baseline_kwh_day": threshold,
                "additional_kwh_day": extra,
                "estimated_additional_cost_day": round(extra * tariff["rate_per_kwh"], 2),
                "message": f"{d['name']} is projected {extra:.2f} kWh/day above its configured baseline.",
                "synthetic": True,
            })
    # Alerts and cost-saving opportunities intentionally share one qualifying
    # set so the simulator, recommendations, and conversational answers agree.
    savings_opportunities = [
        {
            "id": alert["id"],
            "appliance_id": alert["appliance_id"],
            "name": alert["appliance"],
            "additional_kwh": alert["additional_kwh_day"],
            "estimated_additional_cost": alert["estimated_additional_cost_day"],
            "baseline_kwh_day": alert["baseline_kwh_day"],
            "projected_kwh_day": alert["observed_kwh_day"],
        }
        for alert in alerts
    ]
    return {
        "devices": devices,
        "alerts": alerts,
        "savings_opportunities": savings_opportunities,
        "alert_count": len(alerts),
        "tariff": tariff,
        "total_projected_daily_kwh": total_kwh,
        "baseline_daily_kwh": baseline_kwh,
        "additional_kwh": round(total_kwh - baseline_kwh, 3),
        "projected_daily_cost": round(total_kwh * tariff["rate_per_kwh"], 2),
        "projected_monthly_kwh": round(total_kwh * 30, 2),
        # Keep the energy-only amount for transparent arithmetic, and expose
        # the comparable all-in estimate separately for UI/bill consistency.
        "projected_monthly_cost": round(total_kwh * tariff["rate_per_kwh"] * 30, 2),
        "projected_monthly_total_cost": round(total_kwh * tariff["rate_per_kwh"] * 30 + tariff.get("fixed_charge", 0), 2),
        "monthly_fixed_charge": round(float(tariff.get("fixed_charge", 0)), 2),
        "simulated_elapsed_minutes": elapsed_minutes,
        "simulated_time_label": f"{elapsed_minutes // 60:02d}:{elapsed_minutes % 60:02d} simulated hours",
        "accumulated_energy_kwh": round(sum(d["accumulated_kwh"] for d in devices), 4),
        "accumulated_cost": round(sum(d["accumulated_kwh"] for d in devices) * tariff["rate_per_kwh"], 2),
        "synthetic": True,
        "model": "synthetic virtual home; projections use rated kW × scheduled hours; accumulated energy advances only when simulated time is advanced",
    }


def advance_simulation(conn, minutes=60):
    ensure_simulator(conn)
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        raise ValueError("minutes must be an integer")
    if minutes < 1 or minutes > 1440:
        raise ValueError("minutes must be between 1 and 1440")
    runtime = conn.execute("SELECT elapsed_minutes FROM simulator_runtime WHERE singleton=1").fetchone()
    elapsed = int(runtime["elapsed_minutes"]) if runtime else 0
    devices = conn.execute("SELECT * FROM virtual_appliances ORDER BY id").fetchall()
    for row in devices:
        device_id = row["id"]
        current = conn.execute("SELECT accumulated_kwh, simulated_minutes FROM simulator_energy WHERE appliance_id=?", (device_id,)).fetchone()
        accumulated = float(current["accumulated_kwh"]) if current else 0.0
        device_minutes = int(current["simulated_minutes"]) if current else 0
        # An on device consumes rated power while it is within its configured daily runtime.
        remaining_minutes = max(0, int(float(row["scheduled_hours"]) * 60) - device_minutes)
        active_minutes = min(minutes, remaining_minutes) if row["is_on"] else 0
        accumulated += float(row["power_kw"]) * active_minutes / 60.0
        device_minutes += active_minutes
        conn.execute(
            "INSERT INTO simulator_energy (appliance_id, accumulated_kwh, simulated_minutes) VALUES (?, ?, ?) "
            "ON CONFLICT(appliance_id) DO UPDATE SET accumulated_kwh=excluded.accumulated_kwh, simulated_minutes=excluded.simulated_minutes",
            (device_id, round(accumulated, 6), device_minutes),
        )
    conn.execute("UPDATE simulator_runtime SET elapsed_minutes=? WHERE singleton=1", (elapsed + minutes,))
    conn.commit()
    return get_simulator_state(conn)


def update_appliance(conn, appliance_id, *, is_on=None, scheduled_hours=None):
    ensure_simulator(conn)
    row = conn.execute("SELECT * FROM virtual_appliances WHERE id=?", (appliance_id,)).fetchone()
    if row is None:
        raise ValueError("Unknown virtual appliance")
    if is_on is None:
        is_on = bool(row["is_on"])
    if scheduled_hours is None:
        scheduled_hours = float(row["scheduled_hours"])
    scheduled_hours = float(scheduled_hours)
    if not 0 <= scheduled_hours <= 24:
        raise ValueError("scheduled_hours must be between 0 and 24")
    conn.execute(
        "UPDATE virtual_appliances SET is_on=?, scheduled_hours=? WHERE id=?",
        (int(bool(is_on)), scheduled_hours, appliance_id),
    )
    conn.commit()
    return get_simulator_state(conn)


def reset_simulator(conn):
    ensure_simulator(conn)
    conn.execute("DELETE FROM virtual_appliances")
    conn.execute("DELETE FROM simulator_energy")
    conn.execute("UPDATE simulator_runtime SET elapsed_minutes=0 WHERE singleton=1")
    conn.commit()
    ensure_simulator(conn)
    return get_simulator_state(conn)
