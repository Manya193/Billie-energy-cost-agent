from __future__ import annotations

import json
import os
import sys
import re
import secrets
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from app.db import connect, ensure_demo_data, reset_demo_data
    from app.tools import call_tool, list_tools
    from app.simulator import ensure_simulator, get_simulator_state, update_appliance, reset_simulator, advance_simulation
else:
    from .db import connect, ensure_demo_data, reset_demo_data
    from .tools import call_tool, list_tools
    from .simulator import ensure_simulator, get_simulator_state, update_appliance, reset_simulator, advance_simulation

ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT / "frontend"


def json_response(handler, status, payload):
    body = json.dumps(payload, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:8765")
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def mcp_response(request_id, result=None, error=None):
    if error:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(error)}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _simulator_answer(conn, message):
    """Answer energy questions only from the live virtual-appliance state."""
    state = get_simulator_state(conn)
    text = message.lower()
    alerts = state["alerts"]
    opportunities = state["savings_opportunities"]

    aliases = {
        "water heater": ("heater", "Water Heater"), "heater": ("heater", "Water Heater"),
        "kitchen fridge": ("fridge", "Kitchen Fridge"), "fridge": ("fridge", "Kitchen Fridge"),
        "refrigerator": ("fridge", "Kitchen Fridge"), "living room lights": ("lights", "Living Room"),
        "living room": ("lights", "Living Room"), "lights": ("lights", "Living Room"),
        "ev charger": ("ev", "EV Charger"), "ev charging": ("ev", "EV Charger"),
        "home theater": ("theatre", "Home Theater"), "home theatre": ("theatre", "Home Theater"),
        "ac unit": ("ac", "AC Unit"), "air conditioner": ("ac", "AC Unit"),
    }
    matched = next((pair for phrase, pair in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True) if phrase in text), None)
    device = next((d for d in state["devices"] if matched and d["id"] == matched[0]), None)
    evidence = {"source": "virtual_simulator", "synthetic": True, "simulator": state, "action_applied": False}
    trace = [{"tool": "get_simulator_state", "arguments": {}, "result": state}]

    if device is not None:
        alert = next((a for a in alerts if a["appliance_id"] == device["id"]), None)
        if any(word in text for word in ("alert", "warning", "high usage", "above baseline")):
            if alert:
                reply = (f"{alert['appliance']} is projected at {alert['observed_kwh_day']:.2f} kWh/day, "
                         f"above its {alert['baseline_kwh_day']:.2f} kWh/day baseline by "
                         f"{alert['additional_kwh_day']:.2f} kWh/day. The estimated extra cost is "
                         f"₹{alert['estimated_additional_cost_day']:.2f} per day.")
            else:
                reply = f"There is no active simulator alert for {device['name']}. Its projected usage is {device['projected_daily_kwh']:.2f} kWh/day against a {device['baseline_daily_kwh']:.2f} kWh/day baseline."
        elif any(word in text for word in ("saving", "recommend", "reduce", "save", "opportunity")):
            opportunity = next((o for o in opportunities if o["appliance_id"] == device["id"]), None)
            if opportunity:
                reply = (f"For {device['name']}, the simulator estimates {opportunity['additional_kwh']:.2f} extra kWh/day "
                         f"and up to ₹{opportunity['estimated_additional_cost']:.2f} per day in potential savings by reviewing its routine.")
            else:
                reply = f"The simulator shows no above-threshold cost-saving recommendation for {device['name']} right now. Its projected usage is {device['projected_daily_kwh']:.2f} kWh/day."
        else:
            reply = (f"{device['name']} is {'on' if device['is_on'] else 'off'}, with projected usage of "
                     f"{device['projected_daily_kwh']:.2f} kWh/day, baseline {device['baseline_daily_kwh']:.2f} kWh/day, "
                     f"and projected cost ₹{device['estimated_daily_cost']:.2f}/day.")
            if alert:
                reply += f" It has an active alert for ₹{alert['estimated_additional_cost_day']:.2f}/day in estimated extra cost."
        evidence["device"] = device
        evidence["matching_alert"] = alert
        evidence["matching_savings_opportunity"] = next((o for o in opportunities if o["appliance_id"] == device["id"]), None)
        return {"reply": reply, "trace": trace, "evidence": evidence, "engine": "simulator_grounded"}

    if ("evaluate" in text or "summary" in text or "summarize" in text) and any(word in text for word in ("household", "appliance", "usage")):
        ordered = sorted(state["devices"], key=lambda item: item["projected_daily_kwh"], reverse=True)
        usage_summary = ", ".join(
            f"{d['name']} {'on' if d['is_on'] else 'off'}: {d['projected_daily_kwh']:.2f} kWh/day"
            for d in ordered
        )
        if alerts:
            alert_summary = " ".join(
                f"{a['appliance']}: {a['additional_kwh_day']:.2f} extra kWh/day (about ₹{a['estimated_additional_cost_day']:.2f}/day)."
                for a in alerts
            )
        else:
            alert_summary = "No appliances currently meet the alert policy."
        reply = (
            f"Household usage summary: the simulated home projects {state['total_projected_daily_kwh']:.2f} kWh/day "
            f"at ₹{state['projected_daily_cost']:.2f}/day. Appliance status and projections: {usage_summary}. "
            f"Alert policy: an appliance is flagged when it is on and its projected daily usage exceeds its baseline. "
            f"Current qualifying alerts: {alert_summary}"
        )
    elif any(word in text for word in ("alert", "warning", "high usage", "above baseline")):
        if alerts:
            parts = [f"{a['appliance']}: {a['additional_kwh_day']:.2f} extra kWh/day, about ₹{a['estimated_additional_cost_day']:.2f}/day extra." for a in alerts]
            reply = "Current simulator alerts: " + " ".join(parts)
        else:
            reply = "There are no active energy alerts in the simulated house right now."
    elif any(word in text for word in ("saving", "recommend", "reduce", "save", "opportunity")):
        if opportunities:
            parts = [f"{o['name']}: up to ₹{o['estimated_additional_cost']:.2f}/day potential savings from reviewing its routine." for o in opportunities]
            reply = "Current simulator-based cost-saving recommendations: " + " ".join(parts)
        else:
            reply = "The simulated house has no above-threshold cost-saving recommendations right now."
    else:
        breakdown = ", ".join(f"{d['name']} {d['projected_daily_kwh']:.2f} kWh/day" for d in sorted(state["devices"], key=lambda item: item["projected_daily_kwh"], reverse=True))
        reply = (f"The simulated house has accumulated {state['accumulated_energy_kwh']:.2f} kWh so far and projects "
                 f"{state['total_projected_daily_kwh']:.2f} kWh/day at ₹{state['projected_daily_cost']:.2f}/day. "
                 f"Appliance projections: {breakdown}.")
    evidence.update({"alerts": alerts, "savings_opportunities": opportunities})
    return {"reply": reply, "trace": trace, "evidence": evidence, "engine": "simulator_grounded"}


