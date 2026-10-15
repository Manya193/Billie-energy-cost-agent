from __future__ import annotations

import json
from datetime import datetime, timezone


RATE_FALLBACK = 7.5
FIXED_FALLBACK = 125
TWO_ALERT_LIMIT = 1
MATERIAL_WORSENING_COST = 25.0


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def rowdict(row):
    return dict(row) if row is not None else None


def get_tariff(conn):
    bill = conn.execute("SELECT * FROM bills ORDER BY period_end DESC LIMIT 1").fetchone()
    return {
        "currency": "INR",
        "rate_per_kwh": bill["rate_per_kwh"] if bill else RATE_FALLBACK,
        "fixed_charge": bill["fixed_charge"] if bill else FIXED_FALLBACK,
        "model": "flat_rate_plus_fixed_charge",
        "synthetic": True,
    }


def get_bill_history(conn):
    rows = conn.execute("SELECT * FROM bills ORDER BY period_end DESC LIMIT 2").fetchall()
    bills = [rowdict(r) for r in rows]
    comparison = None
    if len(bills) >= 2:
        current, previous = bills[0], bills[1]
        comparison = {
            "current_amount": current["amount"],
            "previous_amount": previous["amount"],
            "difference": round(current["amount"] - previous["amount"], 2),
            "current_kwh": current["total_kwh"],
            "previous_kwh": previous["total_kwh"],
            "kwh_difference": round(current["total_kwh"] - previous["total_kwh"], 3),
        }
    return {"bills": bills, "comparison": comparison}


def get_appliance_usage(conn, period_label="current"):
    rows = conn.execute(
        """
        SELECT appliance, ROUND(SUM(energy_kwh), 3) AS energy_kwh, ROUND(SUM(duration_hours), 3) AS duration_hours,
               COUNT(*) AS events
        FROM appliance_usage
        WHERE period_label = ?
        GROUP BY appliance
        ORDER BY energy_kwh DESC
        """,
        (period_label,),
    ).fetchall()
    return {"period_label": period_label, "usage": [rowdict(r) for r in rows], "synthetic": True}


def get_user_baseline(conn, appliance="AC"):
    row = conn.execute("SELECT * FROM baselines WHERE appliance = ?", (appliance,)).fetchone()
    return rowdict(row)


def get_current_energy_usage(conn):
    rows = conn.execute(
        """
        SELECT * FROM appliance_usage
        WHERE period_label = 'today'
        ORDER BY ts DESC
        """
    ).fetchall()
    total = round(sum(r["energy_kwh"] for r in rows), 3)
    return {
        "timestamp": rows[0]["ts"] if rows else None,
        "total_kwh_today": total,
        "readings": [rowdict(r) for r in rows],
        "synthetic": True,
    }


def detect_energy_anomaly(conn, appliance="AC", period_label="today"):
    usage = conn.execute(
        """
        SELECT ROUND(SUM(energy_kwh), 3) AS energy_kwh, ROUND(SUM(duration_hours), 3) AS duration_hours
        FROM appliance_usage
        WHERE appliance = ? AND period_label = ?
        """,
        (appliance, period_label),
    ).fetchone()
    baseline = get_user_baseline(conn, appliance)
    observed = usage["energy_kwh"] or 0
    expected = baseline["expected_daily_kwh"] if baseline else 0
    variance = baseline["normal_variance_kwh"] if baseline else 0
    threshold = expected + variance
    additional = round(max(0, observed - expected), 3)
    is_anomaly = observed > threshold
    severity = "high" if additional >= 4 else "moderate" if is_anomaly else "normal"
    return {
        "appliance": appliance,
        "period_label": period_label,
        "observed_kwh": observed,
        "expected_kwh": expected,
        "threshold_kwh": round(threshold, 3),
        "additional_kwh": additional,
        "is_anomaly": is_anomaly,
        "severity": severity,
        "synthetic": True,
    }


def estimate_cost_impact(conn, appliance="AC", period_label="today"):
    anomaly = detect_energy_anomaly(conn, appliance, period_label)
    tariff = get_tariff(conn)
    cost = round(anomaly["additional_kwh"] * tariff["rate_per_kwh"], 2)
    return {**anomaly, "rate_per_kwh": tariff["rate_per_kwh"], "estimated_additional_cost": cost, "currency": tariff["currency"]}


def _episode_key(appliance, period_label):
    return f"{appliance}:{period_label}:2026-10-10-demo"


