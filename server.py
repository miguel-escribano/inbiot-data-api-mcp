"""
InBiot Data API - MCP Server

A stateless data API providing InBiot sensor data and outdoor weather context.
No scoring, no compliance logic, no recommendations — raw data only.
Intelligence lives in the plugin layer (Anne or any other consumer).
"""

import sys
from dotenv import load_dotenv
from fastmcp import FastMCP

if sys.platform == 'win32' and "pytest" not in sys.modules:
    import io
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

load_dotenv()

from src.api.inbiot import InBiotClient
from src.api.openweather import OpenWeatherClient, OpenWeatherAPIError
from src.config.loader import ConfigLoader
from src.config.validator import validate_devices, print_validation_warnings
from src.utils.cache import AsyncTTLCache

from src.tools.monitoring import register_monitoring_tools
from src.tools.analytics import register_analytics_tools
from src.tools.weather import register_weather_tools
from src.tools.scoring import register_scoring_tools


def load_devices():
    """Load device configurations from YAML, JSON, or environment variables."""
    try:
        devices = ConfigLoader.load()
        warnings = validate_devices(devices)
        if warnings:
            print_validation_warnings(warnings)
        return devices
    except Exception as e:
        print(f"Error loading device configuration: {e}")
        raise


DEVICES = load_devices()

inbiot_cache = AsyncTTLCache()
weather_cache = AsyncTTLCache()

inbiot_client = InBiotClient(cache=inbiot_cache)

try:
    openweather_client = OpenWeatherClient(cache=weather_cache)
except OpenWeatherAPIError:
    openweather_client = None

mcp = FastMCP(
    "inbiot-data-api-mcp",
    instructions=(
        "Stateless data API for InBiot sensor readings, outdoor weather, "
        "and GO IAQS scoring. Returns raw data and deterministic scores only. "
        "No compliance logic, no recommendations."
    ),
)

register_monitoring_tools(mcp, DEVICES, inbiot_client)
register_analytics_tools(mcp, DEVICES, inbiot_client)
register_weather_tools(mcp, DEVICES, inbiot_client, openweather_client)
register_scoring_tools(mcp, DEVICES, inbiot_client)


def main():
    """Entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
