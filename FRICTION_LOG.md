# Friction Log

## 2026-10-10

- Tool/SDK/version and environment: Codex desktop command execution helper on Windows.
- Task attempted: run simple workspace inspection commands.
- Expected behavior: sandboxed commands should launch.
- Actual behavior and exact error: `Rejected("Failed to create unified exec process: helper_unknown_error: setup refresh had errors")`.
- Severity: high during setup, because it blocked inspection.
- Root cause if established: local execution helper setup state was broken; Windows restart restored normal execution.
- Workaround: temporarily used explicitly approved read-only escalated commands.
- Fix: restart Windows / refresh Codex execution helper.
- Time lost: initial diagnostic cycle.
- Actionable feedback: surface helper setup refresh failures with a targeted recovery action in the UI.

