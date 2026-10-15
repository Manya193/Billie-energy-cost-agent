# Billie — Development Friction Log

## 1. Codex Execution Helper Failure

**Date:** October 10, 2026

- **Tool and environment:** Codex desktop command execution helper on Windows.
- **Task attempted:** Run basic workspace inspection commands.
- **Steps taken:** Attempted to execute commands during development.
- **Expected result:** Approved sandboxed commands should launch normally.
- **Actual result:** Command execution was blocked by the following error:

  `Rejected("Failed to create unified exec process: helper_unknown_error: setup refresh had errors")`

- **Severity:** High during setup.
- **Root cause:** The local execution-helper setup appeared to be in an inconsistent state; the exact underlying cause was not established.
- **Workaround:** Temporarily used explicitly approved, read-only escalated commands.
- **Resolution:** Restarting Windows restored normal execution.
- **Actionable suggestion:** Display a specific recovery action when execution-helper setup refresh fails.

## 2. MCP Tool Execution and State Verification

- **Tool and environment:** Billie’s self-hosted MCP endpoint and local application database.
- **Task attempted:** Test tool discovery, energy-usage retrieval, and simulated actions.
- **Expected result:** Tool calls should provide clear results, and permitted state-changing actions should have verifiable outcomes.
- **Actual result:** MCP connection and tool discovery succeeded, and energy-usage data was returned. During one test, a direct action was refused and the database remained unchanged.
- **Severity:** Medium during testing.
- **Workaround:** Checked the tool response and database state rather than assuming the action had succeeded.
- **Resolution:** No confirmed underlying defect or final fix was established.
- **Actionable suggestion:** Provide explicit explanations for tool refusals, permissions, and state-change outcomes so developers can distinguish intentional safeguards from integration problems.

## 3. Energy Cost Calculation and Baseline Consistency

- **Task attempted:** Develop and test appliance-level energy-cost calculations and comparisons against configured baselines.
- **Expected result:** Projected costs, usage comparisons, alerts, and recommendations should use consistent calculation rules.
- **Actual result:** This area required careful coordination between the application's energy calculations, baseline comparisons, and displayed insights. A specific failure message is not available in the retained notes.
- **Severity:** To be confirmed based on the actual development impact.
- **Workaround:** Use explicit calculations and simulator-backed results to support transparent comparisons.
- **Actionable suggestion:** Provide clear calculation definitions and consistent baseline handling across dashboards, alerts, and agent responses.

## 4. Monthly Energy Cost Interpretation

- **Task attempted:** Present understandable monthly energy-cost estimates.
- **Expected result:** Users should be able to distinguish energy-consumption charges from fixed charges included in a broader bill total.
- **Actual result:** The distinction between energy-only costs and totals that include fixed charges required attention during the application's design.
- **Severity:** To be confirmed.
- **Workaround:** Keep the cost calculation and displayed labels explicit about what is included.
- **Actionable suggestion:** Encourage clear cost breakdowns and labels so users can understand exactly what a displayed estimate represents.

## 5. Simulator and Application State Verification

- **Task attempted:** Test appliance simulations and ensure that resulting usage, alerts, and recommendations reflect the current simulated state.
- **Expected result:** After a permitted simulation changes appliance conditions, the relevant application views should reflect the updated state consistently.
- **Actual result:** State consistency was an important testing concern. The retained notes do not establish a separate confirmed failure or exact error message for this item.
- **Severity:** To be confirmed.
- **Workaround:** Verify the resulting application state and displayed insights after simulation actions.
- **Actionable suggestion:** Provide clear confirmation of state-changing operations and a straightforward way to inspect the updated state.

## Overall Feedback

Developing Billie highlighted the importance of reliable developer tooling, transparent tool execution, consistent energy-cost calculations, clear cost breakdowns, and verifiable simulator state. Better diagnostic messages, explicit calculation definitions, and clear operation outcomes would help developers build more reliable, transparent, tool-driven applications.

