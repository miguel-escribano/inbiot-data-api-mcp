# inbiot-data-api

Stateless MCP server providing InBiot sensor data and WELL compliance tools. Designed as a pure data API for the Anne IAQ plugin -- no persona, no prompts, no resources.

## Tools (14)

**Monitoring (4):** `list_devices`, `get_latest_measurements`, `get_historical_data`, `get_all_devices_summary`

**Analytics (3):** `get_data_statistics`, `detect_patterns`, `export_historical_data`

**Compliance (4):** `well_compliance_check`, `well_feature_compliance`, `health_recommendations`, `well_certification_roadmap`

**Weather (2):** `outdoor_snapshot`, `indoor_vs_outdoor`

## Setup

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

Default transport: stdio. For SSE deployment, run behind a reverse proxy (e.g., Caddy) on a dedicated port.

## Deployment (Linux)

```bash
# Install
cd /opt/anne-mcp-server
python3 -m venv .venv
.venv/bin/pip install -e .

# systemd service (port 8001)
sudo systemctl enable --now anne-mcp-server

# Caddy route
# handle_path /anne/* { reverse_proxy localhost:8001 }
```
