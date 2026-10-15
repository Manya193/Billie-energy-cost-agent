from __future__ import annotations

from . import energy
from .simulator import get_simulator_state, update_appliance


def list_tools():
    names = [
        "get_current_energy_usage",
        "get_bill_history",
        "get_tariff",
        "get_appliance_usage",
        "get_user_baseline",
        "detect_energy_anomaly",
        "estimate_cost_impact",
        "explain_bill",
        "evaluate_alert_policy",
        "record_user_response",
        "manage_alert_state",
        "apply_energy_action",
        "verify_intervention",
        "simulate_worsening_usage",
    ]
    return [
        {
            "name": name,
            "description": name.replace("_", " "),
            "inputSchema": {"type": "object", "additionalProperties": True},
        }
        for name in names
    ]


def _sim_device(conn, appliance):
    state = get_simulator_state(conn)
    needle = str(appliance or "AC").lower()
    aliases = {"ac": "ac", "air conditioner": "ac", "air conditioning": "ac", "water heater": "heater", "heater": "heater", "fridge": "fridge", "refrigerator": "fridge", "lights": "lights", "living room": "lights", "ev": "ev", "ev charger": "ev", "home theater": "theatre", "theatre": "theatre"}
    device_id = aliases.get(needle, needle)
    return state, next((d for d in state["devices"] if d["id"] == device_id or d["name"].lower() == needle), None)


def _sim_usage(conn, period_label="today"):
    state = get_simulator_state(conn)
    usage = [{"appliance": d["name"], "energy_kwh": d["accumulated_kwh"] if period_label == "today" else d["projected_daily_kwh"], "duration_hours": d["simulated_minutes"] / 60 if period_label == "today" else d["scheduled_hours"], "events": 1, "is_on": d["is_on"]} for d in state["devices"]]
    return {"period_label": period_label, "usage": sorted(usage, key=lambda x: x["energy_kwh"], reverse=True), "synthetic": True, "source": "virtual_simulator"}


def _sim_anomaly(conn, appliance="AC", period_label="today"):
    state, device = _sim_device(conn, appliance)
    if device is None:
        return {"error": f"Unknown simulated appliance: {appliance}", "synthetic": True}

    # Use the simulator's canonical alert decision instead of recalculating a
    # second threshold. This keeps tool answers identical to the visible alerts.
    alert = next((item for item in state["alerts"] if item["appliance_id"] == device["id"]), None)
    # Baseline alerts compare like-for-like daily projections. Accumulated energy
    # is exposed separately and must not be mixed into a kWh/day comparison.
    observed = device["projected_daily_kwh"]
    expected = device["baseline_daily_kwh"]
    additional = alert["additional_kwh_day"] if alert else 0.0
    anomalous = alert is not None
    return {
        "appliance": device["name"],
        "appliance_id": device["id"],
        "period_label": period_label,
        "observed_kwh": observed,
        "accumulated_kwh": device["accumulated_kwh"],
        "comparison_basis": "projected_daily_kwh_vs_baseline_daily_kwh",
        "projected_kwh_day": device["projected_daily_kwh"],
        "expected_kwh": expected,
        "threshold_kwh": round(expected + 0.25, 3),
        "additional_kwh": additional,
        "is_anomaly": anomalous,
        "severity": alert["severity"] if alert else "normal",
        "alert": alert,
        "source": "virtual_simulator",
        "synthetic": True,
    }


def _sim_cost_impact(conn, appliance="AC", period_label="today"):
    anomaly = _sim_anomaly(conn, appliance, period_label)
    if "error" in anomaly:
        return anomaly
    state = get_simulator_state(conn)
    return {
        **anomaly,
        "rate_per_kwh": state["tariff"]["rate_per_kwh"],
        "estimated_additional_cost": round(anomaly["additional_kwh"] * state["tariff"]["rate_per_kwh"], 2),
        "currency": "INR",
    }


