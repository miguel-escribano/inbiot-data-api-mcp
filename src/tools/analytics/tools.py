"""Analytics tools for statistical analysis and data export."""

from collections import defaultdict
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from src.api.inbiot import InBiotClient, InBiotAPIError
from src.models.schemas import DeviceConfig
from src.utils.aggregation import DataAggregator
from src.utils.dates import parse_date_param
from src.utils.exporters import CSVExporter, JSONExporter
from src.utils.validation import validate_device
from src.utils.normalization import normalize_parameter_name


def register_analytics_tools(
    mcp: FastMCP,
    devices: dict[str, DeviceConfig],
    inbiot_client: InBiotClient,
):
    """Register analytics tools with the MCP server."""

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
    async def get_data_statistics(
        device: Annotated[str, Field(description="Device ID")],
        start_date: Annotated[str, Field(description="Start date (YYYY-MM-DD)")],
        end_date: Annotated[str, Field(description="End date (YYYY-MM-DD)")],
    ) -> dict:
        """
        Get comprehensive statistical analysis of historical data.

        Returns min, max, mean, median, std dev, quartiles, and trend analysis
        for each air quality parameter over the specified time range.
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

                    entry = {
                        "parameter": param.type,
                        "unit": param.unit,
                        "count": stats["count"],
                        "min": round(stats["min"], 2),
                        "max": round(stats["max"], 2),
                        "mean": round(stats["mean"], 2),
                        "median": round(stats["median"], 2),
                        "std_dev": round(stats["std_dev"], 2),
                        "trend": trends["trend"],
                        "trend_change_pct": round(trends["change_percentage"], 1),
                        "first_half_avg": trends["first_half_avg"],
                        "second_half_avg": trends["second_half_avg"],
                    }
                    if stats["q1"] is not None:
                        entry["q1"] = round(stats["q1"], 2)
                        entry["q3"] = round(stats["q3"], 2)

                    parameters.append(entry)

            return {
                "device": device_config.name,
                "period": {"start": start_date, "end": end_date},
                "parameters": parameters,
            }

        except InBiotAPIError as e:
            return {"error": e.message, "device": device_config.name}

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
    async def export_historical_data(
        device: Annotated[str, Field(description="Device ID")],
        start_date: Annotated[str, Field(description="Start date (YYYY-MM-DD)")],
        end_date: Annotated[str, Field(description="End date (YYYY-MM-DD)")],
        format: Annotated[str, Field(description="Export format: 'csv' or 'json'")] = "csv",
        aggregation: Annotated[
            str, Field(description="Aggregation period: 'none', 'hourly', 'daily', or 'weekly'")
        ] = "none",
    ) -> str | dict:
        """
        Export historical air quality data in CSV or JSON format.

        Supports raw measurements or time-aggregated data with statistics.
        Useful for external analysis, reporting, or archival purposes.
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

        if format not in ["csv", "json"]:
            return {"error": "Invalid format. Use 'csv' or 'json'."}

        if aggregation not in ["none", "hourly", "daily", "weekly"]:
            return {"error": "Invalid aggregation. Use 'none', 'hourly', 'daily', or 'weekly'."}

        try:
            data = await inbiot_client.get_historical_data(device_config, start_dt, end_dt)

            if aggregation == "none":
                if format == "csv":
                    return CSVExporter.export_measurements(data)
                else:
                    return JSONExporter.export_measurements(data)
            else:
                aggregator = DataAggregator()
                if format == "csv":
                    parts = []
                    for param in data:
                        if param.measurements:
                            aggregated = aggregator.aggregate_by_period(param.measurements, aggregation)
                            parts.append(f"# {param.type} ({param.unit})\n")
                            parts.append(CSVExporter.export_aggregated_by_period(aggregated))
                    return "".join(parts)
                else:
                    result = {
                        "device": device_config.name,
                        "period": {"start": start_date, "end": end_date},
                        "aggregation": aggregation,
                        "parameters": [],
                    }
                    for param in data:
                        if param.measurements:
                            aggregated = aggregator.aggregate_by_period(param.measurements, aggregation)
                            result["parameters"].append({
                                "parameter": param.type,
                                "unit": param.unit,
                                "data": JSONExporter.export_aggregated_by_period(
                                    param.type, param.unit, aggregation, aggregated
                                ),
                            })
                    return result

        except InBiotAPIError as e:
            return {"error": e.message, "device": device_config.name}

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
    async def detect_patterns(
        device: Annotated[str, Field(description="Device ID")],
        start_date: Annotated[str, Field(description="Start date (YYYY-MM-DD)")],
        end_date: Annotated[str, Field(description="End date (YYYY-MM-DD)")],
        parameter: Annotated[str, Field(description="Parameter to analyze (e.g., 'co2', 'pm25', 'temperature')")] = "co2",
    ) -> dict:
        """
        Detect daily and weekly patterns in air quality data.

        Analyzes historical data to find recurring patterns like peak hours,
        problematic days, and consistent issues. Useful for identifying
        when air quality typically degrades and planning interventions.
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

            normalized_param = normalize_parameter_name(parameter)
            param_data = None
            for p in data:
                if normalize_parameter_name(p.type) == normalized_param:
                    param_data = p
                    break

            if not param_data or not param_data.measurements:
                return {"error": f"No data found for parameter '{parameter}' in the specified date range."}

            measurements = param_data.measurements

            # Aggregate by hour of day
            hourly_values = defaultdict(list)
            for m in measurements:
                hourly_values[m.timestamp.hour].append(m.numeric_value)

            # Aggregate by day of week
            daily_values = defaultdict(list)
            day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            for m in measurements:
                daily_values[m.timestamp.weekday()].append(m.numeric_value)

            hourly_avg = {h: round(sum(v) / len(v), 1) for h, v in hourly_values.items()}
            daily_avg = {d: round(sum(v) / len(v), 1) for d, v in daily_values.items()}

            peak_hour = max(hourly_avg, key=hourly_avg.get) if hourly_avg else None
            trough_hour = min(hourly_avg, key=hourly_avg.get) if hourly_avg else None
            peak_day = max(daily_avg, key=daily_avg.get) if daily_avg else None
            trough_day = min(daily_avg, key=daily_avg.get) if daily_avg else None

            hourly_pattern = [
                {"hour": h, "avg": hourly_avg[h]}
                for h in sorted(hourly_avg.keys())
            ]

            daily_pattern = [
                {"day": day_names[d], "avg": daily_avg[d]}
                for d in sorted(daily_avg.keys())
            ]

            result = {
                "device": device_config.name,
                "parameter": param_data.type,
                "unit": param_data.unit,
                "period": {"start": start_date, "end": end_date},
                "data_points": len(measurements),
                "hourly_pattern": hourly_pattern,
                "daily_pattern": daily_pattern,
                "insights": {},
            }

            if peak_hour is not None and trough_hour is not None:
                peak_val = hourly_avg[peak_hour]
                trough_val = hourly_avg[trough_hour]
                result["insights"]["peak_hour"] = {"hour": peak_hour, "avg": peak_val}
                result["insights"]["best_hour"] = {"hour": trough_hour, "avg": trough_val}
                result["insights"]["daily_variation"] = round(peak_val - trough_val, 1)

            if peak_day is not None and trough_day is not None:
                result["insights"]["worst_day"] = {"day": day_names[peak_day], "avg": daily_avg[peak_day]}
                result["insights"]["best_day"] = {"day": day_names[trough_day], "avg": daily_avg[trough_day]}

            return result

        except InBiotAPIError as e:
            return {"error": e.message, "device": device_config.name}
