import sqlite3
import unittest

from backend.app.db import init_db, reset_demo_data
from backend.app.energy import (
    add_worsening_usage,
    apply_energy_action,
    evaluate_alert_policy,
    explain_bill,
    verify_intervention,
)
from backend.app.tools import call_tool, list_tools


def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    reset_demo_data(conn)
    return conn


class BillieEngineTests(unittest.TestCase):
    def test_bill_explanation_uses_history_and_contributors(self):
        with memory_db() as conn:
            findings = explain_bill(conn)
            self.assertEqual(findings["current_bill"], 2570)
            self.assertEqual(findings["previous_bill"], 2000)
            self.assertEqual(findings["difference"], 570)
            self.assertGreaterEqual(len(findings["contributors"]), 1)
            self.assertIn("uncertainty", findings)

    def test_one_alert_policy_suppresses_repeats(self):
        with memory_db() as conn:
            first = evaluate_alert_policy(conn)
            self.assertEqual(first["decision"], "NOTIFY")
            second_wait = evaluate_alert_policy(conn)
            self.assertEqual(second_wait["decision"], "SUPPRESS")
            add_worsening_usage(conn)
            second = evaluate_alert_policy(conn)
            self.assertEqual(second["decision"], "SUPPRESS")
            third = evaluate_alert_policy(conn)
            self.assertEqual(third["decision"], "SUPPRESS")
            self.assertIn("One alert has already been sent", third["reason"])

    def test_authorized_action_updates_and_verifies_modeled_state(self):
        with memory_db() as conn:
            rejected = apply_energy_action(conn, authorized=False)
            self.assertFalse(rejected["ok"])
            applied = apply_energy_action(conn, authorized=True)
            self.assertTrue(applied["ok"])
            verified = verify_intervention(conn)
            self.assertTrue(verified["ok"])
            self.assertEqual(verified["verification_status"], "verified_success")

    def test_tool_registry_exposes_required_capabilities(self):
        names = {tool["name"] for tool in list_tools()}
        required = {
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
        }
        self.assertTrue(required.issubset(names))

    def test_tool_call_returns_structured_result(self):
        with memory_db() as conn:
            from backend.app.simulator import update_appliance
            update_appliance(conn, "ac", is_on=True, scheduled_hours=6)
            result = call_tool(conn, "estimate_cost_impact", {"appliance": "AC", "period_label": "today"})
            self.assertTrue(result["is_anomaly"])
            self.assertGreater(result["estimated_additional_cost"], 0)

    def test_simulator_all_in_monthly_projection_includes_fixed_charge(self):
        with memory_db() as conn:
            from backend.app.simulator import get_simulator_state, update_appliance
            update_appliance(conn, "ac", is_on=True, scheduled_hours=6.0)
            state = get_simulator_state(conn)
            self.assertEqual(state["projected_monthly_cost"], 3622.5)
            self.assertEqual(state["monthly_fixed_charge"], 125.0)
            self.assertEqual(state["projected_monthly_total_cost"], 3747.5)

    def test_simulator_bill_attribution_reconciles(self):
        with memory_db() as conn:
            from backend.app.simulator import update_appliance
            update_appliance(conn, "ac", is_on=True, scheduled_hours=6)
            result = call_tool(conn, "explain_bill")
            self.assertTrue(result["reconciles"])
            self.assertAlmostEqual(
                result["explained_difference"],
                result["difference"],
                places=2,
            )
            self.assertEqual(result["source"], "virtual_simulator")


if __name__ == "__main__":
    unittest.main()