def _sim_bill_comparison(conn):
    """Compare current simulated routine with its configured baseline.

    Both totals use the same tariff and fixed charge, so the appliance-level
    monthly deltas reconcile exactly to the projected bill difference.
    """
    state = get_simulator_state(conn)
    tariff = state["tariff"]
    rate = float(tariff["rate_per_kwh"])
    fixed = float(tariff.get("fixed_charge", 0))
    current_kwh_day = float(state["total_projected_daily_kwh"])
    baseline_kwh_day = float(state["baseline_daily_kwh"])
    current_amount = round(current_kwh_day * rate * 30 + fixed, 2)
    baseline_amount = round(baseline_kwh_day * rate * 30 + fixed, 2)
    rows = []
    for d in state["devices"]:
        delta_kwh_day = round(float(d["projected_daily_kwh"]) - float(d["baseline_daily_kwh"]), 3)
        delta_cost_month = round(delta_kwh_day * rate * 30, 2)
        rows.append({
            "appliance": d["name"],
            "appliance_id": d["id"],
            "current_kwh_day": d["projected_daily_kwh"],
            "baseline_kwh_day": d["baseline_daily_kwh"],
            "delta_kwh_day": delta_kwh_day,
            "delta_cost_month": delta_cost_month,
            "direction": "increase" if delta_cost_month > 0 else "reduction" if delta_cost_month < 0 else "unchanged",
        })
    difference = round(current_amount - baseline_amount, 2)
    # Keep the displayed contributions arithmetically consistent with the bill delta.
    contribution_total = round(sum(r["delta_cost_month"] for r in rows), 2)
    return {
        "bills": [
            {"period": "Current simulated routine (30-day projection)", "amount": current_amount, "total_kwh": round(current_kwh_day * 30, 2), "synthetic": True},
            {"period": "Configured baseline (30-day projection)", "amount": baseline_amount, "total_kwh": round(baseline_kwh_day * 30, 2), "synthetic": True},
        ],
        "comparison": {
            "current_amount": current_amount,
            "previous_amount": baseline_amount,
            "difference": difference,
            "current_kwh": round(current_kwh_day * 30, 2),
            "previous_kwh": round(baseline_kwh_day * 30, 2),
            "kwh_difference": round((current_kwh_day - baseline_kwh_day) * 30, 2),
            "basis": "simulator_projection_vs_configured_baseline",
            "contributions": rows,
            "contribution_total": contribution_total,
            "reconciles": abs(difference - contribution_total) < 0.02,
        },
        "source": "virtual_simulator",
        "synthetic": True,
    }


def _sim_bill_explanation(conn):
    state = get_simulator_state(conn)
    comparison = _sim_bill_comparison(conn)["comparison"]
    positive = [r for r in comparison["contributions"] if r["delta_cost_month"] > 0]
    negative = [r for r in comparison["contributions"] if r["delta_cost_month"] < 0]
    positive.sort(key=lambda r: r["delta_cost_month"], reverse=True)
    negative.sort(key=lambda r: r["delta_cost_month"])
    contributions = positive + negative
    if not positive and not negative:
        summary = (
            f"The current simulated bill is ₹{comparison['current_amount']:.2f}/month, "
            f"matching the configured baseline of ₹{comparison['previous_amount']:.2f}/month. "
            "No appliance is changing the projected bill relative to baseline."
        )
    else:
        positive_parts = [
            f"{item['appliance']} increases the projection by ₹{item['delta_cost_month']:.2f}/month"
            for item in positive
        ]
        negative_parts = [
            f"{item['appliance']} reduces the projection by ₹{abs(item['delta_cost_month']):.2f}/month"
            for item in negative
        ]
        direction = "higher" if comparison["difference"] > 0 else "lower" if comparison["difference"] < 0 else "equal to"
        net = (
            f"₹{abs(comparison['difference']):.2f}/month {direction} than baseline"
            if comparison["difference"] != 0 else "the same as baseline"
        )
        drivers = "; ".join(positive_parts + negative_parts) or "No appliance-level changes"
        summary = (
            f"The current simulated bill is ₹{comparison['current_amount']:.2f}/month, "
            f"compared with the configured baseline projection of ₹{comparison['previous_amount']:.2f}/month "
            f"({net}). Main appliance changes: {drivers}. "
            "These are 30-day projections based on the current simulated schedules."
        )
    return {
        "source": "virtual_simulator",
        "synthetic": True,
        "basis": "current scheduled routine compared with configured appliance baselines over 30 days",
        "current_projected_monthly_cost": comparison["current_amount"],
        "baseline_projected_monthly_cost": comparison["previous_amount"],
        "difference": comparison["difference"],
        "current_projected_monthly_kwh": comparison["current_kwh"],
        "baseline_projected_monthly_kwh": comparison["previous_kwh"],
        "appliance_breakdown": contributions,
        "explained_difference": comparison["contribution_total"],
        "reconciles": comparison["reconciles"],
        "alerts": state["alerts"],
        "savings_opportunities": state["savings_opportunities"],
        "summary": summary,
    }

