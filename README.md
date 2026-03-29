# inbiot-data-api-mcp

**Repository:** [github.com/miguel-escribano/inbiot-data-api-mcp](https://github.com/miguel-escribano/inbiot-data-api-mcp)

## What is this?

A stateless MCP server that wraps InBiot sensor APIs and OpenWeather into 9 structured tools for air quality monitoring. Raw data only — no scoring, no compliance logic, no recommendations.

**No persona. No prompts. No resources.** Just clean JSON tools. Every tool is registered with read-only / non-destructive hints for MCP clients.

All intelligence (persona, WELL knowledge, compliance assessment, skill workflows) lives in the consumer layer. The primary consumer today is the Anne plugin: [inbiot-Anne-IAQ-consultant-as-a-plugin](https://github.com/miguel-escribano/inbiot-Anne-IAQ-consultant-as-a-plugin).

```
┌─────────────────────────────────┐     ┌──────────────────────────────────┐
│  Plugin (intelligence)          │     │  This server (data)              │
│  inbiot-Anne-IAQ-consultant-... │     │  inbiot-data-api-mcp             │
│                                 │     │                                  │
│  CLAUDE.md  = Anne's persona    │────>│  server.py  = MCP entry point    │
│  skills/    = workflows         │ MCP │  src/api/   = HTTP clients       │
│  knowledge/ = WELL thresholds   │     │  src/tools/ = tool definitions   │
│  agents/    = agent config      │     │  src/utils/ = cache, dates, etc  │
│  .mcp.json  = server connection │     │                                  │
└─────────────────────────────────┘     └──────────────────────────────────┘
```

---

## Quick Start (Remote Server)

No local install: point your MCP client at the hosted SSE endpoint (path is deployment-specific; token required).

### Cursor (`%USERPROFILE%\.cursor\mcp.json`)

Merge this under `mcpServers` (create the key if missing):

```json
{
  "mcpServers": {
    "inbiot-data-api-mcp": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://mcp.miguel-escribano.com/inbiot-data-api-mcp/sse",
        "--header",
        "X-MCP-Token: <YOUR_TOKEN>"
      ]
    }
  }
}
```

### Other clients

Use the same `command` / `args` block inside your app's MCP config shape (e.g. Claude Desktop: `%APPDATA%\Claude\claude_desktop_config.json`; VS Code: `.vscode/mcp.json` or user MCP settings).

| IDE / App | Config file |
|-----------|-------------|
| **Cursor** | `%USERPROFILE%\.cursor\mcp.json` |
| **Claude Desktop** | `%APPDATA%\Claude\claude_desktop_config.json` |
| **VS Code** | `.vscode/mcp.json` or **MCP: Open User Configuration** |

> **Requirements:** [Node.js 18+](https://nodejs.org/). To request a token, email **mescribano@inbiot.es**.

---

## Tools (9)

| Group | Tool | What it does |
|-------|------|-------------|
| Monitoring | `list_devices` | List configured devices (`id`, `name`, optional `building`) |
| | `get_latest_measurements` | Current sensor values for one device |
| | `get_historical_data` | Historical series with statistics and trend direction |
| | `get_all_devices_summary` | All devices: key metrics (CO2, PM2.5, temperature, humidity, IAQ, thermal) |
| Analytics | `get_data_statistics` | Min/max/mean/median/quartiles/trend for a parameter over a range |
| | `detect_patterns` | Hourly and daily patterns (peak hours, worst/best days) |
| | `export_historical_data` | CSV or JSON export, raw or time-aggregated |
| Weather | `outdoor_snapshot` | Outdoor weather + OpenWeather air quality for device coordinates |
| | `indoor_vs_outdoor` | Side-by-side indoor vs outdoor with filtration effectiveness |

All tools return JSON-friendly structures. Tool responses avoid Markdown so clients can parse them cheaply.

---

## Key constraints

- **InBiot API: 6 requests per device per hour.** The server uses a TTL cache (10 min for latest data, 60 min for historical, 5 min for weather) so repeated calls for the same device reuse cached responses.
- **OpenWeather API key is optional.** Without it, `outdoor_snapshot` and `indoor_vs_outdoor` return a structured error dict instead of crashing the server.

---

## Local Setup

<details>
<summary><strong>Click to expand</strong></summary>

### Requirements

- Python 3.10+
- InBiot MICA device(s) with API credentials from [My inBiot](https://my.inbiot.es)
- OpenWeather API key (optional) from [OpenWeather](https://openweathermap.org/api)

### Install

```bash
git clone https://github.com/miguel-escribano/inbiot-data-api-mcp.git
cd inbiot-data-api-mcp

python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Configure

Create `inbiot-config.yaml` in the project root:

```yaml
openweather_api_key: "your-key"    # optional

devices:
  office:
    name: "Main Office"
    api_key: "from-my.inbiot.es"
    system_id: "from-my.inbiot.es"
    latitude: 40.416775
    longitude: -3.703790
    building: "HQ Madrid"          # optional, for grouping
```

See `inbiot-config.example.yaml` for the full template. Credentials come from [My inBiot Platform](https://my.inbiot.es) -> Device Settings.

Config can also be passed as JSON or environment variables -- see `src/config/loader.py`.

### Run

```bash
python server.py
# or, after editable install:
inbiot-data-api-mcp
```

Both use **stdio** transport (typical for Cursor, Claude Code, and local MCP clients).

### Tests

```bash
pytest tests/ -v
```

</details>

---

## Project structure

```
server.py                       # MCP entry point, wires all tools together
src/
  api/
    inbiot.py                   # InBiot HTTP client (cached, connection-pooled)
    openweather.py              # OpenWeather HTTP client (cached, connection-pooled)
  tools/
    monitoring/tools.py         # 4 monitoring tools
    analytics/tools.py          # 3 analytics tools
    weather/tools.py            # 2 weather tools
  models/schemas.py             # Pydantic models (DeviceConfig, ParameterData, OutdoorConditions...)
  config/
    loader.py                   # YAML/JSON/env config loader
    validator.py                # Config validation
  utils/
    cache.py                    # AsyncTTLCache (in-memory, monotonic clock)
    aggregation.py              # Statistics and time-series aggregation
    normalization.py            # Parameter name aliases (pm2.5->pm25, tvoc->vocs, etc.)
    exporters.py                # CSV/JSON export formatters
    retry.py                    # Exponential backoff for API calls
    dates.py                    # Date parsing for tool parameters
    validation.py               # Shared validation helpers
tests/
  test_cache.py
  test_api_clients.py
  test_tools.py
  test_skills_integration.py    # manual smoke script (not collected by pytest)
```

---

## Architecture note

This server is intentionally a **thin data pipe**. WELL compliance scoring, threshold interpretation, and health recommendations previously lived here but were moved to the plugin layer in March 2025. The rationale:

- Thresholds from WELL v2, ASHRAE 62.1/55, and WHO guidelines are normative data that domain experts (CSO, WELL APs) should review and tweak directly — easier in Markdown than in Python.
- Different clients may interpret the same raw data differently depending on their context (certification prep vs daily monitoring vs sales demo).
- Keeping the MCP stateless and opinion-free makes it a stable dependency for any number of consumers.

**If** multiple MCP clients eventually need consistent, reproducible WELL scoring, the compliance engine can return as a versioned service layer. Until then, the plugin's `knowledge/` files are the single source of truth for thresholds and interpretation.

---

## Links

- [This repo](https://github.com/miguel-escribano/inbiot-data-api-mcp) — MCP data server
- [Anne plugin](https://github.com/miguel-escribano/inbiot-Anne-IAQ-consultant-as-a-plugin) — persona, skills, marketplace metadata
- [InBiot](https://www.inbiot.es/) — Air quality monitoring devices
- [My inBiot Platform](https://my.inbiot.es) — Device management and API credentials
- [WELL Building Standard](https://www.wellcertified.com/) — Certification program
- [Model Context Protocol](https://modelcontextprotocol.io/) — MCP specification

## License
MIT
