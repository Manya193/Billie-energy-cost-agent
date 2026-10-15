
from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from .db import connect, ensure_demo_data
from .tools import call_tool


mcp = MCPServer("billie-energy-agent")


def invoke(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call an existing Billie tool using its own database connection."""
    conn = connect()
    try:
        ensure_demo_data(conn)
        result = call_tool(conn, name, arguments or {})
        return dict(result)
    finally:
        conn.close()


@mcp.tool()
def get_current_energy_usage() -> dict[str, Any]:
    """Get today's modeled energy usage."""
    return invoke("get_current_energy_usage")


@mcp.tool()
def get_bill_history() -> dict[str, Any]:
    """Retrieve historical synthetic electricity bills."""
    return invoke("get_bill_history")


@mcp.tool()
def get_tariff() -> dict[str, Any]:
    """Retrieve the modeled electricity tariff."""
    return invoke("get_tariff")


@mcp.tool()
def get_appliance_usage(period_label: str = "current") -> dict[str, Any]:
    """Get appliance usage for a period such as current, previous, or today."""
    return invoke("get_appliance_usage", {"period_label": period_label})


@mcp.tool()
def get_user_baseline(appliance: str = "AC") -> dict[str, Any]:
    """Get the expected usage baseline for an appliance."""
    return invoke("get_user_baseline", {"appliance": appliance})


@mcp.tool()
def detect_energy_anomaly(
    appliance: str = "AC",
    period_label: str = "today",
) -> dict[str, Any]:
    """Detect unusual modeled energy usage."""
    return invoke(
        "detect_energy_anomaly",
        {"appliance": appliance, "period_label": period_label},
    )


@mcp.tool()
def estimate_cost_impact(
    appliance: str = "AC",
    period_label: str = "today",
) -> dict[str, Any]:
    """Estimate the additional cost associated with appliance usage."""
    return invoke(
        "estimate_cost_impact",
        {"appliance": appliance, "period_label": period_label},
    )


@mcp.tool()
def explain_bill() -> dict[str, Any]:
    """Explain the bill using history and modeled usage contributors."""
    return invoke("explain_bill")


@mcp.tool()
def evaluate_alert_policy(
    appliance: str = "AC",
    period_label: str = "today",
) -> dict[str, Any]:
    """Evaluate whether an energy alert should be sent."""
    return invoke(
        "evaluate_alert_policy",
        {"appliance": appliance, "period_label": period_label},
    )


@mcp.tool()
def record_user_response(
    response: str = "acknowledged",
    appliance: str = "AC",
    period_label: str = "today",
) -> dict[str, Any]:
    """Record a user's response to an energy alert."""
    return invoke(
        "record_user_response",
        {
            "response": response,
            "appliance": appliance,
            "period_label": period_label,
        },
    )


@mcp.tool()
def manage_alert_state() -> dict[str, Any]:
    """Read and manage the current energy alert state."""
    return invoke("manage_alert_state")


@mcp.tool()
def apply_energy_action(
    action: str = "set_ac_eco_routine",
    authorized: bool = False,
    reason: str = "MCP request",
) -> dict[str, Any]:
    """Request an energy action. Direct MCP calls cannot authorize changes."""
    # Never trust an MCP client's authorized=True argument.
    # The existing Billie confirmation flow remains the authorization gate.
    return {
        "ok": False,
        "action_applied": False,
        "error": (
            "Direct MCP action execution is disabled. "
            "Use Billie's explicit confirmation flow."
        ),
    }


@mcp.tool()
def verify_intervention() -> dict[str, Any]:
    """Verify the latest modeled energy intervention."""
    return invoke("verify_intervention")


@mcp.tool()
def simulate_worsening_usage() -> dict[str, Any]:
    """Increase synthetic usage for a demo scenario."""
    return invoke("simulate_worsening_usage")


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8766,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )
