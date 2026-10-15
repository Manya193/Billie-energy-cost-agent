import anyio
from mcp import ClientSession
from backend.app.db import connect
from mcp.client.streamable_http import streamable_http_client

def snapshot_state():
    conn = connect()
    try:
        tables = [
            "interventions",
            "appliance_state",
            "pending_actions",
        ]
        snapshot = {}

        for table in tables:
            rows = conn.execute(
                f"SELECT * FROM {table} ORDER BY rowid"
            ).fetchall()
            snapshot[table] = [tuple(row) for row in rows]

        return snapshot
    finally:
        conn.close()

async def main():
    url = "http://127.0.0.1:8766/mcp"

    print("Connecting to Billie MCP server...")

    async with streamable_http_client(url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # 1. Initialize MCP connection
            await session.initialize()
            print("\nMCP CONNECTION: OK")

            # 2. Discover available tools
            tools_result = await session.list_tools()
            tool_names = [tool.name for tool in tools_result.tools]

            print(f"\nTOTAL TOOLS: {len(tool_names)}")
            print("TOOLS:", tool_names)

            # 3. Test current energy usage
            print("\n--- ENERGY USAGE TEST ---")
            energy_result = await session.call_tool(
                "get_current_energy_usage",
                {},
            )

            print("ENERGY RESULT:", energy_result)
            print("ENERGY CALL ERROR:", energy_result.is_error)
            
            print("\n--- BILL EXPLANATION TEST ---")
            bill_result = await session.call_tool(
                "explain_bill",
                {},
            )

            print("BILL EXPLANATION:", bill_result)
            print("BILL EXPLANATION ERROR:", bill_result.is_error)

            # 4. Test whether direct action execution is blocked
            print("\n--- ACTION SECURITY TEST ---")
            if "apply_energy_action" not in tool_names:
                print("SECURITY TEST: FAIL - action tool not registered")
            else:
                before = snapshot_state()
                action_result = await session.call_tool(
                    "apply_energy_action",
                    {
                        "action": "set_ac_eco_routine",
                        "authorized": True,
                        "reason": "MCP security test",
                    },
                )

                print("ACTION RESULT:", action_result)
                print("ACTION CALL ERROR:", action_result.is_error)

                after = snapshot_state()
                print("DATABASE UNCHANGED:", before == after)

                response_text = " ".join(
                    item.text
                    for item in action_result.content
                    if hasattr(item, "text")
                )

                if (
                    not action_result.is_error
                    and (
                        "disabled" in response_text.lower()
                        or "cannot authorize" in response_text.lower()
                        or "cannot be authorized" in response_text.lower()
                    )
                ):
                    print("SECURITY TEST: REFUSAL MESSAGE RECEIVED")
                    print(
                        "IMPORTANT: Verify the database/state was unchanged "
                        "before declaring the test passed."
                    )
                else:
                    print(
                        "SECURITY TEST: NEEDS REVIEW - "
                        "inspect the action result and database state."
                    )

    print("\nMCP TEST RUN FINISHED.")


if __name__ == "__main__":
    anyio.run(main)