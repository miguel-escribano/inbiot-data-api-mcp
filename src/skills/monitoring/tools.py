"""Monitoring tools for real-time and historical air quality data."""

import asyncio
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from src.api.inbiot import InBiotClient, InBiotAPIError
from src.models.schemas import DeviceConfig
from src.utils.aggregation import DataAggregator
from src.utils.dates import parse_date_param
from src.utils.validation import validate_device
from src.well.thresholds import get_threshold_for_parameter, normalize_parameter_name


def register_monitoring_tools(
    mcp: FastMCP,
    devices: dict[str, DeviceConfig],
    inbiot_client: InBiotClient,
):
    """Register monitoring tools with the MCP server."""

    @mcp.tool()
    def list_devices() -> dict:
        """
        List all available InBiot air quality monitoring devices.

        Returns a list of device IDs and their human-readable names.
        """
        device_list = []
        for device_id, config in devices.items():
            entry = {"id": device_id, "name": config.name}
            if config.building:
                entry["building"] = config.building
            device_list.append(entry)
        return {"devices": device_list}

    @mcp.tool()
    async def get_latest_measurements(
        device: Annotated[str, Field(description="Device ID (use list_devices to see options)")]
    ) -> dict:
        """
        Get the latest air quality measurements from an InBiot device.

        Returns current values for all monitored parameters including temperature,
        humidity, CO2, particulate matter, VOCs, and composite indicators.
        """
        try:
            device_config = validate_device(devices, device)
        except ValueError as e:
            return {"error": str(e)}

        try:
            data = await inbiot_client.get_latest_measurements(device_config)

            measurements = []
            for param in data:
                if param.latest_value is not None:
                    measurements.append({
                        "parameter": param.type,
                        "value": param.latest_value,
                        "unit": param.unit,
                    })

            return {
                "device": device_config.name,
                "measurements": measurements,
            }

        except InBiotAPIError as e:
            return {"error": e.message, "device": device_config.name}

    @mcp.tool()
    async def get_historical_data(
        device: Annotated[str, Field(description="Device ID")],
        start_date: Annotated[str, Field(description="Start date (YYYY-MM-DD or ISO-8601)")],
        end_date: Annotated[str, Field(description="End date (YYYY-MM-DD or ISO-8601)")],
    ) -> dict:
        """
        Get historical air quality measurements from an InBiot device.

        Retrieves measurements between the specified dates.
        Note: InBiot API is rate-limited to 6 requests per device per hour.
        """
        try:
            device_config = validate_device(devices, device)
        except ValueError as e:
            return {"error": str(e)}

        try:
            start_dt = parse_date_param(start_date)
            end_dt = parse_date_param(end_date, end_of_day=True)
        except ValueError as e:
            return {"error": f"Invalid date format: {e}. Use YYYY-MM-DD or ISO-8601 format."}

        try:
            data = await inbiot_client.get_historical_data(device_config, start_dt, end_dt)

            aggregator = DataAggregator()
            parameters = []

            for param in data:
                if param.measurements:
                    stats = aggregator.calculate_statistics(param.measurements)
                    trends = aggregator.detect_trends(param.measurements)

                    parameters.append({
                        "parameter": param.type,
                        "unit": param.unit,
                        "latest_value": param.latest_value,
                        "count": stats["count"],
                        "min": round(stats["min"], 1),
                        "max": round(stats["max"], 1),
                        "mean": round(stats["mean"], 1),
                        "trend": trends["trend"],
                        "trend_change_pct": round(trends["change_percentage"], 1),
                    })

            return {
                "device": device_config.name,
                "period": {"start": start_date, "end": end_date},
                "parameters": parameters,
            }

        except InBiotAPIError as e:
            return {"error": e.message, "device": device_config.name}

    @mcp.tool()
    async def get_all_devices_summary() -> dict:
        """
        Get a summary of all devices with status indicators.

        Shows key parameters (CO2, PM2.5, temperature, IAQ) for all devices
        in a single view, with status indicators highlighting devices that
        need attention. Useful for quick facility-wide assessment.
        """
        key_params = ["co2", "pm25", "temperature", "iaq", "thermalindicator"]

        async def fetch_device_data(device_id: str, config: DeviceConfig):
            try:
                data = await inbiot_client.get_latest_measurements(config)
                values = {}
                for param in data:
                    normalized = normalize_parameter_name(param.type)
                    if normalized in key_params and param.latest_value is not None:
                        values[normalized] = {"value": param.latest_value, "unit": param.unit}
                return device_id, config.name, values, None
            except InBiotAPIError as e:
                return device_id, config.name, {}, e.message

        tasks = [fetch_device_data(did, cfg) for did, cfg in devices.items()]
        results = await asyncio.gather(*tasks)

        device_summaries = []

        for device_id, name, values, error in results:
            if error:
                device_summaries.append({"id": device_id, "name": name, "status": "offline", "error": error})
                continue

            status = "good"

            co2_entry = values.get("co2")
            if co2_entry:
                threshold = get_threshold_for_parameter("co2")
                if threshold and co2_entry["value"] > threshold["acceptable"]:
                    status = "alert"
                elif threshold and co2_entry["value"] > threshold["good"]:
                    if status != "alert":
                        status = "warning"

            pm25_entry = values.get("pm25")
            if pm25_entry:
                threshold = get_threshold_for_parameter("pm25")
                if threshold and pm25_entry["value"] > threshold["acceptable"]:
                    status = "alert"
                elif threshold and pm25_entry["value"] > threshold["good"]:
                    if status != "alert":
                        status = "warning"

            temp_entry = values.get("temperature")
            if temp_entry:
                threshold = get_threshold_for_parameter("temperature")
                if threshold:
                    tv = temp_entry["value"]
                    if tv < threshold["acceptable_min"] or tv > threshold["acceptable_max"]:
                        status = "alert"
                    elif tv < threshold["optimal_min"] or tv > threshold["optimal_max"]:
                        if status != "alert":
                            status = "warning"

            iaq_entry = values.get("iaq")
            if iaq_entry:
                if iaq_entry["value"] < 40:
                    status = "alert"
                elif iaq_entry["value"] < 60 and status != "alert":
                    status = "warning"

            summary = {
                "id": device_id,
                "name": name,
                "status": status,
            }
            for k, v in values.items():
                summary[k] = v["value"]

            device_summaries.append(summary)

        return {"devices": device_summaries}
