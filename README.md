# inbiot-data-api

Stateless MCP server providing InBiot sensor data and WELL compliance tools. Designed as a pure data API for the [Anne IAQ plugin](https://github.com/miguel-escribano/inbiot-Anne-IAQ-consultant-as-a-plugin) — no persona, no prompts, no resources.

> **Architecture note:** This is the "split" approach — data API here, intelligence in the plugin. For a standalone MCP that bundles both data and Anne's persona/prompts, see [inBiot_MCP_with_WeatherAPI_and_WELL_standard](https://github.com/miguel-escribano/inBiot_MCP_with_WeatherAPI_and_WELL_standard).

## Remote access

The server is deployed at:

```
https://mcp.miguel-escribano.com/inbiot-mcp-for-Anne-IAQ-consultant-as-a-plugin/sse
```

Auth header: `X-MCP-Token: <your-token>`

To request a token, email **mescribano@inbiot.es**.

## Tools (14)

**Monitoring (4):** `list_devices`, `get_latest_measurements`, `get_historical_data`, `get_all_devices_summary`

**Analytics (3):** `get_data_statistics`, `detect_patterns`, `export_historical_data`

**Compliance (4):** `well_compliance_check`, `well_feature_compliance`, `health_recommendations`, `well_certification_roadmap`

**Weather (2):** `outdoor_snapshot`, `indoor_vs_outdoor`

## Setup (local)

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
pip install -e .
```

## Configuration

1. Copy `inbiot-config.example.yaml` to `inbiot-config.yaml` and fill in device API keys
2. Create `.env` with `OPENWEATHER_API_KEY=<your-key>`

## Running

```bash
python server.py
```

Default transport: stdio. For SSE deployment, run behind a reverse proxy on a dedicated port.

## License

MIT
