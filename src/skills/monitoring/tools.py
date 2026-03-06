"""Monitoring tools for real-time and historical air quality data."""

import asyncio
from datetime import datetime
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from src.api.inbiot import InBiotClient, InBiotAPIError
from src.models.schemas import DeviceConfig
from src.utils.provenance import (
    generate_provenance,
    create_data_unavailable_error,
)
from src.utils.aggregation import DataAggregator
from src.well.thresholds import get_threshold_for_parameter, normalize_parameter_name


def register_monitoring_tools(
    mcp: FastMCP,
    devices: dict[str, DeviceConfig],
    inbiot_client: InBiotClient,
):
    """Register monitoring tools with the MCP server."""

    @mcp.tool()
    def list_devices() -> str:
        """
        List all available InBiot air quality monitoring devices.

        Returns a list of device IDs and their human-readable names.
        """
        device_list = []
        for device_id, config in devices.items():
            device_list.append(f"- **{device_id}**: {config.name}")

        return "## Available Devices\n\n" + "\n".join(device_list)

    @mcp.tool()
    async def get_latest_measurements(
        device: Annotated[str, Field(description="Device ID (use list_devices to see options)")]
    ) -> str:
        """
        Get the latest air quality measurements from an InBiot device.

        Returns current values for all monitored parameters including temperature,
        humidity, CO2, particulate matter, VOCs, and composite indicators.
        """
        if device not in devices:
            return f"Unknown device: {device}. Use list_devices to see available options."

        device_config = devices[device]
        endpoint = f"/last-measurements/{device_config.api_key}/{device_config.system_id}"

        try:
            data = await inbiot_client.get_latest_measurements(device_config)

            # Format results
            result = f"## Latest Measurements: {device_config.name}\n\n"
            result += "| Parameter | Value | Unit |\n|-----------|-------|------|\n"

            for param in data:
                if param.latest_value is not None:
                    result += f"| {param.type} | {param.latest_value} | {param.unit} |\n"

            # Add provenance
            result += generate_provenance(
                device_name=device_config.name,
                device_api_key=device_config.api_key,
                endpoint=endpoint,
                data=data,
                analysis_type="Latest Measurements",
            )

            return result

        except InBiotAPIError as e:
            return create_data_unavailable_error(
                device_name=device_config.name,
                error_message=e.message,
                endpoint=endpoint,
            )

    @mcp.tool()
    async def get_historical_data(
        device: Annotated[str, Field(description="Device ID")],
        start_date: Annotated[str, Field(description="Start date (YYYY-MM-DD or ISO-8601)")],
        end_date: Annotated[str, Field(description="End date (YYYY-MM-DD or ISO-8601)")],
    ) -> str:
        """
        Get historical air quality measurements from an InBiot device.

        Retrieves measurements between the specified dates.
        Note: InBiot API is rate-limited to 6 requests per device per hour.
        """
        if device not in devices:
            return f"Unknown device: {device}. Use list_devices to see available options."

        device_config = devices[device]

        # Parse dates
        try:
            if "T" in start_date:
                start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            else:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")

            if "T" in end_date:
                end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            else:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59
                )
        except ValueError as e:
            return f"Invalid date format: {e}. Use YYYY-MM-DD or ISO-8601 format."

        endpoint = f"/measurements-by-time/{device_config.api_key}/{device_config.system_id}/..."

        try:
            data = await inbiot_client.get_historical_data(device_config, start_dt, end_dt)

            # Format results
            result = f"## Historical Data: {device_config.name}\n\n"
            result += f"**Period**: {start_date} to {end_date}\n\n"

            # Statistics summary
            aggregator = DataAggregator()
            result += "### Quick Statistics\n\n"
            result += "| Parameter | Count | Min | Max | Mean |\n"
            result += "|-----------|-------|-----|-----|------|\n"

            for param in data:
                if param.measurements:
                    stats = aggregator.calculate_statistics(param.measurements)
                    result += f"| {param.type} ({param.unit}) | {stats['count']} | {stats['min']:.1f} | {stats['max']:.1f} | {stats['mean']:.1f} |\n"

            result += "\n### Detailed Breakdown\n\n"

            for param in data:
                if param.measurements:
                    stats = aggregator.calculate_statistics(param.measurements)
                    trends = aggregator.detect_trends(param.measurements)

                    result += f"#### {param.type} ({param.unit})\n"
                    result += f"- **Measurements**: {len(param.measurements)}\n"
                    result += f"- **Latest value**: {param.latest_value}\n"
                    result += f"- **Range**: {stats['min']:.1f} - {stats['max']:.1f}\n"
                    result += f"- **Average**: {stats['mean']:.1f}\n"
                    result += f"- **Trend**: {trends['trend']} ({trends['change_percentage']:+.1f}%)\n"
                    result += "\n"

            # Add provenance
            result += generate_provenance(
                device_name=device_config.name,
                device_api_key=device_config.api_key,
                endpoint=endpoint,
                data=data,
                analysis_type="Historical Data",
            )

            return result

        except InBiotAPIError as e:
            return create_data_unavailable_error(
                device_name=device_config.name,
                error_message=e.message,
                endpoint=endpoint,
            )

    @mcp.tool()
    async def get_all_devices_summary() -> str:
        """
        Get a summary of all devices with status indicators.

        Shows key parameters (CO2, PM2.5, temperature, IAQ) for all devices
        in a single view, with status indicators highlighting devices that
        need attention. Useful for quick facility-wide assessment.
        """
        key_params = ["co2", "pm25", "temperature", "iaq", "thermalindicator"]

        async def fetch_device_data(device_id: str, config: DeviceConfig):
            """Fetch data for a single device, handling errors gracefully."""
            try:
                data = await inbiot_client.get_latest_measurements(config)
                values = {}
                for param in data:
                    normalized = normalize_parameter_name(param.type)
                    if normalized in key_params and param.latest_value is not None:
                        values[normalized] = (param.latest_value, param.unit)
                return device_id, config.name, values, None
            except InBiotAPIError as e:
                return device_id, config.name, {}, e.message

        # Fetch all devices in parallel
        tasks = [fetch_device_data(did, cfg) for did, cfg in devices.items()]
        results = await asyncio.gather(*tasks)

        # Build summary table
        result = "## All Devices Summary\n\n"
        result += "| Device | Status | CO2 (ppm) | PM2.5 (µg/m³) | Temp (°C) | IAQ | Thermal |\n"
        result += "|--------|--------|-----------|---------------|-----------|-----|----------|\n"

        for device_id, name, values, error in results:
            if error:
                result += f"| {name} | ⚫ Offline | - | - | - | - | - |\n"
                continue

            status = "🟢 Good"

            # Check CO2
            co2_val = values.get("co2", (None, None))[0]
            if co2_val is not None:
                threshold = get_threshold_for_parameter("co2")
                if threshold and co2_val > threshold["acceptable"]:
                    status = "🔴 Alert"
                elif threshold and co2_val > threshold["good"]:
                    if status != "🔴 Alert":
                        status = "🟡 Warning"

            # Check PM2.5
            pm25_val = values.get("pm25", (None, None))[0]
            if pm25_val is not None:
                threshold = get_threshold_for_parameter("pm25")
                if threshold and pm25_val > threshold["acceptable"]:
                    status = "🔴 Alert"
                elif threshold and pm25_val > threshold["good"]:
                    if status != "🔴 Alert":
                        status = "🟡 Warning"

            # Check temperature (range-based)
            temp_val = values.get("temperature", (None, None))[0]
            if temp_val is not None:
                threshold = get_threshold_for_parameter("temperature")
                if threshold:
                    if temp_val < threshold["acceptable_min"] or temp_val > threshold["acceptable_max"]:
                        status = "🔴 Alert"
                    elif temp_val < threshold["optimal_min"] or temp_val > threshold["optimal_max"]:
                        if status != "🔴 Alert":
                            status = "🟡 Warning"

            # Check IAQ indicator (higher is better)
            iaq_val = values.get("iaq", (None, None))[0]
            if iaq_val is not None:
                if iaq_val < 40:
                    status = "🔴 Alert"
                elif iaq_val < 60 and status != "🔴 Alert":
                    status = "🟡 Warning"

            # Format row values
            co2_str = f"{co2_val:.0f}" if co2_val is not None else "-"
            pm25_str = f"{pm25_val:.1f}" if pm25_val is not None else "-"
            temp_str = f"{temp_val:.1f}" if temp_val is not None else "-"
            iaq_str = f"{iaq_val:.0f}" if iaq_val is not None else "-"
            thermal_val = values.get("thermalindicator", (None, None))[0]
            thermal_str = f"{thermal_val:.0f}" if thermal_val is not None else "-"

            result += f"| {name} | {status} | {co2_str} | {pm25_str} | {temp_str} | {iaq_str} | {thermal_str} |\n"

        result += "\n**Legend**: 🟢 Good | 🟡 Warning | 🔴 Alert | ⚫ Offline\n"

        return result
