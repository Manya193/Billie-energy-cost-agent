# Billie — Energy Cost Intelligence Agent
## Development Friction Log

This document records technical issues encountered while developing and testing Billie, the troubleshooting steps taken, their impact, and actionable improvements identified during development.

## 1. MCP Server Connectivity Failure

**Task attempted:** Verify connectivity between the MCP test client and the local MCP server.

**Steps taken:** Executed `mcp_check.py` to connect to the configured MCP endpoint and test tool communication.

**Expected result:** The client should connect to the MCP server, discover available tools, and retrieve energy data.

**Actual result:** The test failed with `httpx.ConnectError: All connection attempts failed`. The client could not establish a connection to the configured endpoint.

**Severity:** High — blocked the connectivity test.

**Workaround:** Investigate the MCP server process, endpoint configuration, and server availability before rerunning the test.

**Actionable suggestion:** Add server health checks, endpoint validation, connection diagnostics, and clear error messages that distinguish an unavailable server from an incorrect endpoint.

## 2. Windows Command-Execution Failure

**Task attempted:** Execute development and testing commands through the desktop command-execution helper.

**Steps taken:** Attempted to execute commands and examined the reported environment error.

**Expected result:** Commands should execute normally in the development environment.

**Actual result:** Execution was rejected with the error:

`Failed to create unified exec process: helper_unknown_error: setup refresh had errors`

**Severity:** Medium — interrupted the development workflow.

**Workaround:** Restarted Windows, after which normal command execution resumed.

**Actionable suggestion:** Improve environment-refresh diagnostics and recovery mechanisms so developers can identify and resolve command-execution failures without restarting the system.

## 3. MCP Tool Execution and State Verification

**Task attempted:** Discover MCP tools, retrieve energy usage, and verify the outcome of a state-changing intervention.

**Steps taken:** Tested tool discovery, queried energy data, attempted a direct action, and checked the database state.

**Expected result:** Tool calls should return structured results, and a successful state-changing operation should be reflected in the stored application state.

**Actual result:** Tool discovery and energy retrieval succeeded in one test. However, the direct action was refused, and the database remained unchanged. The precise cause was not established.

**Severity:** High — affected verification of state-changing operations.

**Workaround:** Checked the resulting application state instead of assuming the attempted operation had succeeded.

**Actionable suggestion:** Clearly distinguish read-only tools from state-changing tools, provide explicit authorization feedback, and verify the final state after every permitted intervention.

## 4. Energy Cost and Baseline Consistency

**Task attempted:** Validate simulated electricity costs, historical bill comparisons, appliance-level cost contributions, and baseline calculations.

**Steps taken:** Compared simulated consumption, tariff assumptions, historical bill values, and appliance-level explanations.

**Expected result:** Consumption figures, estimated costs, baseline comparisons, and appliance-level contributions should be internally consistent.

**Actual result:** Calculation and baseline consistency required additional scrutiny. The analysis also needed to distinguish consumption charges from fixed charges and avoid attributing unexplained bill differences to unsupported causes.

**Severity:** High — inaccurate estimates could reduce user trust in the energy analysis.

**Workaround:** Cross-check calculations against the simulated readings and tariff assumptions, and keep unexplained differences separate from supported explanations.

**Actionable suggestion:** Add automated calculation tests, validate baseline assumptions, separate fixed charges from consumption charges, and report unexplained cost differences transparently.

## 5. Virtual Smart-Home State Consistency

**Task attempted:** Verify consistency between virtual appliance settings, simulated energy usage, alerts, and savings recommendations.

**Steps taken:** Examined how simulated device states relate to the energy calculations and dashboard insights.

**Expected result:** Changes to simulated appliances should propagate consistently to energy consumption, estimated costs, relevant alerts, and recommendations.

**Actual result:** Consistency across these connected components required verification. The available test evidence did not establish a single confirmed root cause.

**Severity:** Medium to High — inconsistent outputs could make the simulation misleading.

**Workaround:** Cross-check appliance states and calculated outputs instead of relying on a single dashboard indicator.

**Actionable suggestion:** Maintain a consistent simulation state and add end-to-end tests that verify appliance changes against updated usage, costs, alerts, and recommendations.

## Overall Impact and Lessons Learned

These issues highlighted the practical challenges of integrating a locally hosted language model, MCP tools, a Python backend, and a stateful virtual smart-home simulation.

The debugging process reinforced several important engineering principles:

- Validate service connectivity before testing dependent components.
- Treat tool execution results and state changes as separate things to verify.
- Keep energy calculations consistent with the underlying tariff and simulation assumptions.
- Distinguish measured or simulated data from estimates and unsupported explanations.
- Make failures observable through clear errors, structured tool results, and repeatable tests.

## Suggested Improvements

The main opportunities for improvement are stronger integration testing, clearer MCP connection diagnostics, reliable state verification, consistent energy calculations, and more transparent error handling.

These improvements can help make Billie more reliable, explainable, and trustworthy when investigating household energy usage and recommending potential cost savings.

**Note:** Billie uses a virtual smart-home simulation. Energy readings and cost estimates presented by the project should therefore be interpreted according to the simulation data and assumptions, rather than as verified measurements of a real household.