def evaluate_alert_policy(conn, appliance="AC", period_label="today", persist=True):
    impact = estimate_cost_impact(conn, appliance, period_label)
    key = _episode_key(appliance, period_label)
    episode = conn.execute("SELECT * FROM alert_episodes WHERE episode_key = ?", (key,)).fetchone()
    if episode is None and persist:
        conn.execute(
            """
            INSERT INTO alert_episodes (episode_key, appliance, status, alert_count, created_at)
            VALUES (?, ?, 'ANOMALY_DETECTED', 0, ?)
            """,
            (key, appliance, now_iso()),
        )
        conn.commit()
        episode = conn.execute("SELECT * FROM alert_episodes WHERE episode_key = ?", (key,)).fetchone()

    if not impact["is_anomaly"]:
        return {"decision": "WAIT", "reason": "Usage is within the personalized baseline.", "impact": impact, "episode": rowdict(episode)}

    if episode and episode["user_response"] == "dismissed":
        return {"decision": "SUPPRESS", "reason": "The user dismissed this anomaly episode.", "impact": impact, "episode": rowdict(episode)}

    count = episode["alert_count"] if episode else 0
    last_cost = episode["last_notified_cost"] if episode else 0
    material_change = impact["estimated_additional_cost"] >= last_cost + MATERIAL_WORSENING_COST

    if count >= TWO_ALERT_LIMIT:
        if persist and episode:
            conn.execute("UPDATE alert_episodes SET status = 'SILENT' WHERE id = ?", (episode["id"],))
            conn.commit()
        return {"decision": "SUPPRESS", "reason": "One alert has already been sent for this issue; repeat alerts are suppressed.", "impact": impact, "episode": rowdict(episode)}

    if count == 0:
        decision, reason = "NOTIFY", "First alert is permitted for this qualifying anomaly."
    else:
        return {"decision": "SUPPRESS", "reason": "One alert has already been sent for this issue; repeat alerts are suppressed.", "impact": impact, "episode": rowdict(episode)}

    if persist and episode:
        alert_no = count + 1
        ts = now_iso()
        status = "ALERT_1_SENT"
        conn.execute(
            """
            INSERT INTO alerts (episode_id, sent_at, alert_number, appliance, severity, estimated_cost, additional_kwh, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'sent')
            """,
            (episode["id"], ts, alert_no, appliance, impact["severity"], impact["estimated_additional_cost"], impact["additional_kwh"]),
        )
        conn.execute(
            """
            UPDATE alert_episodes
            SET alert_count = ?, last_alert_at = ?, last_notified_cost = ?, status = ?
            WHERE id = ?
            """,
            (alert_no, ts, impact["estimated_additional_cost"], "SILENT_AFTER_ALERT_1", episode["id"]),
        )
        conn.commit()
        episode = conn.execute("SELECT * FROM alert_episodes WHERE episode_key = ?", (key,)).fetchone()
    return {"decision": decision, "reason": reason, "impact": impact, "episode": rowdict(episode)}


def record_user_response(conn, response, appliance="AC", period_label="today"):
    key = _episode_key(appliance, period_label)
    episode = conn.execute("SELECT * FROM alert_episodes WHERE episode_key = ?", (key,)).fetchone()
    if not episode:
        return {"ok": False, "error": "No active alert episode exists."}
    conn.execute("UPDATE alert_episodes SET user_response = ?, status = ? WHERE id = ?", (response, response.upper(), episode["id"]))
    conn.execute("UPDATE alerts SET user_response = ? WHERE episode_id = ?", (response, episode["id"]))
    conn.commit()
    return {"ok": True, "response": response, "episode": rowdict(conn.execute("SELECT * FROM alert_episodes WHERE id = ?", (episode["id"],)).fetchone())}


def manage_alert_state(conn):
    episodes = [rowdict(r) for r in conn.execute("SELECT * FROM alert_episodes ORDER BY id DESC").fetchall()]
    alerts = [rowdict(r) for r in conn.execute("SELECT * FROM alerts ORDER BY id DESC").fetchall()]
    return {"episodes": episodes, "alerts": alerts, "max_alerts_per_episode": 1}


def add_worsening_usage(conn):
    conn.execute(
        """
        INSERT INTO appliance_usage (ts, period_label, appliance, power_kw, duration_hours, energy_kwh, source)
        VALUES ('2026-10-10T18:00:00+05:30', 'today', 'AC', 1.5, 2.5, 3.75, 'synthetic_demo_worsening')
        """
    )
    conn.commit()
    return get_current_energy_usage(conn)


