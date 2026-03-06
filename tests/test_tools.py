"""Tests for MCP tools using FastMCP in-memory client."""

import pytest
from unittest.mock import AsyncMock, patch
from fastmcp import Client

# Import the server
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def mock_inbiot_response():
    """Mock InBiot API response."""
    return [
        {
            "_id": "temp_001",
            "type": "temperature",
            "unit": "°C",
            "measurements": [
                {"_id": "m1", "value": "22.5", "date": 1702000000000}
            ],
        },
        {
            "_id": "hum_001",
            "type": "humidity",
            "unit": "%",
            "measurements": [
                {"_id": "m2", "value": "45", "date": 1702000000000}
            ],
        },
        {
            "_id": "co2_001",
            "type": "co2",
            "unit": "ppm",
            "measurements": [
                {"_id": "m3", "value": "650", "date": 1702000000000}
            ],
        },
    ]


@pytest.mark.asyncio
async def test_list_devices():
    """Test list_devices tool returns available devices header."""
    from server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool("list_devices", {})
        text = result.content[0].text

        # Should always have the header, even with no devices configured
        assert "Available Devices" in text


@pytest.mark.asyncio
async def test_get_latest_measurements_unknown_device():
    """Test get_latest_measurements with unknown device."""
    from server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_latest_measurements",
            {"device": "UNKNOWN_DEVICE"},
        )
        text = result.content[0].text

        assert "Unknown device" in text


@pytest.mark.asyncio
async def test_well_compliance_check_unknown_device():
    """Test well_compliance_check with unknown device."""
    from server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool(
            "well_compliance_check",
            {"device": "UNKNOWN_DEVICE"},
        )
        text = result.content[0].text

        assert "Unknown device" in text


@pytest.mark.asyncio
async def test_list_tools():
    """Test that all expected tools are registered."""
    from server import mcp

    async with Client(mcp) as client:
        tools = await client.list_tools()
        # FastMCP returns a list directly
        tool_names = [tool.name for tool in tools]

        expected_tools = [
            "list_devices",
            "get_latest_measurements",
            "get_historical_data",
            "well_compliance_check",
            "outdoor_snapshot",
            "indoor_vs_outdoor",
            "health_recommendations",
        ]

        for expected in expected_tools:
            assert expected in tool_names, f"Missing tool: {expected}"


@pytest.mark.asyncio
async def test_list_resources():
    """Test that all expected resources are registered."""
    from server import mcp

    async with Client(mcp) as client:
        resources = await client.list_resources()
        # FastMCP returns a list directly
        resource_uris = [str(r.uri) for r in resources]

        expected_resources = [
            "inbiot://docs/parameters",
            "inbiot://docs/well-standards",
            "inbiot://docs/iaq",
            "inbiot://docs/thermal-comfort",
            "inbiot://docs/virus-resistance",
            "inbiot://docs/ventilation",
        ]

        for expected in expected_resources:
            assert expected in resource_uris, f"Missing resource: {expected}"


@pytest.mark.asyncio
async def test_list_prompts():
    """Test that all expected prompts are registered."""
    from server import mcp

    async with Client(mcp) as client:
        prompts = await client.list_prompts()
        # FastMCP returns a list directly
        prompt_names = [p.name for p in prompts]

        expected_prompts = [
            "air_quality_analysis",
            "compare_devices",
            "well_certification_analysis",
            "health_recommendations_prompt",
        ]

        for expected in expected_prompts:
            assert expected in prompt_names, f"Missing prompt: {expected}"
