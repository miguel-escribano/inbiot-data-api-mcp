# inbiot-data-api (MCP Server)

## What is this?

The data layer behind Anne, the IAQ consultant plugin. A stateless MCP server that wraps InBiot sensor APIs and OpenWeather into 14 structured tools for air quality monitoring and WELL Building Standard compliance.

**No persona. No prompts. No resources.** Just clean JSON tools.

The intelligence (Anne's persona, WELL knowledge, skill workflows) lives in the plugin at `../inbiot-Anne-IAQ-consultant-as-a-plugin/`. This server is what gives Anne real data to work with.

```
┌─────────────────────────────────┐     ┌──────────────────────────────────┐
│  Plugin (intelligence)          │     │  This server (data)              │
│  inbiot-Anne-IAQ-consultant-... │     │  inbiot-mcp-for-Anne-IAQ-...     │
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

The easiest way -- no installation. Just point your MCP client at the hosted server.

Add this to your MCP configuration:

```json
"inbiot-data-api": {
  "command": "npx",
  "args": [
    "-y",
    "mcp-remote",
    "https://mcp.miguel-escribano.com/inbiot-mcp-for-Anne-IAQ-consultant-as-a-plugin/sse",
    "--header",
    "X-MCP-Token: <YOUR_TOKEN>"
  ]
}
```

| IDE / App | Config file |
|-----------|-------------|
| **Cursor** | `%USERPROFILE%\.cursor\mcp.json` |
| **Claude Desktop** | `%APPDATA%\Claude\claude_desktop_config.json` |
| **VS Code** | `.vscode/mcp.json` in your project, or `Ctrl+Shift+P` -> MCP: Open User Configuration |

> **Requirements:** [Node.js 18+](https://nodejs.org/). To request a token, email **mescribano@inbiot.es**.

---

## Tools (14)

| Group | Tool | What it does |
|-------|------|-------------|
| Monitoring | `list_devices` | List all configured devices (filterable by `building`) |
| | `get_latest_measurements` | Current sensor values for one device |
| | `get_historical_data` | Historical data with statistics and trend direction |
| | `get_all_devices_summary` | All devices at a glance with status flags |
| Analytics | `get_data_statistics` | Min/max/mean/median/quartiles/trend for any parameter |
| | `detect_patterns` | Hourly and daily patterns (peak hours, worst days) |
| | `export_historical_data` | CSV or JSON export, raw or time-aggregated |
| Compliance | `well_compliance_check` | WELL assessment snapshot |
| | `well_feature_compliance` | Per-feature breakdown (A01-A08, T01-T07) |
| | `health_recommendations` | Actionable advice based on current readings |
| | `well_certification_roadmap` | Prioritized path to next WELL certification level |
| | `compliance_over_time` | Sustained compliance % over a date range |
| Weather | `outdoor_snapshot` | Outdoor weather + air quality from OpenWeather |
| | `indoor_vs_outdoor` | Indoor vs outdoor comparison with filtration effectiveness % |

All tools return JSON dicts. No Markdown in responses -- saves context tokens and keeps output machine-parseable.

---

## Key constraints

- **InBiot API: 6 requests per device per hour.** The server uses a TTL cache (10 min for latest data, 60 min for historical, 5 min for weather) so consecutive tool calls for the same device reuse cached responses.
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
git clone <repo-url>
cd inbiot-mcp-for-Anne-IAQ-consultant-as-a-plugin

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
python server.py    # stdio transport (default for Claude Code / local MCP clients)
```

### Tests

```bash
pytest tests/ -v    # 35 tests, no external API calls needed (all HTTP mocked)
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
  skills/
    monitoring/tools.py         # 4 monitoring tools
    analytics/tools.py          # 3 analytics tools
    compliance/tools.py         # 5 compliance tools
    weather/tools.py            # 2 weather tools
  models/schemas.py             # Pydantic models (DeviceConfig, ParameterData, WELLAssessment...)
  well/
    compliance.py               # WELL compliance engine (scoring, levels, recommendations)
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
tests/
  test_cache.py
  test_api_clients.py
  test_compliance.py
  test_tools.py
```

---

## Links

- [InBiot](https://www.inbiot.es/) -- Air quality monitoring devices
- [My inBiot Platform](https://my.inbiot.es) -- Device management and API credentials
- [WELL Building Standard](https://www.wellcertified.com/) -- Certification program
- [Model Context Protocol](https://modelcontextprotocol.io/) -- MCP specification
- [Plugin repo](../inbiot-Anne-IAQ-consultant-as-a-plugin/) -- Anne's persona and skills
- [Previous monolithic version](../inBiot_MCP_with_WeatherAPI_and_WELL_standard/) -- Original combined repo

## License
MIT