def _sim_manage_alert_state(conn):
    state = get_simulator_state(conn)
    return {"active": state["alerts"], "episodes": [], "max_alerts_per_episode": 1,
            "source": "virtual_simulator", "synthetic": True}


def _sim_worsen_usage(conn):
    # Keep the demo button/tool connected to the same appliance state that drives
    # cards, alerts, recommendations, and chat answers.
    return update_appliance(conn, "ac", is_on=True, scheduled_hours=6.0)


def _sim_alert_policy(conn, appliance="AC"):
    state, device = _sim_device(conn, appliance)
    if device is None:
        return {"decision": "ERROR", "reason": f"Unknown simulated appliance: {appliance}", "source": "virtual_simulator"}
    alert = next((item for item in state["alerts"] if item["appliance_id"] == device["id"]), None)
    if alert:
        return {"decision": "NOTIFY", "reason": alert["message"], "alert": alert, "source": "virtual_simulator", "synthetic": True}
    return {"decision": "WAIT", "reason": f"{device['name']} is not above the simulator's configured alert threshold.", "alert": None, "source": "virtual_simulator", "synthetic": True}


def call_tool(conn, name, arguments=None):
    args = arguments or {}
    dispatch = {
        "get_current_energy_usage": lambda: {"timestamp": None, "total_kwh_today": get_simulator_state(conn)["accumulated_energy_kwh"], "projected_daily_kwh": get_simulator_state(conn)["total_projected_daily_kwh"], "readings": _sim_usage(conn, "today")["usage"], "source": "virtual_simulator", "synthetic": True},
        "get_bill_history": lambda: _sim_bill_comparison(conn),
        "get_tariff": lambda: energy.get_tariff(conn),
        "get_appliance_usage": lambda: _sim_usage(conn, args.get("period_label", "current")),
        "get_user_baseline": lambda: (lambda pair: {"appliance": pair[1]["name"], "expected_daily_kwh": pair[1]["baseline_daily_kwh"], "normal_variance_kwh": max(0.25, round(pair[1]["baseline_daily_kwh"] * 0.15, 3)), "source": "virtual_simulator", "synthetic": True} if pair[1] else energy.get_user_baseline(conn, args.get("appliance", "AC")))(_sim_device(conn, args.get("appliance", "AC"))),
        "detect_energy_anomaly": lambda: _sim_anomaly(conn, args.get("appliance", "AC"), args.get("period_label", "today")),
        "estimate_cost_impact": lambda: _sim_cost_impact(conn, args.get("appliance", "AC"), args.get("period_label", "today")),
        "explain_bill": lambda: _sim_bill_explanation(conn),
        "evaluate_alert_policy": lambda: _sim_alert_policy(conn, args.get("appliance", "AC")),
        "record_user_response": lambda: energy.record_user_response(conn, args.get("response", "acknowledged"), args.get("appliance", "AC"), args.get("period_label", "today")),
        "manage_alert_state": lambda: _sim_manage_alert_state(conn),
        "apply_energy_action": lambda: energy.apply_energy_action(conn, args.get("action", "set_simulated_routine"), bool(args.get("authorized")), args.get("reason", "User authorized routine adjustment"), args.get("appliance", "AC")),
        "verify_intervention": lambda: energy.verify_intervention(conn),
        "simulate_worsening_usage": lambda: _sim_worsen_usage(conn),
    }
    if name not in dispatch:
        raise ValueError(f"Unknown tool: {name}")
    return dispatch[name]()

