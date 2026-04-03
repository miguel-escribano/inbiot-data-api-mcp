# inbiot-data-api-mcp

**Repository:** [github.com/miguel-escribano/inbiot-data-api-mcp](https://github.com/miguel-escribano/inbiot-data-api-mcp)

## What is this?

A stateless MCP server that wraps InBiot sensor APIs, OpenWeather, and a Chronos-2 forecasting endpoint into 14 structured tools for air quality monitoring, outdoor weather context, GO IAQS scoring, and CO2 forecasting. Raw data, deterministic scoring, and model predictions — no compliance logic, no recommendations.

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
└─────────────────────────────────┘     └──────────────┬───────────────────┘
                                                       │ HTTP
                                        ┌──────────────▼───────────────────┐
                                        │  HuggingFace Space (model)       │
                                        │  chronos-co2-forecast            │
                                        │                                  │
                                        │  Chronos-2-small (28M params)    │
                                        │  Gradio API on free CPU tier     │
                                        └──────────────────────────────────┘
```

---

## Two ways to use this server

### Option A — Run it yourself (self-hosted)

Clone the repo, configure your own InBiot device credentials, and run it locally or on your own server. The server uses **stdio** transport, which works directly with Cursor, Claude Code, Claude Desktop, and other MCP clients.

**You need:** Python 3.10+, at least one [InBiot MICA](https://www.inbiot.es/) device with API credentials from [My inBiot](https://my.inbiot.es).

[Jump to setup instructions](#self-hosted-setup)

### Option B — Try the demo server (hosted)

We maintain a hosted instance at `mcp.miguel-escribano.com` with pre-configured devices and weather data, so you can explore the tools without owning any hardware.

**What's on the demo server:**
- Several InBiot MICA devices in real office/lab environments (Pamplona, Spain)
- OpenWeather API pre-configured for outdoor air quality context
- All 10 tools available and returning live data

**You need:** [Node.js 18+](https://nodejs.org/) (for `mcp-remote`) and an access token. To request a token, email **mescribano@inbiot.es**.

[Jump to demo server setup](#demo-server-setup)

---

## Tools (14)

| Group | Tool | What it does |
|-------|------|-------------|
| Monitoring | `list_devices` | List configured devices (`id`, `name`, optional `building`) |
| | `get_latest_measurements` | Current sensor values for one device |
| | `get_historical_data` | Historical series with statistics and trend direction |
| | `get_all_devices_summary` | All devices: key metrics (CO2, PM2.5, temperature, humidity, IAQ, thermal) |
| Analytics | `get_data_statistics` | Min/max/mean/median/quartiles/trend for a parameter over a range |
| | `detect_patterns` | Hourly and daily patterns (peak hours, worst/best days) |
| | `export_historical_data` | CSV or JSON export, raw or time-aggregated |
| Scoring | `calculate_go_iaqs_score` | GO IAQS Score (0-10) from live sensor data — per-pollutant sub-scores, tier, grade, dominant pollutant, health advice |
| | `check_go_iaqs_compliance` | 24h rolling compliance check against GO IAQS thresholds |
| Weather | `outdoor_snapshot` | Outdoor weather + air quality for device coordinates (all pollutants: PM2.5, PM10, O3, NO2, NO, SO2, CO, NH3) |
| | `indoor_vs_outdoor` | Side-by-side indoor vs outdoor with filtration effectiveness |
| | `outdoor_forecast` | 4-day hourly air quality forecast — best/worst ventilation windows |
| | `outdoor_history` | Historical outdoor AQ for a time range (up to 7 days) — correlate with indoor events |
| Forecasting | `forecast_co2` | Predict future CO2 levels (10min–4h) via Chronos-2-small. Returns median + 80% confidence interval + threshold crossing alerts |

All tools return JSON-friendly structures. Tool responses avoid Markdown so clients can parse them cheaply.

---

## Key constraints

- **InBiot API: 6 requests per device per hour.** The server uses a TTL cache (10 min for latest data, 60 min for historical, 5 min for weather) so repeated calls for the same device reuse cached responses.
- **OpenWeather API key is optional.** Without it, `outdoor_snapshot` and `indoor_vs_outdoor` return a structured error dict instead of crashing the server.
- **HuggingFace endpoint is optional.** Without it, `forecast_co2` returns a structured error dict. The default endpoint is a free HuggingFace Space running Chronos-2-small — no API key required, but it sleeps after 48h of inactivity (first call after sleep takes ~60s).

---

## Self-hosted setup

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

huggingface_endpoint_url: "https://miguel-escribano-chronos-co2-forecast.hf.space"  # optional, for CO2 forecasting

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

### Point your MCP client at it

Add to your client's MCP config:

```json
{
  "mcpServers": {
    "inbiot-data-api-mcp": {
      "command": "python",
      "args": ["server.py"],
      "cwd": "/path/to/inbiot-data-api-mcp"
    }
  }
}
```

| IDE / App | Config file |
|-----------|-------------|
| **Cursor** | `%USERPROFILE%\.cursor\mcp.json` |
| **Claude Desktop** | `%APPDATA%\Claude\claude_desktop_config.json` |
| **VS Code** | `.vscode/mcp.json` or **MCP: Open User Configuration** |
| **Claude Code** | `.mcp.json` in your project root |

### Tests

```bash
pytest tests/ -v
```

---

## Demo server setup

Point your MCP client at the hosted SSE endpoint. The `mcp-remote` package bridges between the remote SSE server and your local client's stdio.

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

Use the same `command` / `args` block inside your app's MCP config shape:

| IDE / App | Config file |
|-----------|-------------|
| **Cursor** | `%USERPROFILE%\.cursor\mcp.json` |
| **Claude Desktop** | `%APPDATA%\Claude\claude_desktop_config.json` |
| **VS Code** | `.vscode/mcp.json` or **MCP: Open User Configuration** |
| **Claude Code** | `.mcp.json` in your project root |

> **Requirements:** [Node.js 18+](https://nodejs.org/) for `mcp-remote`. To request a token, email **mescribano@inbiot.es**.

---

## Project structure

```
server.py                       # MCP entry point, wires all tools together
src/
  api/
    inbiot.py                   # InBiot HTTP client (cached, connection-pooled)
    openweather.py              # OpenWeather HTTP client (cached, connection-pooled)
    forecasting.py              # HuggingFace endpoint client (Gradio Space or Inference Endpoint)
  tools/
    monitoring/tools.py         # 4 monitoring tools
    analytics/tools.py          # 3 analytics tools
    weather/tools.py            # 4 weather tools (snapshot, comparison, forecast, history)
    scoring/calculator.py       # GO IAQS Score engine (breakpoints, interpolation, synergy)
    scoring/tools.py            # 2 scoring tools
    forecasting/tools.py        # 1 forecasting tool (CO2 prediction via Chronos-2)
  models/schemas.py             # Pydantic models (DeviceConfig, ParameterData, CO2Forecast...)
  config/
    loader.py                   # YAML/JSON/env config loader (InBiot + OpenWeather + HF)
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
  test_go_iaqs.py               # 38 tests: white paper parity, synergy, boundaries, CH2O conversion
  test_skills_integration.py    # manual smoke script (not collected by pytest)
```

---

## Architecture note

This server is intentionally a **thin data pipe**. WELL compliance scoring, threshold interpretation, and health recommendations live in the plugin layer — not here.

There are two exceptions:

1. **GO IAQS Score** (`calculate_go_iaqs_score`). Deterministic scoring — the GO AQS methodology (piecewise linear interpolation, worst-pollutant-wins, synergistic reduction) is fully specified in the [GO AQS White Paper v1.0](https://goaqs.org/) and benefits from consistent, reproducible calculation. The scoring engine covers all 7 GO IAQS pollutants (PM2.5, CO2, CO, CH2O, O3, NO2, Radon) with 38 unit tests validated against the white paper's worked examples.

2. **CO2 Forecasting** (`forecast_co2`). Calls a remote [Chronos-2-small](https://huggingface.co/autogluon/chronos-2-small) model hosted on a HuggingFace Space. The server sends 24h of CO2 history and receives quantile predictions — no ML dependencies in the MCP server itself. The approach is validated by [Garcia-Pinilla et al. (2026)](https://doi.org/10.3390/forecasting8010026) who benchmarked Chronos models for indoor CO2 forecasting using InBiot MICA data.

WELL, EPBD, and other framework-specific interpretation remains in the plugin's `knowledge/` files, where domain experts can review and tweak thresholds directly.

---

## Links

- [This repo](https://github.com/miguel-escribano/inbiot-data-api-mcp) — MCP data server
- [Anne plugin](https://github.com/miguel-escribano/inbiot-Anne-IAQ-consultant-as-a-plugin) — persona, skills, marketplace metadata
- [Chronos-2 CO2 Forecast Space](https://huggingface.co/spaces/miguel-escribano/chronos-co2-forecast) — HuggingFace Space serving the forecasting model
- [InBiot](https://www.inbiot.es/) — Air quality monitoring devices
- [My inBiot Platform](https://my.inbiot.es) — Device management and API credentials
- [WELL Building Standard](https://www.wellcertified.com/) — Certification program
- [Model Context Protocol](https://modelcontextprotocol.io/) — MCP specification

## License
MIT
