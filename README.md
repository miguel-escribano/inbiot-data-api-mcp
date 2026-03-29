# inbiot-data-api-mcp (MCP Server)

**Repository:** [github.com/miguel-escribano/inbiot-data-api-mcp](https://github.com/miguel-escribano/inbiot-data-api-mcp)

## What is this?

The data layer behind Anne, the IAQ consultant plugin. A stateless MCP server that wraps InBiot sensor APIs and OpenWeather into 14 structured tools for air quality monitoring and WELL Building Standard compliance.

**No persona. No prompts. No resources.** Just clean JSON tools. Every tool is registered with read-only / non-destructive hints for MCP clients.

The intelligence (Anne's persona, WELL knowledge, skill workflows) lives in the Anne plugin: [inbiot-Anne-IAQ-consultant-as-a-plugin](https://github.com/miguel-escribano/inbiot-Anne-IAQ-consultant-as-a-plugin). This server supplies raw data and scores; the plugin turns that into guidance.

```
┌─────────────────────────────────┐     ┌──────────────────────────────────┐
│  Plugin (intelligence)          │     │  This server (data)              │
│  inbiot-Anne-IAQ-consultant-... │     │  inbiot-data-api-mcp             │
│                                 │     │                                  │
│  CLAUDE.md  = Anne's persona    │────>│  server.py  = MCP entry point    │
│  skills/    = slash commands    │ MCP │  src/api/   = HTTP clients       │
│  knowledge/ = standards docs    │     │  src/skills/= tool definitions   │
│  hooks.json = session greeting  │     │  src/well/  = compliance engine  │
│  .mcp.json  = server connection │     │  src/utils/ = cache, dates, etc  │
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
        "https://mcp.miguel-escribano.com/inbiot-mcp-for-Anne-IAQ-consultant-as-a-plugin/sse",
        "--header",
        "X-MCP-Token: <YOUR_TOKEN>"
      ]
    }
  }
}
```

### Other clients

Use the same `command` / `args` block inside your app’s MCP config shape (e.g. Claude Desktop: `%APPDATA%\Claude\claude_desktop_config.json`; VS Code: `.vscode/mcp.json` or user MCP settings).

| IDE / App | Config file |
|-----------|-------------|
| **Cursor** | `%USERPROFILE%\.cursor\mcp.json` |
| **Claude Desktop** | `%APPDATA%\Claude\claude_desktop_config.json` |
| **VS Code** | `.vscode/mcp.json` or **MCP: Open User Configuration** |

> **Requirements:** [Node.js 18+](https://nodejs.org/). To request a token, email **mescribano@inbiot.es**.

---

## Tools (14)

| Group | Tool | What it does |
|-------|------|-------------|
| Monitoring | `list_devices` | List configured devices (`id`, `name`, optional `building` per row) |
| | `get_latest_measurements` | Current sensor values for one device |
| | `get_historical_data` | Historical series with statistics and trend direction |
| | `get_all_devices_summary` | All devices: key metrics (CO2, PM2.5, temperature, humidity, IAQ, thermal) as flat numeric fields; errors per device when a fetch fails |
| Analytics | `get_data_statistics` | Min/max/mean/median/quartiles/trend for a parameter over a range |
| | `detect_patterns` | Hourly and daily patterns (peak hours, worst/best days) |
| | `export_historical_data` | CSV or JSON export, raw or time-aggregated |
| Compliance | `well_compliance_check` | WELL snapshot: overall score, %, level, per-parameter scores/levels (no narrative recommendation block in JSON) |
| | `well_feature_compliance` | Per WELL feature (A01–A08, T01–T07): score, max, %, derived level, compliant flag |
| | `health_recommendations` | Parameters at risk: score, severity, optional gap/target vs thresholds |
| | `well_certification_roadmap` | Next certification tier, points needed, top ROI-style opportunities with gaps and targets |
| | `compliance_over_time` | Sustained compliance % per parameter over a date range |
| Weather | `outdoor_snapshot` | Outdoor weather + OpenWeather air payload for device coordinates |
| | `indoor_vs_outdoor` | Side-by-side indoor vs outdoor; for PM2.5/PM10 includes `filtration_pct` when outdoor is above zero |

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

**35** pytest tests; HTTP to InBiot/OpenWeather is mocked. (`tests/test_skills_integration.py` is a manual `python tests/test_skills_integration.py` helper, not part of the pytest suite.)

</details>

---

## Project structure

```
server.py                       # MCP entry point, wires all tools together
src/
  api/
    inbiot.py                   # InBiot HTTP client (cached, connection-pooled)
    openweather.py              # OpenWeather HTTP client (cached, connection-pooled)
  skills/
    monitoring/tools.py         # 4 monitoring tools
    analytics/tools.py          # 3 analytics tools
    compliance/tools.py         # 5 compliance tools
    weather/tools.py            # 2 weather tools
  models/schemas.py             # Pydantic models (DeviceConfig, ParameterData, WELLAssessment...)
  well/
    compliance.py               # WELL compliance engine (scoring, levels, internal recommendations)
    thresholds.py               # WELL/ASHRAE/WHO thresholds
    features.py                 # WELL v2 feature definitions (A01-A08, T01-T07)
  config/
    loader.py                   # YAML/JSON/env config loader
    validator.py                # Config validation
  utils/
    cache.py                    # AsyncTTLCache (in-memory, monotonic clock)
    aggregation.py              # Statistics and time-series aggregation
    exporters.py                # CSV/JSON export formatters
    retry.py                    # Exponential backoff for API calls
    dates.py                    # Date parsing for tool parameters
    validation.py               # Shared validation helpers
    provenance.py               # Data provenance helpers
tests/
  test_cache.py
  test_api_clients.py
  test_compliance.py
  test_tools.py
  test_skills_integration.py    # manual smoke script (not collected by pytest)
```

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
