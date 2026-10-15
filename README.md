# Billie — Energy Cost Intelligence Agent

Billie is a runnable hackathon demo for a simulated Alexa+ energy-cost assistant. It combines:

- Deterministic electricity bill intelligence.
- Simulator-grounded energy alerts and matching cost-saving recommendations.
- Authorized simulated actions and verification.
- A self-hosted JSON-RPC MCP-style Streamable HTTP endpoint at `/mcp`.
- A lightweight web conversation UI served by the same Python app.

This demo uses clearly labeled synthetic data. It does not control real appliances and does not claim production Alexa+ integration.

## Foundation

The repository was empty, so the first implementation uses Python 3.13 standard-library modules only: `http.server`, `sqlite3`, `json`, and `unittest`. This keeps the demo reproducible while preserving the intended architecture:

Simulated Alexa+ web UI -> orchestration endpoint -> MCP tool calls -> deterministic energy services -> SQLite state -> explanation layer.

The MCP endpoint implements the JSON-RPC methods needed for this demo:

- `initialize`
- `tools/list`
- `tools/call`

The transport is a single HTTP endpoint, `/mcp`, using POST requests with JSON-RPC messages, matching the Streamable HTTP direction rather than the older standalone SSE-first style.

## Run (two PowerShell terminals)

Install the MCP SDK in the same Python environment used for the app (`python -m pip install mcp`).

Terminal 1 — start the MCP server on port 8766:

```powershell
python -m backend.app.mcp_server
```

Terminal 2 — from the same project root, start the website/API on port 8765:

```powershell
python -m backend.app.server
```

Then open:

```text
http://127.0.0.1:8765
```

## Test

```powershell
python -m unittest discover -s tests
```

## Demo Flow

1. Open the web app and inspect the six simulated appliance cards.
2. The Energy alerts and Cost-saving recommendations are generated from the same simulator state and use the same baseline, projected kWh/day, and tariff.
3. Click "Simulate worsening" to switch the AC on with a six-hour daily schedule; the AC's projected usage, alert, and recommendation update together.
4. Ask Billie about current usage, an appliance, active alerts, or potential savings. Simulator-related answers are grounded in the current appliance state.
5. Request an appliance-specific routine, review the proposal, and confirm it. The confirmed routine updates the virtual appliance schedule and refreshes the calculations.

## Bedrock

The explanation layer is structured so Amazon Bedrock can be added as the wording provider while deterministic findings remain the numerical source of truth. This local demo currently uses the deterministic fallback because no AWS credentials or Bedrock model access were configured or tested in this environment.

## Synthetic Data

All readings, bills, baselines, alerts, and interventions are synthetic and stored in `data/billie.sqlite3` when the app runs.



## Virtual Smart-Home Simulator

The dashboard includes a deterministic virtual home with six devices: AC, living-room lights, kitchen fridge, EV charger, home theatre, and water heater.

- `GET /api/simulator` returns appliance states, scheduled hours, projected daily kWh, cost estimates, baseline comparisons, and monthly projections.
- `POST /api/simulator/update` accepts `{"id":"ac","is_on":true}` and/or `{"id":"ac","scheduled_hours":6}`.
- `POST /api/simulator/reset` restores the virtual appliance defaults.
- Energy projections are calculated from rated kW × scheduled hours when a device is switched on. These are simulated estimates, not physical measurements.

## Simulator-backed bill attribution update

The `get_bill_history` and `explain_bill` MCP tools now compare the current appliance schedule against the simulator's configured appliance baselines over a 30-day projection. Each appliance's monthly cost delta is shown as an increase or reduction; the sum reconciles to the net projected bill difference using the configured tariff. This is explicitly a synthetic simulator comparison, not a claim about an actual utility invoice. The dashboard labels the comparison as a simulated projection versus baseline. Actual MCP tool calls and their results appear in the trace after a Billie chat request.


## End-to-end source-of-truth notes

- The website and MCP server use the same SQLite database file, so simulator changes are visible to MCP tools.
- The virtual appliance simulator is the single source of truth for projected usage alerts, cost-saving recommendations, and simulator-related chat answers. Alert and recommendation entries share the same qualifying set and cost calculation.
- Simulator-related chat answers use the deterministic `simulator_grounded` path so a language model cannot independently recalculate or invent appliance figures. General questions may still use the Ollama/MCP agent when available.
- Bill attribution compares the current scheduled routine with the configured appliance baseline over 30 days. The signed appliance deltas reconcile to the projected net difference. All amounts are synthetic projections, not an actual utility invoice.
- Automated alerts currently use configured baseline thresholds against projected daily usage. Simulated-time accumulation is available separately; do not describe projected warnings as real sensor alerts.

### Voice alerts and concise recommendations

The browser UI supports spoken Billie replies plus a separate **Alerts spoken / Alerts muted** control. Newly appearing simulator alerts are announced aloud once; **Read active alerts** reads the current alert cards on demand. Visual alerts remain available as a fallback. Browser speech output requires a browser that supports `speechSynthesis`; some browsers require a user click before audio playback.

Simulator-generated savings suggestions use the exact same appliance, projected daily usage, baseline, threshold, and tariff values as the visible alert. Accumulated energy is displayed separately from projected kWh/day so unlike measures are not compared. Responses stay concise and spoken-friendly.
