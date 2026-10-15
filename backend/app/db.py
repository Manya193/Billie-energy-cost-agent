from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "billie.sqlite3"


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """

        CREATE TABLE IF NOT EXISTS virtual_appliances (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            room TEXT NOT NULL,
            power_kw REAL NOT NULL,
            is_on INTEGER NOT NULL DEFAULT 0,
            scheduled_hours REAL NOT NULL DEFAULT 0,
            baseline_hours REAL NOT NULL DEFAULT 0,
            icon TEXT NOT NULL DEFAULT 'plug'
        );

        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            total_kwh REAL NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL,
            fixed_charge REAL NOT NULL,
            rate_per_kwh REAL NOT NULL,
            synthetic INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS baselines (
            appliance TEXT PRIMARY KEY,
            expected_daily_kwh REAL NOT NULL,
            normal_variance_kwh REAL NOT NULL,
            power_kw REAL NOT NULL,
            reference_period TEXT NOT NULL,
            adaptation_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS appliance_usage (
            id INTEGER PRIMARY KEY,
            ts TEXT NOT NULL,
            period_label TEXT NOT NULL,
            appliance TEXT NOT NULL,
            power_kw REAL NOT NULL,
            duration_hours REAL NOT NULL,
            energy_kwh REAL NOT NULL,
            source TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS alert_episodes (
            id INTEGER PRIMARY KEY,
            episode_key TEXT NOT NULL UNIQUE,
            appliance TEXT NOT NULL,
            status TEXT NOT NULL,
            alert_count INTEGER NOT NULL DEFAULT 0,
            last_alert_at TEXT,
            last_notified_cost REAL NOT NULL DEFAULT 0,
            user_response TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY,
            episode_id INTEGER NOT NULL REFERENCES alert_episodes(id),
            sent_at TEXT NOT NULL,
            alert_number INTEGER NOT NULL,
            appliance TEXT NOT NULL,
            severity TEXT NOT NULL,
            estimated_cost REAL NOT NULL,
            additional_kwh REAL NOT NULL,
            status TEXT NOT NULL,
            user_response TEXT
        );

        CREATE TABLE IF NOT EXISTS interventions (
            id INTEGER PRIMARY KEY,
            ts TEXT NOT NULL,
            appliance TEXT NOT NULL,
            authorized_action TEXT NOT NULL,
            reason TEXT NOT NULL,
            previous_state TEXT NOT NULL,
            requested_state TEXT NOT NULL,
            actual_state TEXT NOT NULL,
            verification_status TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS appliance_state (
            appliance TEXT PRIMARY KEY,
            state TEXT NOT NULL
        );
        
        CREATE TABLE IF NOT EXISTS pending_actions (
            id INTEGER PRIMARY KEY,
            action_token TEXT NOT NULL UNIQUE,
            appliance TEXT NOT NULL,
            action_name TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING'
                CHECK (status IN ('PENDING', 'APPLIED', 'CANCELLED', 'EXPIRED')),
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            confirmed_at TEXT
        );

        """
    )
    conn.commit()


def reset_demo_data(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DELETE FROM alerts;
        DELETE FROM alert_episodes;
        DELETE FROM pending_actions;
        DELETE FROM interventions;
        DELETE FROM appliance_usage;
        DELETE FROM bills;
        DELETE FROM baselines;
        DELETE FROM appliance_state;
        DELETE FROM virtual_appliances;
        """
    )
    conn.executemany(
        """
        INSERT INTO bills (
            period_start, period_end, total_kwh, amount, currency, fixed_charge, rate_per_kwh, synthetic
        ) VALUES (?, ?, ?, ?, 'INR', ?, ?, 1)
        """,
        [
            ("2026-08-01", "2026-08-31", 250, 2000, 125, 7.5),
            ("2026-09-01", "2026-09-30", 326, 2570, 125, 7.5),
        ],
    )
    conn.executemany(
        """
        INSERT INTO baselines (
            appliance, expected_daily_kwh, normal_variance_kwh, power_kw, reference_period, adaptation_count
        ) VALUES (?, ?, ?, ?, ?, 0)
        """,
        [
            ("AC", 3.2, 1.0, 1.5, "Last 45 synthetic days"),
            ("Water heater", 1.8, 0.7, 2.0, "Last 45 synthetic days"),
            ("Refrigerator", 1.5, 0.3, 0.15, "Last 45 synthetic days"),
        ],
    )
    usage_rows = [
        ("2026-08-14T20:00:00+05:30", "previous", "AC", 1.5, 2.1),
        ("2026-08-15T07:00:00+05:30", "previous", "Water heater", 2.0, 0.8),
        ("2026-09-08T20:00:00+05:30", "current", "AC", 1.5, 3.4),
        ("2026-09-12T19:30:00+05:30", "current", "AC", 1.5, 5.8),
        ("2026-09-13T07:00:00+05:30", "current", "Water heater", 2.0, 1.4),
        ("2026-09-20T19:00:00+05:30", "current", "AC", 1.5, 5.1),
        ("2026-09-21T07:15:00+05:30", "current", "Water heater", 2.0, 1.3),
        ("2026-09-29T22:00:00+05:30", "current", "AC", 1.5, 4.9),
        ("2026-10-10T14:00:00+05:30", "today", "AC", 1.5, 5.5),
    ]
    conn.executemany(
        """
        INSERT INTO appliance_usage (ts, period_label, appliance, power_kw, duration_hours, energy_kwh, source)
        VALUES (?, ?, ?, ?, ?, ?, 'synthetic_demo')
        """,
        [(ts, period, appliance, power, hours, round(power * hours, 3)) for ts, period, appliance, power, hours in usage_rows],
    )

    conn.executemany(
        """
        INSERT INTO virtual_appliances
            (id, name, room, power_kw, is_on, scheduled_hours, baseline_hours, icon)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("ac", "AC Unit", "Bedroom", 1.5, 0, 4.0, 3.0, "snowflake"),
            ("lights", "Living Room", "Living room", 0.1, 1, 5.0, 4.0, "lightbulb"),
            ("fridge", "Kitchen Fridge", "Kitchen", 0.2, 1, 24.0, 24.0, "refrigerator"),
            ("ev", "EV Charger", "Garage", 7.4, 0, 1.0, 1.0, "plug"),
            ("theatre", "Home Theater", "Living room", 0.4, 0, 2.0, 1.0, "tv"),
            ("heater", "Water Heater", "Bathroom", 1.8, 1, 1.0, 0.7, "waves"),
        ],
    )

    conn.execute(
        "INSERT INTO appliance_state (appliance, state) VALUES ('AC', ?)",
        ('{"routine":"Comfort cooling","target_temp_c":22,"max_daily_hours":6}',),
    )
    conn.commit()


def ensure_demo_data(conn: sqlite3.Connection) -> None:
    init_db(conn)
    count = conn.execute("SELECT COUNT(*) AS c FROM bills").fetchone()["c"]
    if count == 0:
        reset_demo_data(conn)