def _requires_simulator_truth(message):
    text = message.lower()
    terms = ("alert", "warning", "usage", "appliance", "energy", "saving", "save", "money", "recommend", "baseline", "projected", "projection", "kwh", "electricity", "bill", "cost", "water heater", "fridge", "lights", "ev charger", "home theater", "ac unit", "confirm ", "adjust", "routine", "schedule", "change")
    return any(term in text for term in terms)


def run_orchestration(conn, message):
    raw_message = message.strip()
    text = raw_message.lower()
    trace = []

    def tool(name, args=None):
        result = call_tool(conn, name, args or {})
        trace.append({"tool": name, "arguments": args or {}, "result": result})
        return result

    if ("bill" in text or "electricity" in text or "cost" in text) and any(word in text for word in ("why", "increase", "increased", "higher", "high", "explain", "breakdown", "contribut", "cost")):
        tool("get_bill_history")
        tool("get_tariff")
        tool("get_appliance_usage", {"period_label": "current"})
        tool("get_user_baseline", {"appliance": "AC"})
        tool("manage_alert_state")
        findings = tool("explain_bill")
        # Never return a bill explanation whose appliance contributions do not
        # reconcile with the deterministic simulator bill comparison.
        if not findings.get("reconciles", False):
            findings = {
                **findings,
                "summary": (
                    f"The current simulated bill is ₹{findings['current_projected_monthly_cost']:.2f}/month, "
                    f"compared with the configured baseline of ₹{findings['baseline_projected_monthly_cost']:.2f}/month. "
                    "The appliance-level breakdown needs reconciliation, so I will not attribute the difference yet."
                ),
            }
        return {"reply": findings["summary"], "trace": trace, "evidence": findings, "engine": "simulator_grounded"}

        
   
    # Process confirmation before interpreting a new action request.
    if text.startswith("confirm "):
        token = raw_message.split(maxsplit=1)[1].strip()

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        # Atomically claim a valid pending action.
        conn.execute("BEGIN IMMEDIATE")
        pending = conn.execute(
            """
            SELECT id, appliance, action_name, reason
            FROM pending_actions
            WHERE action_token = ?
              AND status = 'PENDING'
              AND expires_at > ?
            """,
            (token, now),
        ).fetchone()

        if pending is None:
            conn.rollback()
            return {
                "reply": (
                    "I couldn't confirm that action. It may be invalid, "
                    "expired, cancelled, or already used. No new action "
                    "was executed."
                ),
                "trace": trace,
                "evidence": {"action_applied": False},
            }

        conn.execute(
            """
            UPDATE pending_actions
            SET status = 'APPLIED', confirmed_at = ?
            WHERE id = ? AND status = 'PENDING'
            """,
            (now, pending["id"]),
        )

        action = tool(
            "apply_energy_action",
            {
                "authorized": True,
                "reason": pending["reason"],
                "appliance": pending["appliance"],
                "action": pending["action_name"],
            },
        )

        if not action.get("ok"):
            conn.rollback()
            return {
                "reply": "The simulated action could not be applied.",
                "trace": trace,
                "evidence": {"action": action, "action_applied": False},
            }

        # Keep the visible virtual-appliance simulator in sync with the confirmed routine.
        routine_targets = {
            "AC": ("ac", 3.5), "Living Room": ("lights", 4.0),
            "Kitchen Fridge": ("fridge", 24.0), "Water Heater": ("heater", 0.7),
            "EV Charger": ("ev", 1.0), "Home Theater": ("theatre", 1.0),
        }
        target = routine_targets.get(pending["appliance"])
        if target:
            appliance_id, hours = target
            current_state = get_simulator_state(conn)
            current_device = next((d for d in current_state["devices"] if d["id"] == appliance_id), None)
            if current_device:
                update_appliance(conn, appliance_id, is_on=current_device["is_on"], scheduled_hours=hours)

        verification = tool("verify_intervention")

        if not verification.get("ok"):
            conn.rollback()
            return {
                "reply": (
                    "The simulated action was attempted, but verification "
                    "did not succeed. Please inspect the demo state."
                ),
                "trace": trace,
                "evidence": {
                    "action": action,
                    "verification": verification,
                },
            }

        conn.commit()
        updated_state = get_simulator_state(conn)
        selected_id = routine_targets.get(pending["appliance"], (None, None))[0]
        updated_device = next((d for d in updated_state["devices"] if d["id"] == selected_id), None)
        updated_alert = next((a for a in updated_state["alerts"] if a["appliance_id"] == selected_id), None)
        reply = f"The simulated {action.get('appliance', pending['appliance'])} routine was applied and verified. "
        if updated_device:
            reply += (f"Its updated schedule is {updated_device['scheduled_hours']:.1f} hours/day, "
                      f"with projected usage {updated_device['projected_daily_kwh']:.2f} kWh/day "
                      f"against a {updated_device['baseline_daily_kwh']:.2f} kWh/day baseline.")
            if updated_alert:
                reply += f" The current alert estimates ₹{updated_alert['estimated_additional_cost_day']:.2f}/day in extra cost."
            else:
                reply += " There is no active above-threshold alert for this appliance now."
        reply += " No real appliance was controlled."
        return {
            "reply": reply,
            "trace": [{"tool": "get_simulator_state", "arguments": {}, "result": updated_state}],
            "evidence": {
                "action": action,
                "verification": verification,
                "action_applied": True,
                "updated_simulator": updated_state,
            },
        }


    # Propose a selected appliance's simulated routine; never execute before confirmation.
    # A bare appliance name is also treated as the user's answer to the appliance-selection prompt.
    action_intent_phrases = (
        "please adjust", "adjust the", "change the", "set a routine", "set the schedule",
        "schedule the", "i want to adjust", "i want to change", "apply routine", "authorize",
        "prepare a routine", "routine for",
    )
    appliance_names_in_text = any(term in text for term in (
        "water heater", "heater", "kitchen fridge", "fridge", "refrigerator",
        "living room lights", "living room", "lights", "ev charger", "ev charging",
        "home theater", "home theatre", "theater", "theatre", "air conditioner",
        "air conditioning", "ac unit", " ac ",
    ))
    if any(text.startswith(phrase) for phrase in action_intent_phrases):
        appliance_options = [
            (("water heater", "heater"), "Water Heater", "set_heater_schedule"),
            (("kitchen fridge", "fridge", "refrigerator"), "Kitchen Fridge", "check_fridge_efficiency"),
            (("living room lights", "lights", "living room"), "Living Room", "set_lighting_schedule"),
            (("ev charger", "ev charging", "charger", "ev"), "EV Charger", "set_ev_charging_schedule"),
            (("home theater", "home theatre", "theater", "theatre"), "Home Theater", "set_home_theater_auto_off"),
            (("ac", "air conditioner", "air conditioning"), "AC", "set_ac_eco_routine"),
        ]
        selected = next(((name, action_name) for terms, name, action_name in appliance_options
                         if any(term in text for term in terms)), None)
        if selected is None:
            return {
                "reply": "Which appliance should I prepare a simulated routine for: AC, Living Room lights, Kitchen Fridge, Water Heater, EV Charger, or Home Theater?",
                "trace": trace,
                "evidence": {"action_applied": False, "needs_appliance_selection": True},
            }
        appliance, action_name = selected
        descriptions = {
            "AC": "an Eco cooling routine (24°C, maximum 3.5 hours/day)",
            "Living Room": "a lighting schedule (maximum 4 hours/day with auto-off)",
            "Kitchen Fridge": "an efficiency check that keeps cooling on and checks temperature/door-seal settings",
            "Water Heater": "a scheduled heating routine (maximum 0.7 hours/day with auto-off)",
            "EV Charger": "an off-peak charging schedule (maximum 1 hour/day)",
            "Home Theater": "an auto-off routine (maximum 1 hour/day)",
        }
        token = secrets.token_urlsafe(16)
        created = datetime.now(timezone.utc)
        expires = created + timedelta(minutes=5)
        conn.execute(
            """INSERT INTO pending_actions
            (action_token, appliance, action_name, reason, status, created_at, expires_at)
            VALUES (?, ?, ?, ?, 'PENDING', ?, ?)""",
            (token, appliance, action_name, f"User requested a simulated routine for {appliance}.",
             created.isoformat(timespec="seconds"), expires.isoformat(timespec="seconds")),
        )
        conn.commit()
        return {
            "reply": (f"I have not changed anything. I can prepare {descriptions[appliance]} for {appliance}. "
                      f"To confirm this simulated action within five minutes, type: confirm {token}. "
                      "This demo does not control a real appliance."),
            "trace": trace,
            "evidence": {"action_applied": False, "pending_action": True, "appliance": appliance,
                         "action": action_name, "expires_at": expires.isoformat(timespec="seconds")},
        }


    if any(word in text for word in ("alert", "usage", "saving", "save", "money", "recommend", "opportunity", "appliance", "energy", "baseline", "projected", "kwh", "routine", "schedule", "water heater", "fridge", "lights", "ev charger", "home theater", "ac unit")):
        return _simulator_answer(conn, raw_message)

    overview = tool("get_current_energy_usage")
    return {
        "reply": f"Billie is ready. Today's synthetic modeled energy usage is {overview['total_kwh_today']} kWh. Ask why the bill is high or evaluate AC usage.",
        "trace": trace,
        "evidence": overview,
    }


