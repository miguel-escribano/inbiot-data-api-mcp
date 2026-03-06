"""
InBiot Data API - MCP Server

A stateless data API providing InBiot sensor data and WELL compliance tools.
No persona, no prompts, no resources -- the plugin layer handles intelligence.
"""

import sys
from dotenv import load_dotenv
from fastmcp import FastMCP

# Fix encoding for Windows console
if sys.platform == 'win32':
    import io
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Load environment variables from .env file
load_dotenv()

from src.api.inbiot import InBiotClient
from src.well.compliance import WELLComplianceEngine
from src.config.loader import ConfigLoader
from src.config.validator import validate_devices, print_validation_warnings

# Import skills
from src.skills.monitoring import register_monitoring_tools
from src.skills.analytics import register_analytics_tools
from src.skills.compliance import register_compliance_tools
from src.skills.weather import register_weather_tools


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


# Initialize
DEVICES = load_devices()
inbiot_client = InBiotClient()
well_engine = WELLComplianceEngine()

mcp = FastMCP(
    "inbiot-data-api",
    instructions=(
        "Stateless data API for InBiot sensor readings and WELL compliance checks. "
        "Returns raw data only. No persona, no analysis, no recommendations."
    ),
)

# Register tools
register_monitoring_tools(mcp, DEVICES, inbiot_client)
register_analytics_tools(mcp, DEVICES, inbiot_client)
register_compliance_tools(mcp, DEVICES, inbiot_client, well_engine)
register_weather_tools(mcp, DEVICES, inbiot_client)


def main():
    """Entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
