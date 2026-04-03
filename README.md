# inbiot-data-api-mcp

**Repository:** [github.com/miguel-escribano/inbiot-data-api-mcp](https://github.com/miguel-escribano/inbiot-data-api-mcp)

## What is this?

A stateless MCP server that wraps InBiot sensor APIs, OpenWeather, and a Chronos-2 forecasting endpoint into 14 structured tools for air quality monitoring, outdoor weather context, GO IAQS scoring, and CO2 forecasting. It returns raw data, deterministic scoring, and model predictions — no compliance logic, no recommendations, no persona.

Every tool is registered with read-only / non-destructive hints so MCP clients know nothing here mutates state. All responses are JSON-friendly structures (no Markdown), which keeps them cheap to parse and easy to compose in downstream workflows.

All intelligence — persona, WELL knowledge, compliance assessment, skill workflows — lives in the consumer layer. The primary consumer today is the Anne plugin: [inbiot-Anne-IAQ-consultant-as-a-plugin](https://github.com/miguel-escribano/inbiot-Anne-IAQ-consultant-as-a-plugin). But this server is designed to be consumed by anyone: a different agent, a dashboard, a notebook.

```
┌─────────────────────────────────┐     ┌──────────────────────────────────┐
│  Plugin (intelligence)          │     │  This server (data)              │
│  inbiot-Anne-IAQ-consultant-... │     │  inbiot-data-api-mcp             │
│                                 │     │                                  │
│  agents/    = Anne's persona    │────>│  server.py  = MCP entry point    │
│  skills/    = workflows         │ MCP │  src/api/   = HTTP clients       │
│  knowledge/ = WELL thresholds   │     │  src/tools/ = tool definitions   │
│  commands/  = slash commands    │     │  src/utils/ = cache, dates, etc  │
│  .mcp.json  = server connection │     │                                  │
└─────────────────────────────────┘     └──┬──────────┬──────────┬─────────┘
                                           │          │          │
                                         HTTP       HTTP       HTTP
                                           │          │          │
                              ┌────────────▼──┐ ┌────▼────────┐ ┌▼─────────────────┐
                              │  InBiot API    │ │ OpenWeather │ │ HuggingFace Space │
                              │  my.inbiot.es  │ │ API         │ │ chronos-co2-      │
                              │                │ │             │ │ forecast          │
                              │  Sensor data   │ │ Outdoor AQ  │ │ Chronos-2-small   │
                              │  6 req/dev/h   │ │ + weather   │ │ CO2 predictions   │
                              └────────────────┘ └─────────────┘ └───────────────────┘
```

---

## Two ways to use this server

### Option A — Run it yourself (self-hosted)

Clone the repo, configure your own InBiot device credentials, and run it locally or on your own server. The server uses **stdio** transport, which works directly with Cursor, Claude Code, Claude Desktop, and other MCP clients.

**You need:** Python 3.10+, at least one [InBiot MICA](https://www.inbiot.es/) device with API credentials from [My inBiot](https://my.inbiot.es).

[Jump to setup instructions](#self-hosted-setup)

### Option B — Try the demo server (hosted)

We maintain a hosted instance at `mcp.miguel-escribano.com` with pre-configured devices and weather data, so you can explore the tools without owning any hardware. The hosted server uses SSE transport behind a reverse proxy, with token-based authentication.

**What's on the demo server:**
- Several InBiot MICA devices in real office/lab environments (Pamplona, Spain)
- OpenWeather API pre-configured for outdoor air quality context
- Chronos-2 CO2 forecasting via the HuggingFace Space
- All 14 tools available and returning live data

**You need:** [Node.js 18+](https://nodejs.org/) (for `mcp-remote`, which bridges SSE→stdio for local MCP clients) and an access token. To request a token, email **mescribano@inbiot.es**.

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

The tool groupings reflect how the Anne plugin thinks about data: monitoring tools give you the current state, analytics tools give you patterns over time, weather tools provide outdoor context for ventilation decisions, scoring tools give you a standardized numeric benchmark, and forecasting lets Anne anticipate problems before they happen.

---

## Constraints and caching strategy

### InBiot API: 6 requests per device per hour

This is the hard constraint that shapes everything. The InBiot platform rate-limits API calls to 6 per device per hour, and there's no way to increase it. The server uses an in-memory TTL cache to make this workable:

| Data type | TTL | Rationale |
|-----------|-----|-----------|
| Latest measurements | 10 min | MICA sensors sample every 10 minutes, so more frequent requests would just return the same data anyway |
| Historical data | 60 min | Historical data doesn't change — once a reading is recorded, it's final |
| Weather data | 5 min | OpenWeather updates roughly every 10 min; 5 min gives a good freshness/load balance |
| CO2 forecasts | 10 min | Aligned with MICA sampling — new predictions only make sense when new data is available |

The cache is in-memory (`AsyncTTLCache` with a monotonic clock), not persistent. If the server restarts, the cache is cold, but that's fine — the rate limit resets hourly on InBiot's side anyway. The cache key design hashes the request parameters, so the same device + time range reuses a cached response, but a different time range triggers a fresh API call.

In practice, a typical Anne assessment of one device uses 2–3 InBiot API calls (latest + historical + maybe a second historical for a different time range), well within the 6/hour budget. The `assess all` workflow across multiple devices is where the limit matters — Anne's skill files are designed to batch efficiently.

### Optional dependencies

The server is designed so that missing API keys degrade gracefully instead of crashing:

- **Without OpenWeather API key:** The weather tools (`outdoor_snapshot`, `indoor_vs_outdoor`, `outdoor_forecast`, `outdoor_history`) return a structured error dict with a clear message. The monitoring, analytics, scoring, and forecasting tools work normally. Anne's ventilation skill detects this and falls back to indoor-only analysis.
- **Without HuggingFace endpoint:** `forecast_co2` returns a structured error dict. Everything else works. The HuggingFace Space is free and requires no API key, but it sleeps after 48h of inactivity — the first call after sleep takes ~60s for a cold start.

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
openweather_api_key: "your-key"    # optional — without it, weather tools return errors

huggingface_endpoint_url: "https://miguel-escribano-chronos-co2-forecast.hf.space"  # optional — for CO2 forecasting

devices:
  office:
    name: "Main Office"
    api_key: "from-my.inbiot.es"
    system_id: "from-my.inbiot.es"
    latitude: 40.416775
    longitude: -3.703790
    building: "HQ Madrid"          # optional, for grouping
```

See `inbiot-config.example.yaml` for the full template. Credentials come from [My inBiot Platform](https://my.inbiot.es) → Device Settings.

The config loader (`src/config/loader.py`) supports three sources, checked in order: YAML file, JSON file, environment variables. You only need one. YAML is recommended for multi-device setups; environment variables work for single-device deployments or CI.

### Run

```bash
python server.py
# or, after editable install:
inbiot-data-api-mcp
```

Both use **stdio** transport, which is what Cursor, Claude Code, and most local MCP clients expect. The server starts, loads device configs, validates them (printing warnings for missing optional fields like coordinates), and begins listening for MCP requests.

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

The test suite covers: cache TTL behavior and expiration (`test_cache.py`), InBiot and OpenWeather API client mocking (`test_api_clients.py`), tool registration and response shapes (`test_tools.py`), and GO IAQS scoring with 38 tests validated against the white paper's worked examples (`test_go_iaqs.py`). There's also a manual smoke script (`test_skills_integration.py`) that exercises the full tool chain against real APIs — not collected by pytest, run it manually when testing end-to-end.

---

## Demo server setup

Point your MCP client at the hosted SSE endpoint. The `mcp-remote` package bridges between the remote SSE server and your local client's stdio transport.

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

Use the same `command` / `args` block inside your app's MCP config:

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
server.py                       # MCP entry point — loads config, creates clients, registers all tools
src/
  api/
    inbiot.py                   # InBiot HTTP client (cached, connection-pooled, retry with backoff)
    openweather.py              # OpenWeather HTTP client (cached, connection-pooled)
    forecasting.py              # HuggingFace endpoint client (handles both Gradio Space and Inference Endpoint protocols)
  tools/
    monitoring/tools.py         # 4 monitoring tools (list, latest, historical, summary)
    analytics/tools.py          # 3 analytics tools (statistics, patterns, export)
    weather/tools.py            # 4 weather tools (snapshot, comparison, forecast, history)
    scoring/calculator.py       # GO IAQS Score engine (breakpoints, interpolation, synergy penalties)
    scoring/compliance.py       # GO IAQS compliance checker (24h rolling window)
    scoring/tools.py            # 2 scoring tools wrapping the engine
    forecasting/tools.py        # 1 forecasting tool (CO2 prediction via Chronos-2)
  models/schemas.py             # Pydantic models (DeviceConfig, ParameterData, CO2Forecast...)
  config/
    loader.py                   # YAML/JSON/env config loader with fallback chain
    validator.py                # Config validation — warns on missing optional fields
  utils/
    cache.py                    # AsyncTTLCache — in-memory, monotonic clock, async-safe
    aggregation.py              # Statistics and time-series aggregation (mean, median, quartiles, trend)
    normalization.py            # Parameter name aliases (pm2.5→pm25, tvoc→vocs, etc.)
    exporters.py                # CSV/JSON export formatters with time aggregation
    retry.py                    # Exponential backoff with configurable attempts and delays
    dates.py                    # Date parsing for tool parameters (natural language → datetime)
    validation.py               # Shared validation helpers (device ID checks, parameter validation)
tests/
  test_cache.py                 # TTL expiration, concurrent access, monotonic clock behavior
  test_api_clients.py           # Mocked HTTP responses for InBiot and OpenWeather
  test_tools.py                 # Tool registration, parameter validation, response shape
  test_go_iaqs.py               # 38 tests: white paper parity, synergy, boundaries, CH2O conversion
  test_skills_integration.py    # Manual smoke script against real APIs (not collected by pytest)
```

---

## Architecture decisions

### Why a thin data pipe

This server is intentionally a **data pipe with minimal logic**. WELL compliance scoring, threshold interpretation, health recommendations, and framework-specific assessments live in the plugin layer, not here.

The separation exists because compliance knowledge changes frequently — WELL v2 addenda, EPBD phasing timelines, ASHRAE updates — and the people who maintain that knowledge (IAQ consultants, sustainability managers) should be able to edit it in plain Markdown without touching Python. Keeping the standards in the plugin's `knowledge/` files makes that possible. The server just returns numbers; the plugin decides what those numbers mean.

### Two exceptions

1. **GO IAQS Scoring** (`calculate_go_iaqs_score`, `check_go_iaqs_compliance`). The GO IAQS methodology — piecewise linear interpolation, worst-pollutant-wins, synergistic reduction for multi-pollutant exposure — is fully specified in the [GO AQS White Paper v1.0](https://goaqs.org/) and is deterministic. Unlike WELL or EPBD, there's no interpretation involved: you put in concentrations, you get a score. Putting this in the server means every consumer gets identical, reproducible results, and the 38-test suite validates against the white paper's worked examples. The engine covers all 7 GO IAQS pollutants (PM2.5, CO2, CO, CH2O, O3, NO2, Radon) including the CH2O unit conversion (mg/m³ → µg/m³) that the white paper specifies.

2. **CO2 Forecasting** (`forecast_co2`). This calls a remote Chronos-2-small model hosted on a [HuggingFace Space](https://huggingface.co/spaces/miguel-escribano/chronos-co2-forecast). The server sends 24h of CO2 history (144 values at 10-min intervals) and receives quantile predictions. There are no ML dependencies in the MCP server itself — the forecasting client just makes HTTP requests and parses JSON. The approach is validated by [Garcia-Pinilla et al. (2026)](https://doi.org/10.3390/forecasting8010026) who benchmarked Chronos models for indoor CO2 forecasting using InBiot MICA data.

### Why responses avoid Markdown

All tool responses return plain JSON dicts and lists. No Markdown formatting, no tables, no headers. This is deliberate: MCP tool responses are consumed by the LLM, not rendered to the user. If the tool returns Markdown, the LLM tends to parrot it verbatim rather than interpreting the data. Clean JSON lets the LLM (or in our case, Anne's skill workflows) decide how to present findings to the user in context.

---

## Links

- [This repo](https://github.com/miguel-escribano/inbiot-data-api-mcp) — MCP data server
- [Anne plugin](https://github.com/miguel-escribano/inbiot-Anne-IAQ-consultant-as-a-plugin) — persona, skills, marketplace metadata
- [Chronos-2 CO2 Forecast Space](https://huggingface.co/spaces/miguel-escribano/chronos-co2-forecast) — HuggingFace Space serving the forecasting model
- [InBiot](https://www.inbiot.es/) — Air quality monitoring devices
- [My inBiot Platform](https://my.inbiot.es) — Device management and API credentials
- [WELL Building Standard](https://www.wellcertified.com/) — Certification program
- [GO AQS White Paper](https://goaqs.org/) — Scoring methodology reference
- [Model Context Protocol](https://modelcontextprotocol.io/) — MCP specification

## License

MIT
