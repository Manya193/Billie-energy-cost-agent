
import sqlite3
import unittest
import re
from datetime import datetime, timedelta, timezone

from backend.app.db import init_db, reset_demo_data
from backend.app.server import WEB_DIR, mcp_response, run_orchestration
from backend.app.tools import list_tools


def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    reset_demo_data(conn)
    return conn


class AppFlowTests(unittest.TestCase):
    def test_static_ui_exists(self):
        index = WEB_DIR / "index.html"
        self.assertTrue(index.exists())
        self.assertIn("Billie", index.read_text(encoding="utf-8"))

    def test_mcp_shapes_and_tool_discovery(self):
        initialized = mcp_response(
            1,
            {
                "protocolVersion": "2025-11-25",
                "serverInfo": {
                    "name": "billie-energy-agent",
                    "version": "0.1.0",
                },
                "capabilities": {"tools": {"listChanged": False}},
            },
        )
        self.assertEqual(initialized["jsonrpc"], "2.0")
        self.assertEqual(
            initialized["result"]["protocolVersion"], "2025-11-25"
        )
        self.assertGreaterEqual(len(list_tools()), 13)

    def test_conversation_orchestrates_real_tools(self):
        with memory_db() as conn:
            result = run_orchestration(
                conn, "Why is my electricity bill so high?"
            )
            self.assertIn("configured baseline", result["reply"])
            self.assertIn("current simulated bill is", result["reply"])
            self.assertIn("baseline projection", result["reply"])
            self.assertGreaterEqual(len(result["trace"]), 5)
            self.assertEqual(result["trace"][-1]["tool"], "explain_bill")


    def test_bill_question_uses_live_simulator_and_reconciled_costs(self):
        with memory_db() as conn:
            from backend.app.simulator import get_simulator_state, update_appliance
            update_appliance(conn, "ac", is_on=True, scheduled_hours=6.0)
            result = run_orchestration(conn, "Why is my electricity bill high?")
            state = get_simulator_state(conn)
            evidence = result["evidence"]
            self.assertEqual(evidence["current_projected_monthly_cost"], 3747.5)
            self.assertEqual(evidence["baseline_projected_monthly_cost"], 4346.0)
            self.assertEqual(evidence["difference"], -598.5)
            self.assertTrue(evidence["reconciles"])
            self.assertIn("AC Unit increases the projection by ₹1012.50/month", result["reply"])
            self.assertNotIn("AC Unit reduces the projection", result["reply"])
            self.assertEqual(state["projected_monthly_cost"], 3622.5)
            self.assertEqual(state["projected_monthly_total_cost"], 3747.5)

    def test_living_room_small_excess_appears_in_alerts_and_savings(self):
        with memory_db() as conn:
            from backend.app.simulator import get_simulator_state
            state = get_simulator_state(conn)
            living = next(d for d in state["devices"] if d["id"] == "lights")
            # Make the Living Room on and just 0.1 kWh/day above baseline.
            conn.execute("UPDATE virtual_appliances SET is_on=1, scheduled_hours=? WHERE id='lights'",
                         (living["baseline_hours"] + 0.1 / living["power_kw"],))
            conn.commit()
            state = get_simulator_state(conn)
            self.assertTrue(any(a["appliance_id"] == "lights" for a in state["alerts"]))
            self.assertTrue(any(o["appliance_id"] == "lights" for o in state["savings_opportunities"]))

    def test_household_evaluation_summarizes_usage_and_alert_policy(self):
        with memory_db() as conn:
            result = run_orchestration(conn, "Evaluate household appliance usage and alert policy")
            reply = result["reply"]
            self.assertIn("Household usage summary", reply)
            self.assertIn("Alert policy", reply)
            self.assertIn("projected", reply.lower())

    def test_alerts_and_savings_use_identical_simulator_values(self):
        with memory_db() as conn:
            from backend.app.simulator import get_simulator_state
            state = get_simulator_state(conn)
            self.assertEqual(len(state["alerts"]), len(state["savings_opportunities"]))
            savings_by_id = {item["appliance_id"]: item for item in state["savings_opportunities"]}
            for alert in state["alerts"]:
                item = savings_by_id[alert["appliance_id"]]
                self.assertEqual(item["name"], alert["appliance"])
                self.assertEqual(item["additional_kwh"], alert["additional_kwh_day"])
                self.assertEqual(item["estimated_additional_cost"], alert["estimated_additional_cost_day"])
                self.assertEqual(item["baseline_kwh_day"], alert["baseline_kwh_day"])
                self.assertEqual(item["projected_kwh_day"], alert["observed_kwh_day"])

    def test_alert_question_reports_the_simulator_appliance_not_default_ac(self):
        with memory_db() as conn:
            result = run_orchestration(conn, "What energy alerts are active?")
            self.assertIn("Water Heater", result["reply"])
            self.assertNotIn("AC Unit:", result["reply"])
            self.assertEqual(result["engine"], "simulator_grounded")

    def test_savings_question_does_not_start_an_action(self):
        with memory_db() as conn:
            result = run_orchestration(conn, "What should I adjust to save money?")
            self.assertIn("Water Heater", result["reply"])
            self.assertNotIn("confirm ", result["reply"])
            self.assertFalse(result["evidence"].get("action_applied", False))

    def test_confirmed_routine_changes_visible_simulator_projection(self):
        with memory_db() as conn:
            from backend.app.simulator import get_simulator_state
            before = get_simulator_state(conn)
            before_heater = next(d for d in before["devices"] if d["id"] == "heater")
            proposal = run_orchestration(conn, "Please adjust the water heater schedule")
            token = re.search(r"type: confirm ([A-Za-z0-9_-]+)", proposal["reply"]).group(1)
            confirmed = run_orchestration(conn, f"confirm {token}")
            after = get_simulator_state(conn)
            after_heater = next(d for d in after["devices"] if d["id"] == "heater")
            self.assertTrue(confirmed["evidence"]["action_applied"])
            self.assertEqual(after_heater["scheduled_hours"], 0.7)
            self.assertNotEqual(after_heater["projected_daily_kwh"], before_heater["projected_daily_kwh"])

    def test_water_heater_action_is_appliance_specific(self):
        with memory_db() as conn:
            result = run_orchestration(conn, "Please adjust the water heater schedule")
            self.assertFalse(result["evidence"]["action_applied"])
            self.assertEqual(result["evidence"]["appliance"], "Water Heater")
            token = re.search(r"type: confirm ([A-Za-z0-9_-]+)", result["reply"]).group(1)
            confirmed = run_orchestration(conn, f"confirm {token}")
            self.assertTrue(confirmed["evidence"]["action_applied"])
            row = conn.execute("SELECT appliance, requested_state FROM interventions ORDER BY id DESC LIMIT 1").fetchone()
            self.assertEqual(row["appliance"], "Water Heater")
            self.assertIn("Scheduled heating", row["requested_state"])

    def test_fridge_action_keeps_cooling_on(self):
        with memory_db() as conn:
            result = run_orchestration(conn, "Please adjust the fridge routine")
            token = re.search(r"type: confirm ([A-Za-z0-9_-]+)", result["reply"]).group(1)
            confirmed = run_orchestration(conn, f"confirm {token}")
            self.assertTrue(confirmed["evidence"]["action_applied"])
            row = conn.execute("SELECT requested_state FROM interventions ORDER BY id DESC LIMIT 1").fetchone()
            self.assertIn('"keep_cooling_on": true', row["requested_state"])

    def test_action_question_does_not_execute_action(self):
        with memory_db() as conn:
            result = run_orchestration(
                conn, "Should I adjust the AC routine?"
            )
            self.assertFalse(result["evidence"]["action_applied"])

            count = conn.execute(
                "SELECT COUNT(*) FROM interventions"
            ).fetchone()[0]
            self.assertEqual(count, 0)

    def test_confirmation_without_pending_action_is_rejected(self):
        with memory_db() as conn:
            result = run_orchestration(conn, "confirm made-up-token")
            self.assertFalse(result["evidence"].get("action"))
            count = conn.execute(
                "SELECT COUNT(*) FROM interventions"
            ).fetchone()[0]
            self.assertEqual(count, 0)

    def test_invalid_token_is_rejected(self):
        with memory_db() as conn:
            run_orchestration(conn, "Please adjust the AC routine")
            result = run_orchestration(conn, "confirm invalid-token")
            self.assertFalse(result["evidence"].get("action"))
            count = conn.execute(
                "SELECT COUNT(*) FROM interventions"
            ).fetchone()[0]
            self.assertEqual(count, 0)

    def test_expired_pending_action_is_rejected(self):
        with memory_db() as conn:
            run_orchestration(conn, "Please adjust the AC routine")
            expired = (
                datetime.now(timezone.utc) - timedelta(minutes=10)
            ).isoformat(timespec="seconds")
            conn.execute(
                "UPDATE pending_actions SET expires_at = ? "
                "WHERE status = 'PENDING'",
                (expired,),
            )
            conn.commit()

            row = conn.execute(
                "SELECT action_token FROM pending_actions "
                "WHERE status = 'PENDING'"
            ).fetchone()
            self.assertIsNotNone(row)

            result = run_orchestration(
                conn, f"confirm {row['action_token']}"
            )
            self.assertFalse(result["evidence"].get("action"))
            count = conn.execute(
                "SELECT COUNT(*) FROM interventions"
            ).fetchone()[0]
            self.assertEqual(count, 0)

    
    def test_valid_pending_action_is_applied_and_verified(self):
        with memory_db() as conn:
            proposal = run_orchestration(
                conn, "Please adjust the AC routine"
            )
            import re
            match = re.search(
                r"type:\s*confirm\s+([A-Za-z0-9_-]+)",
                proposal["reply"],
                re.IGNORECASE,
            )
            self.assertIsNotNone(match)
            token = match.group(1)

            result = run_orchestration(conn, f"confirm {token}")

            self.assertTrue(result["evidence"]["action"]["ok"])
            self.assertTrue(result["evidence"]["verification"]["ok"])
            self.assertTrue(result["evidence"]["action_applied"])

            count = conn.execute(
                "SELECT COUNT(*) FROM interventions"
            ).fetchone()[0]
            self.assertEqual(count, 1)

    def test_reused_confirmation_token_cannot_apply_twice(self):
        with memory_db() as conn:
            proposal = run_orchestration(
                conn, "Please adjust the AC routine"
            )
            import re
            match = re.search(
                r"type:\s*confirm\s+([A-Za-z0-9_-]+)",
                proposal["reply"],
                re.IGNORECASE,
            )
            self.assertIsNotNone(match)
            token = match.group(1)

            first = run_orchestration(conn, f"confirm {token}")
            second = run_orchestration(conn, f"confirm {token}")

            self.assertTrue(first["evidence"]["action_applied"])
            self.assertFalse(second["evidence"]["action_applied"])

            count = conn.execute(
                "SELECT COUNT(*) FROM interventions"
            ).fetchone()[0]
            self.assertEqual(count, 1)

    def test_pending_action_does_not_execute_before_confirmation(self):
        with memory_db() as conn:
            result = run_orchestration(
                conn, "Please adjust the AC routine"
            )

            self.assertTrue(result["evidence"]["pending_action"])
            self.assertFalse(result["evidence"]["action_applied"])

            count = conn.execute(
                "SELECT COUNT(*) FROM interventions"
            ).fetchone()[0]
            self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