def apply_energy_action(
    conn, action="set_ac_eco_routine", authorized=False,
    reason="User requested adjustment", appliance="AC"
):
    """Apply an appliance-specific simulated routine after explicit authorization."""
    if not authorized:
        return {"ok": False, "error": "Explicit user authorization is required."}

    aliases = {
        "ac unit": "AC", "air conditioner": "AC", "air conditioning": "AC",
        "living room lights": "Living Room", "lights": "Living Room", "living room": "Living Room",
        "kitchen fridge": "Kitchen Fridge", "fridge": "Kitchen Fridge", "refrigerator": "Kitchen Fridge",
        "water heater": "Water Heater", "heater": "Water Heater",
        "ev": "EV Charger", "ev charger": "EV Charger",
        "home theater": "Home Theater", "home theatre": "Home Theater", "theater": "Home Theater", "theatre": "Home Theater",
    }
    target = aliases.get(str(appliance or "AC").strip().lower(), str(appliance or "AC").strip())
    routines = {
        "AC": ("Eco cooling", {"target_temp_c": 24, "max_daily_hours": 3.5}),
        "Living Room": ("Lighting schedule", {"max_daily_hours": 4.0, "auto_off": True}),
        "Kitchen Fridge": ("Efficiency check", {"check_door_seal": True, "check_temperature_setting": True, "keep_cooling_on": True}),
        "Water Heater": ("Scheduled heating", {"max_daily_hours": 0.7, "auto_off": True}),
        "EV Charger": ("Off-peak charging schedule", {"schedule": "off_peak", "max_daily_hours": 1.0}),
        "Home Theater": ("Auto-off routine", {"max_daily_hours": 1.0, "auto_off": True}),
    }
    if target not in routines:
        return {"ok": False, "error": "Unsupported appliance: " + target}

    routine, settings = routines[target]
    row = conn.execute("SELECT state FROM appliance_state WHERE appliance = ?", (target,)).fetchone()
    previous = row["state"] if row else "{}"
    requested = {"routine": routine, **settings, "simulated": True}
    actual = dict(requested)
    conn.execute("INSERT OR REPLACE INTO appliance_state (appliance, state) VALUES (?, ?)", (target, json.dumps(actual)))
    conn.execute(
        """INSERT INTO interventions
        (ts, appliance, authorized_action, reason, previous_state, requested_state, actual_state, verification_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_verification')""",
        (now_iso(), target, action, reason, previous, json.dumps(requested), json.dumps(actual)),
    )
    conn.commit()
    return {"ok": True, "appliance": target, "previous_state": json.loads(previous),
            "requested_state": requested, "actual_state": actual}


def verify_intervention(conn):
    intervention = conn.execute("SELECT * FROM interventions ORDER BY id DESC LIMIT 1").fetchone()
    if not intervention:
        return {"ok": False, "error": "No intervention has been recorded."}
    state = conn.execute("SELECT state FROM appliance_state WHERE appliance = ?", (intervention["appliance"],)).fetchone()
    actual = json.loads(state["state"]) if state else {}
    requested = json.loads(intervention["requested_state"])
    verified = actual == requested
    status = "verified_success" if verified else "verified_mismatch"
    conn.execute("UPDATE interventions SET verification_status = ?, actual_state = ? WHERE id = ?", (status, json.dumps(actual), intervention["id"]))
    conn.commit()
    return {"ok": verified, "verification_status": status, "requested_state": requested, "actual_state": actual, "intervention_id": intervention["id"]}


def explain_bill(conn):
    history = get_bill_history(conn)
    tariff = get_tariff(conn)
    current_usage = get_appliance_usage(conn, "current")["usage"]
    previous_usage = get_appliance_usage(conn, "previous")["usage"]
    previous_by_app = {r["appliance"]: r for r in previous_usage}
    contributors = []
    for row in current_usage:
        app = row["appliance"]
        previous_kwh = previous_by_app.get(app, {}).get("energy_kwh", 0)
        additional = round(max(0, row["energy_kwh"] - previous_kwh), 3)
        if additional > 0:
            contributors.append(
                {
                    "appliance": app,
                    "additional_kwh": additional,
                    "estimated_additional_cost": round(additional * tariff["rate_per_kwh"], 2),
                    "evidence": f"{app} recorded {row['energy_kwh']} kWh this period versus {previous_kwh} kWh in the prior sample.",
                }
            )
    comparison = history["comparison"] or {}
    explained = round(sum(c["estimated_additional_cost"] for c in contributors), 2)
    diff = comparison.get("difference", 0)
    alerts = [rowdict(r) for r in conn.execute("SELECT * FROM alerts ORDER BY id").fetchall()]
    interventions = [rowdict(r) for r in conn.execute("SELECT * FROM interventions ORDER BY id").fetchall()]
    findings = {
        "current_bill": comparison.get("current_amount"),
        "previous_bill": comparison.get("previous_amount"),
        "difference": diff,
        "current_kwh": comparison.get("current_kwh"),
        "previous_kwh": comparison.get("previous_kwh"),
        "contributors": contributors,
        "explained_estimated_cost": explained,
        "unexplained_difference": round(diff - explained, 2),
        "tariff": tariff,
        "alerts": alerts,
        "interventions": interventions,
        "uncertainty": "Appliance estimates are based on synthetic appliance-level records and do not force every rupee of the bill difference to match.",
    }
    findings["summary"] = fallback_explanation(findings)
    return findings


def fallback_explanation(findings):
    parts = [
        f"Your current synthetic bill is ₹{findings['current_bill']} versus ₹{findings['previous_bill']} previously, a change of ₹{findings['difference']}.",
    ]
    if findings["contributors"]:
        leader = findings["contributors"][0]
        parts.append(
            f"The largest estimated contributor is {leader['appliance']}: {leader['additional_kwh']} additional kWh, about ₹{leader['estimated_additional_cost']} at the modeled tariff."
        )
    if findings["alerts"]:
        parts.append(f"I found {len(findings['alerts'])} prior alert record(s) connected to unusual usage.")
    if findings["interventions"]:
        parts.append(f"I also found {len(findings['interventions'])} recorded intervention(s) that can be considered in follow-up analysis.")
    parts.append(findings["uncertainty"])
    return " ".join(parts)

