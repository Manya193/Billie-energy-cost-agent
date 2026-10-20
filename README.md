# Billie — Energy Cost Intelligence Agent

**Understand energy usage. Estimate costs. Discover opportunities to save energy.**

Billie is an energy cost intelligence application that analyzes simulated household appliance usage, estimates electricity costs, compares consumption against configured baselines, and generates energy-saving recommendations.

The project combines a Python backend, a web frontend, SQLite storage, and an MCP-compatible HTTP interface for agent-tool interaction.

🌐 Live Demo

Access Billie online: https://billie-energy-cost-agent.onrender.com

The live application can be accessed directly through your web browser. No local installation is required to explore the deployed dashboard.

## Features

- **Energy analysis:** Analyze simulated appliance energy consumption.
- **Cost estimation:** Estimate electricity costs using configured calculation logic.
- **Baseline comparison:** Compare modeled usage against configured baselines.
- **Smart recommendations:** Generate actionable energy-saving suggestions.
- **Alerts:** Identify modeled usage or cost conditions that meet configured thresholds.
- **Interactive simulation:** Explore appliance scenarios and their resulting changes.
- **MCP tool integration:** Discover and invoke supported tools through an HTTP endpoint.
- **Tool execution trace:** Inspect tool calls and their results.
- **Automated testing:** Test core application behavior using Python's `unittest` framework.

## Technology Stack

- Python
- HTML, CSS, and JavaScript
- SQLite
- Model Context Protocol (MCP)-compatible HTTP interface
- JSON-RPC-style messages
- Python `unittest`

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
├── LICENSE
├── mcp_check.py
└── README.md
```

## Getting Started

### Prerequisites

- Python installed on your system.
- Git.
- A modern web browser.

### 1. Clone the repository

```bash
git clone https://github.com/Manya193/Billie-energy-cost-agent.git
cd Billie-energy-cost-agent
```

### 2. Create and activate a virtual environment

**Windows PowerShell:**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS/Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

If the project includes a `requirements.txt` file, run:

```bash
python -m pip install -r requirements.txt
```

If it does not, install the dependencies required by the application before starting the servers.

### 4. Configure environment variables

Review `.env.example` for the supported configuration:

```env
BILLIE_HOST=127.0.0.1
BILLIE_PORT=8765
```

Use the configuration expected by the application. Never publish actual secrets or private credentials.

## Running Billie

Run the commands below from the **project root directory**, where the `backend` folder is located.

### Terminal 1 — Start the backend server

```powershell
python -m backend.app.server
```

The backend provides the application's HTTP functionality. The configured local port is `8765`, if that is the port used by the current server implementation.

### Terminal 2 — Start the MCP server

Open another terminal in the same project directory, activate the virtual environment, and run:

```powershell
python -m backend.app.mcp_server
```

The MCP server exposes supported tools through the project's HTTP interface.

Keep both terminals running while testing the application.

### Open the frontend

Open `frontend/index.html` in your browser if the application is designed to run as a standalone static frontend. If the backend serves the frontend itself, use the local URL printed by the backend instead.

The exact browser URL depends on the current server configuration.

## MCP Interface

Billie's MCP-compatible endpoint is configured at:

```text
/mcp
```

The implementation is designed to support JSON-RPC-style operations such as:

- `initialize` — initialize a client connection.
- `tools/list` — discover available tools.
- `tools/call` — invoke a supported tool.

The endpoint address, transport behavior, and supported tool names are determined by the implementation in `backend/app/mcp_server.py`.

### MCP Connectivity Check

The project includes an MCP checking script:

```powershell
python mcp_check.py
```

Run it with the MCP server active and use any additional configuration required by the script.

## Running Tests

From the project root, execute:

```powershell
python -m unittest discover -s tests -v
```

This discovers and runs the tests in the `tests` directory.

## How Billie Works

1. **Input:** The application receives appliance information and simulated usage data.
2. **Processing:** The backend processes the inputs using its energy-analysis logic.
3. **Cost analysis:** The application estimates energy consumption and electricity costs.
4. **Comparison:** Usage is compared against configured baselines.
5. **Recommendations:** The application generates relevant suggestions and alerts.
6. **Tool interaction:** Supported MCP tools allow compatible clients to interact with application functionality.
7. **Visualization:** The frontend presents energy information and tool execution results.

## Contributing

Contributions, suggestions, and bug reports are welcome.

1. Fork the repository.
2. Create a feature branch.
3. Make and test your changes.
4. Submit a pull request describing your changes.

Please do not commit private environment files, credentials, or sensitive local data.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

**Billie — Energy Cost Intelligence Agent**

*Making household energy usage and estimated costs easier to understand through simulation and agent-tool interaction.*
