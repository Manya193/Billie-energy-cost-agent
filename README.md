# Billie — Energy Cost Intelligence Agent

Billie is a runnable hackathon demo of a simulated Alexa+ energy-cost assistant. It helps users understand household energy consumption, explore projected electricity costs, identify unusual usage against configured baselines, and discover potential cost-saving opportunities.

The project combines a lightweight web conversation interface, deterministic energy calculations, a virtual smart-home simulator, and an MCP-style tool interface.

**Important:** Billie uses synthetic data and simulated appliance states. It does not control real appliances, access real smart-home sensors, or claim production Alexa+ integration.

## Key Features

- **Electricity cost intelligence:** Calculates projected energy consumption and electricity costs using configured appliance ratings, schedules, and tariff values.
- **Simulator-grounded alerts:** Identifies when projected appliance usage exceeds configured baseline thresholds.
- **Cost-saving recommendations:** Generates recommendations from the same simulator state and cost calculations used by the dashboard alerts.
- **Virtual smart-home simulator:** Models six household devices and allows their simulated states and schedules to be changed.
- **Appliance-specific routines:** Lets users review and confirm simulated routine changes before updating virtual appliance schedules.
- **MCP-style tool interface:** Provides a self-hosted JSON-RPC HTTP endpoint at `/mcp` for tool discovery and execution.
- **Conversation interface:** Serves a lightweight web UI and API through the Python application.
- **Bill attribution:** Compares projected appliance costs against configured baselines over a 30-day period.
- **Voice output:** Supports browser-based spoken replies and optional spoken alerts where the browser supports the Web Speech API.
- **Automated tests:** Includes a test suite for checking application behavior and core functionality.

## How Billie Works

Billie follows a simulator-grounded architecture:

```text
Web Conversation UI
        |
        v
Application / Orchestration Logic
        |
        v
MCP-Style JSON-RPC Tool Interface
        |
        v
Deterministic Energy Services
        |
        v
Virtual Appliance Simulator
        |
        v
SQLite Database
        |
        v
Calculated Results and Explanations
```

The virtual simulator is the source of truth for appliance states and projected energy usage. Deterministic application logic calculates projected consumption, costs, baseline differences, alerts, and recommendations.

Simulator-related conversation responses use the same underlying data and calculations as the dashboard. This helps keep displayed values, recommendations, and tool results consistent.

## Technology Stack

- **Language:** Python 3.13
- **Backend:** Python standard-library HTTP server
- **Frontend:** HTML, CSS, JavaScript
- **Database:** SQLite
- **Tool communication:** JSON-RPC over HTTP using an MCP-style interface
- **Testing:** Python `unittest`
- **Voice output:** Browser speech synthesis, where supported

The main application uses Python standard-library modules, including `http.server`, `sqlite3`, and `json`. The standalone MCP server requires the MCP Python SDK.

## Project Structure

```text
Billie/
├── backend/
│   └── app/
│       ├── __init__.py
│       ├── agent.py
│       ├── db.py
│       ├── energy.py
│       ├── mcp_server.py
│       ├── server.py
│       ├── simulator.py
│       └── tools.py
├── data/
│   └── billie.sqlite3
├── frontend/
│   ├── app.js
│   ├── index.html
│   └── styles.css
├── tests/
│   ├── test_app_flow.py
│   └── test_billie.py
├── .env.example
├── .gitignore
├── README.md
├── mcp_check.py
├── PRODUCT_FEEDBACK.md
└── FRICTION_LOG.md
```

## Prerequisites

- Python 3.13 or a compatible Python version.
- PowerShell or another terminal.
- A modern web browser.

The main web application uses Python standard-library modules. Install the MCP SDK in the same Python environment if you intend to run the standalone MCP server.

## Installation and Setup

Clone the repository:

```powershell
git clone https://github.com/Manya193/Billie-energy-cost-agent.git
cd Billie-energy-cost-agent
```

If your extracted project folder is named `Billie`, open the terminal in the directory that contains the `backend`, `frontend`, and `tests` folders.

To install the MCP SDK for the standalone MCP server:

```powershell
python -m pip install mcp
```

## Running Billie Locally

### Terminal 1 — Start the MCP server

From the project root:

```powershell
python -m backend.app.mcp_server
```

The standalone MCP server is configured to use port `8766`.

### Terminal 2 — Start the web application

From the same project root:

```powershell
python -m backend.app.server
```

The web application uses port `8765` by default.

Open the application in your browser:

http://127.0.0.1:8765

The web application and standalone MCP server are separate processes. Run the MCP server when you need to test its standalone endpoint.

## Virtual Smart-Home Simulator

Billie includes six simulated household devices:

