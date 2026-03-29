"""Tests for MCP tools using FastMCP in-memory client."""

import json
import pytest
from unittest.mock import AsyncMock, patch
from fastmcp import Client

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
            "unit": "C",
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
    """Test list_devices tool returns JSON with devices array."""
    from server import mcp

    async with Client(mcp) as client:
        result = await client.call_tool("list_devices", {})
        text = result.content[0].text

        data = json.loads(text)
        assert "devices" in data


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

        data = json.loads(text)
        assert "error" in data
        assert "Unknown device" in data["error"]


@pytest.mark.asyncio
async def test_list_tools():
    """Test that all 9 expected tools are registered."""
    from server import mcp

    async with Client(mcp) as client:
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]

        expected_tools = [
            "list_devices",
            "get_latest_measurements",
            "get_historical_data",
            "get_all_devices_summary",
            "get_data_statistics",
            "export_historical_data",
            "detect_patterns",
            "outdoor_snapshot",
            "indoor_vs_outdoor",
        ]

        for expected in expected_tools:
            assert expected in tool_names, f"Missing tool: {expected}"

        assert len(tool_names) == len(expected_tools), (
            f"Expected {len(expected_tools)} tools, got {len(tool_names)}: {sorted(tool_names)}"
        )


@pytest.mark.asyncio
async def test_list_resources():
    """Test that no resources are registered (stateless data API)."""
    from server import mcp

    async with Client(mcp) as client:
        resources = await client.list_resources()
        assert len(resources) == 0


@pytest.mark.asyncio
async def test_list_prompts():
    """Test that no prompts are registered (stateless data API)."""
    from server import mcp

    async with Client(mcp) as client:
        prompts = await client.list_prompts()
        assert len(prompts) == 0