class BillieHandler(BaseHTTPRequestHandler):
    server_version = "Billie/0.1"

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:8765")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self.serve_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
        if parsed.path == "/styles.css":
            return self.serve_file(WEB_DIR / "styles.css", "text/css; charset=utf-8")
        if parsed.path == "/app.js":
            return self.serve_file(WEB_DIR / "app.js", "text/javascript; charset=utf-8")
        if parsed.path == "/api/simulator":
            with connect() as conn:
                ensure_demo_data(conn)
                return json_response(self, 200, get_simulator_state(conn))
        if parsed.path == "/api/overview":
            with connect() as conn:
                ensure_demo_data(conn)
                payload = {
                    "usage": call_tool(conn, "get_current_energy_usage"),
                    "bill": call_tool(conn, "get_bill_history"),
                    "baseline": call_tool(conn, "get_user_baseline", {"appliance": "AC"}),
                    "alerts": {"active": get_simulator_state(conn)["alerts"], "episodes": []},
                }
            return json_response(self, 200, payload)
        json_response(self, 404, {"error": "Not found"})

    def serve_file(self, path, content_type):
        if not path.exists():
            return json_response(self, 404, {"error": f"Missing file {path.name}"})
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/mcp":
                return self.handle_mcp()

            if parsed.path == "/api/chat":
                payload = read_json(self)
                message = payload.get("message", "").strip()

                if not message:
                    return json_response(
                        self, 400, {"error": "Message cannot be empty"}
                    )

                # Simulator-facing questions and state changes must use the same
                # live simulator state as the visible appliance cards, alerts,
                # and recommendations. Do not let a free-form model response
                # independently recalculate or invent those values.
                if _requires_simulator_truth(message):
                    with connect() as conn:
                        ensure_demo_data(conn)
                        result = run_orchestration(conn, message)
                    result.setdefault("engine", "simulator_grounded")
                    return json_response(self, 200, result)

                # Keep the Ollama + MCP agent available for general questions.
                try:
                    from .agent import investigate_sync
                    result = investigate_sync(message)
                    result.setdefault("engine", "ollama_mcp")
                except Exception as exc:
                    print(f"[Billie] Agent unavailable; using deterministic simulator fallback: {exc}", flush=True)
                    with connect() as conn:
                        ensure_demo_data(conn)
                        result = run_orchestration(conn, message)
                    result["engine"] = "simulator_fallback"
                    result["fallback_reason"] = str(exc)
                return json_response(self, 200, result)

            if parsed.path == "/api/simulator/update":
                payload = read_json(self)
                appliance_id = str(payload.get("id", ""))
                is_on = payload.get("is_on")
                hours = payload.get("scheduled_hours")
                if is_on is not None and not isinstance(is_on, bool):
                    return json_response(self, 400, {"error": "is_on must be true or false"})
                with connect() as conn:
                    ensure_demo_data(conn)
                    result = update_appliance(conn, appliance_id, is_on=is_on, scheduled_hours=hours)
                return json_response(self, 200, result)

            if parsed.path == "/api/simulator/reset":
                with connect() as conn:
                    ensure_demo_data(conn)
                    result = reset_simulator(conn)
                return json_response(self, 200, result)

            if parsed.path == "/api/simulator/advance":
                payload = read_json(self)
                minutes = payload.get("minutes", 60)
                with connect() as conn:
                    ensure_demo_data(conn)
                    result = advance_simulation(conn, minutes)
                return json_response(self, 200, result)

            if parsed.path == "/api/demo/reset":
                with connect() as conn:
                    reset_demo_data(conn)
                return json_response(self, 200, {"ok": True})

            if parsed.path == "/api/demo/worsen":
                with connect() as conn:
                    ensure_demo_data(conn)
                    # Demonstrate a new alert by changing the actual simulator state.
                    result = call_tool(conn, "simulate_worsening_usage")
                return json_response(self, 200, result)

            return json_response(self, 404, {"error": "Not found"})

        except Exception as exc:
            return json_response(self, 500, {"error": str(exc)})

    def handle_mcp(self):
        req = read_json(self)
        method = req.get("method")
        request_id = req.get("id")
        params = req.get("params") or {}
        with connect() as conn:
            ensure_demo_data(conn)
            try:
                if method == "initialize":
                    result = {
                        "protocolVersion": "2025-11-25",
                        "serverInfo": {"name": "billie-energy-agent", "version": "0.1.0"},
                        "capabilities": {"tools": {"listChanged": False}},
                    }
                elif method == "tools/list":
                    result = {"tools": list_tools()}
                elif method == "tools/call":
                    name = params.get("name")
                    arguments = params.get("arguments") or {}
                    content = call_tool(conn, name, arguments)
                    result = {"content": [{"type": "json", "json": content}], "structuredContent": content}
                else:
                    return json_response(self, 400, mcp_response(request_id, error=f"Unsupported method: {method}"))
                return json_response(self, 200, mcp_response(request_id, result=result))
            except Exception as exc:
                return json_response(self, 500, mcp_response(request_id, error=exc))


def main():
    port = int(os.environ.get("PORT", os.environ.get("BILLIE_PORT", "8765")))
    host = "0.0.0.0" if os.environ.get("PORT") else os.environ.get("BILLIE_HOST", "127.0.0.1")
    with connect() as conn:
        ensure_demo_data(conn)
    server = ThreadingHTTPServer((host, port), BillieHandler)
    print(f"Billie running at http://{host}:{port}")
    print(f"MCP endpoint: http://{host}:{port}/mcp")
    server.serve_forever()



if __name__ == "__main__":
    main()