1. Air conditioner (AC)
2. Living-room lights
3. Kitchen refrigerator
4. Electric vehicle (EV) charger
5. Home theatre
6. Water heater

The simulator provides appliance states, scheduled operating hours, projected daily energy consumption, cost estimates, baseline comparisons, and monthly projections.

### Simulator API

| Endpoint | Purpose |
|---|---|
| `GET /api/simulator` | Retrieves the current simulated appliance states and energy projections. |
| `POST /api/simulator/update` | Updates a simulated appliance state or schedule. |
| `POST /api/simulator/reset` | Restores the default virtual appliance states. |

Example update request:

```json
{
  "id": "ac",
  "is_on": true,
  "scheduled_hours": 6
}
```

These endpoints modify the virtual simulator only. They do not send commands to physical appliances.

### Energy Calculations

Projected daily energy consumption is calculated using the appliance's rated power and scheduled operating hours when the appliance is switched on.

The simulator's configured tariff is used to estimate electricity costs. Actual results depend on the configured appliance values, schedules, tariff, and baseline assumptions.

## Demo Walkthrough

1. Start the web application and open the dashboard.
2. Inspect the six simulated appliance cards and their projected energy usage.
3. Review the energy alerts and matching cost-saving recommendations.
4. Select **Simulate worsening** to apply the predefined scenario that increases AC usage.
5. Observe how the projected consumption, alert, and recommendation update together.
6. Ask Billie about current usage, a particular appliance, active alerts, or potential savings.
7. Request an appliance-specific routine, review the proposed change, and confirm it.
8. Verify that the virtual schedule and associated calculations reflect the confirmed change.

The exact behavior depends on the simulator state and the application's configured rules.

## MCP-Style JSON-RPC Interface

Billie includes a self-hosted JSON-RPC HTTP endpoint at:

`/mcp`

The implementation supports the methods needed by this demo:

- `initialize`
- `tools/list`
- `tools/call`

The endpoint uses HTTP POST requests containing JSON-RPC messages. The website and MCP server use the same SQLite database file, allowing simulator changes to be reflected in tool results.

Actual MCP tool calls and their results can be inspected in the conversation trace after a Billie chat request.

This is a project-specific MCP-style implementation. Do not assume that every feature or transport behavior of a complete MCP implementation is supported without further testing.

## Simulated Bill Attribution

Billie's bill-attribution tools compare the current virtual appliance schedules with configured appliance baselines over a 30-day projection.

The comparison includes:

- Estimated monthly appliance costs.
- Cost increases or reductions relative to the baseline.
- The projected net bill difference.
- Reconciliation of appliance-level cost differences using the configured tariff.

These results are synthetic projections. They do not represent an actual electricity utility invoice or verified household consumption.

## Alerts and Voice Output

Billie's dashboard displays simulator-generated alerts and corresponding cost-saving recommendations.

The alerts currently use configured baseline thresholds applied to projected daily usage. They are not real sensor alerts.

The browser UI also supports spoken replies and controls for spoken alerts where browser speech synthesis is available. Users can mute spoken alerts or request that active alerts be read aloud.

Voice playback depends on browser capabilities and permissions. Visual alerts remain available if speech output is unavailable.


## Synthetic Data and Limitations

Billie uses synthetic readings, bills, baselines, alerts, and interventions. The SQLite database stores the demo's application and simulator state.

Keep the following limitations in mind:

- Appliance states and schedules are virtual.
- Energy consumption and electricity costs are estimates based on configured assumptions.
- Alerts are generated from projected usage and configured thresholds.
- Bill attribution compares simulated projections with configured baselines.
- The demo does not control physical appliances or access real smart-home sensors.
- Production Alexa+ integration is not implemented.
- Amazon Bedrock integration is not implemented.
- General questions may use the optional Ollama/MCP agent when available; its availability and behavior depend on the local configuration.

## Running the Tests

From the project root, run:

```powershell
python -m unittest discover -s tests -v
```

The tests exercise application flows and core Billie functionality.

## Future Improvements

Potential future improvements include:

- Integrating and testing a language model for natural-language explanations.
- Adding real energy-meter integrations with appropriate authorization.
- Supporting persistent deployment storage for simulator state.
- Improving monitoring, logging, and deployment configuration.
- Expanding automated tests for tool communication and error handling.

These are potential improvements, not claims about features already implemented.

## Project Goal

Billie demonstrates how deterministic energy calculations, a virtual smart-home simulator, tool-based orchestration, and a conversational interface can work together to explain projected household energy costs and suggest potential savings.

Its central design principle is that energy figures and simulator-grounded findings should come from the application's calculation logic rather than being invented by a language model.
