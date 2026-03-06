"""Analytics tools for statistical analysis and data export."""

from collections import defaultdict
from datetime import datetime
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from src.api.inbiot import InBiotClient, InBiotAPIError
from src.models.schemas import DeviceConfig
from src.utils.provenance import create_data_unavailable_error
from src.utils.aggregation import DataAggregator
from src.utils.exporters import CSVExporter, JSONExporter
from src.well.thresholds import get_threshold_for_parameter, normalize_parameter_name


def register_analytics_tools(
    mcp: FastMCP,
    devices: dict[str, DeviceConfig],
    inbiot_client: InBiotClient,
):
    """Register analytics tools with the MCP server."""

    @mcp.tool()
    async def get_data_statistics(
        device: Annotated[str, Field(description="Device ID")],
        start_date: Annotated[str, Field(description="Start date (YYYY-MM-DD)")],
        end_date: Annotated[str, Field(description="End date (YYYY-MM-DD)")],
    ) -> str:
        """
        Get comprehensive statistical analysis of historical data.

        Returns min, max, mean, median, std dev, quartiles, and trend analysis
        for each air quality parameter over the specified time range.
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

        try:
            data = await inbiot_client.get_historical_data(device_config, start_dt, end_dt)

            aggregator = DataAggregator()
            result = f"## Statistical Analysis: {device_config.name}\n\n"
            result += f"**Period**: {start_date} to {end_date}\n\n"

            for param in data:
                if param.measurements:
                    stats = aggregator.calculate_statistics(param.measurements)
                    trends = aggregator.detect_trends(param.measurements)

                    result += f"### {param.type} ({param.unit})\n\n"

                    # Statistics table
                    result += "| Statistic | Value |\n"
                    result += "|-----------|-------|\n"
                    result += f"| Count | {stats['count']} |\n"
                    result += f"| Min | {stats['min']:.2f} |\n"
                    result += f"| Max | {stats['max']:.2f} |\n"
                    result += f"| Mean | {stats['mean']:.2f} |\n"
                    result += f"| Median | {stats['median']:.2f} |\n"
                    result += f"| Std Dev | {stats['std_dev']:.2f} |\n"

                    if stats["q1"] is not None:
                        result += f"| Q1 (25th %) | {stats['q1']:.2f} |\n"
                        result += f"| Q3 (75th %) | {stats['q3']:.2f} |\n"

                    # Trend analysis
                    result += "\n**Trend Analysis**:\n"
                    result += f"- Direction: {trends['trend'].upper()}\n"
                    result += f"- Change: {trends['change_percentage']:+.1f}%\n"
                    result += f"- First half average: {trends['first_half_avg']}\n"
                    result += f"- Second half average: {trends['second_half_avg']}\n\n"

            return result

        except InBiotAPIError as e:
            return create_data_unavailable_error(
                device_name=device_config.name,
                error_message=e.message,
            )

    @mcp.tool()
    async def export_historical_data(
        device: Annotated[str, Field(description="Device ID")],
        start_date: Annotated[str, Field(description="Start date (YYYY-MM-DD)")],
        end_date: Annotated[str, Field(description="End date (YYYY-MM-DD)")],
        format: Annotated[str, Field(description="Export format: 'csv' or 'json'")] = "csv",
        aggregation: Annotated[
            str, Field(description="Aggregation period: 'none', 'hourly', 'daily', or 'weekly'")
        ] = "none",
    ) -> str:
        """
        Export historical air quality data in CSV or JSON format.

        Supports raw measurements or time-aggregated data with statistics.
        Useful for external analysis, reporting, or archival purposes.
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

        # Validate format
        if format not in ["csv", "json"]:
            return "Invalid format. Use 'csv' or 'json'."

        # Validate aggregation
        if aggregation not in ["none", "hourly", "daily", "weekly"]:
            return "Invalid aggregation. Use 'none', 'hourly', 'daily', or 'weekly'."

        try:
            data = await inbiot_client.get_historical_data(device_config, start_dt, end_dt)

            if aggregation == "none":
                # Export raw measurements
                if format == "csv":
                    return CSVExporter.export_measurements(data)
                else:
                    return JSONExporter.export_measurements(data)
            else:
                # Export aggregated data
                aggregator = DataAggregator()
                result = f"## Aggregated Data Export: {device_config.name}\n\n"
                result += f"**Period**: {start_date} to {end_date}\n"
                result += f"**Aggregation**: {aggregation}\n\n"

                for param in data:
                    if param.measurements:
                        aggregated = aggregator.aggregate_by_period(
                            param.measurements, aggregation
                        )

                        result += f"### {param.type} ({param.unit})\n\n"

                        if format == "csv":
                            result += "```csv\n"
                            result += CSVExporter.export_aggregated_by_period(aggregated)
                            result += "```\n\n"
                        else:
                            result += "```json\n"
                            result += JSONExporter.export_aggregated_by_period(
                                param.type, param.unit, aggregation, aggregated
                            )
                            result += "```\n\n"

                return result

        except InBiotAPIError as e:
            return create_data_unavailable_error(
                device_name=device_config.name,
                error_message=e.message,
            )

    @mcp.tool()
    async def detect_patterns(
        device: Annotated[str, Field(description="Device ID")],
        start_date: Annotated[str, Field(description="Start date (YYYY-MM-DD)")],
        end_date: Annotated[str, Field(description="End date (YYYY-MM-DD)")],
        parameter: Annotated[str, Field(description="Parameter to analyze (e.g., 'co2', 'pm25', 'temperature')")] = "co2",
    ) -> str:
        """
        Detect daily and weekly patterns in air quality data.

        Analyzes historical data to find recurring patterns like peak hours,
        problematic days, and consistent issues. Useful for identifying
        when air quality typically degrades and planning interventions.
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

        try:
            data = await inbiot_client.get_historical_data(device_config, start_dt, end_dt)

            # Find the requested parameter
            normalized_param = normalize_parameter_name(parameter)
            param_data = None
            for p in data:
                if normalize_parameter_name(p.type) == normalized_param:
                    param_data = p
                    break

            if not param_data or not param_data.measurements:
                return f"No data found for parameter '{parameter}' in the specified date range."

            measurements = param_data.measurements
            threshold = get_threshold_for_parameter(normalized_param)

            # Aggregate by hour of day
            hourly_values = defaultdict(list)
            for m in measurements:
                hour = m.timestamp.hour
                hourly_values[hour].append(m.numeric_value)

            # Aggregate by day of week
            daily_values = defaultdict(list)
            day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            for m in measurements:
                day = m.timestamp.weekday()
                daily_values[day].append(m.numeric_value)

            # Calculate averages
            hourly_avg = {h: sum(v) / len(v) for h, v in hourly_values.items()}
            daily_avg = {d: sum(v) / len(v) for d, v in daily_values.items()}

            # Find peaks and troughs
            if hourly_avg:
                peak_hour = max(hourly_avg, key=hourly_avg.get)
                trough_hour = min(hourly_avg, key=hourly_avg.get)
            else:
                peak_hour = trough_hour = None

            if daily_avg:
                peak_day = max(daily_avg, key=daily_avg.get)
                trough_day = min(daily_avg, key=daily_avg.get)
            else:
                peak_day = trough_day = None

            # Build result
            result = f"## Pattern Analysis: {param_data.type}\n\n"
            result += f"**Device**: {device_config.name}\n"
            result += f"**Period**: {start_date} to {end_date}\n"
            result += f"**Data Points**: {len(measurements)}\n\n"

            # Hourly patterns
            result += "### Hourly Patterns\n\n"
            result += "| Hour | Average | Status |\n"
            result += "|------|---------|--------|\n"

            for hour in sorted(hourly_avg.keys()):
                avg = hourly_avg[hour]
                status = ""
                if hour == peak_hour:
                    status = "📈 Peak"
                elif hour == trough_hour:
                    status = "📉 Best"
                elif threshold:
                    good_val = threshold.get("good", threshold.get("optimal_max", 100))
                    if avg > good_val:
                        status = "⚠️ Elevated"
                result += f"| {hour:02d}:00 | {avg:.1f} {param_data.unit} | {status} |\n"

            # Daily patterns
            result += "\n### Daily Patterns\n\n"
            result += "| Day | Average | Status |\n"
            result += "|-----|---------|--------|\n"

            for day in sorted(daily_avg.keys()):
                avg = daily_avg[day]
                status = ""
                if day == peak_day:
                    status = "📈 Worst"
                elif day == trough_day:
                    status = "📉 Best"
                result += f"| {day_names[day]} | {avg:.1f} {param_data.unit} | {status} |\n"

            # Key insights
            result += "\n### Key Insights\n\n"

            if peak_hour is not None and trough_hour is not None:
                peak_val = hourly_avg[peak_hour]
                trough_val = hourly_avg[trough_hour]
                diff = peak_val - trough_val

                result += f"- **Peak hour**: {peak_hour:02d}:00 (avg: {peak_val:.1f} {param_data.unit})\n"
                result += f"- **Best hour**: {trough_hour:02d}:00 (avg: {trough_val:.1f} {param_data.unit})\n"
                if trough_val > 0:
                    result += f"- **Daily variation**: {diff:.1f} {param_data.unit} ({(diff/trough_val*100):.0f}% swing)\n\n"
                else:
                    result += f"- **Daily variation**: {diff:.1f} {param_data.unit}\n\n"

            if peak_day is not None and trough_day is not None:
                result += f"- **Worst day**: {day_names[peak_day]} (avg: {daily_avg[peak_day]:.1f} {param_data.unit})\n"
                result += f"- **Best day**: {day_names[trough_day]} (avg: {daily_avg[trough_day]:.1f} {param_data.unit})\n\n"

            # Recommendations based on patterns
            result += "### Recommendations\n\n"

            if peak_hour is not None:
                if 9 <= peak_hour <= 17:
                    result += f"- {param_data.type} peaks during business hours ({peak_hour:02d}:00). Consider increasing ventilation during this time.\n"
                elif peak_hour < 9:
                    result += f"- {param_data.type} peaks in early morning ({peak_hour:02d}:00). Check if HVAC starts early enough.\n"
                else:
                    result += f"- {param_data.type} peaks in evening ({peak_hour:02d}:00). Review after-hours ventilation settings.\n"

            if peak_day is not None:
                weekday_avg = sum(daily_avg.get(d, 0) for d in range(5)) / 5 if any(d in daily_avg for d in range(5)) else 0
                weekend_avg = sum(daily_avg.get(d, 0) for d in range(5, 7)) / 2 if any(d in daily_avg for d in range(5, 7)) else 0

                if weekday_avg > 0 and weekend_avg > 0:
                    if weekday_avg > weekend_avg * 1.2:
                        result += "- Weekday levels are significantly higher than weekends. Occupancy-related issue likely.\n"
                    elif weekend_avg > weekday_avg * 1.2:
                        result += "- Weekend levels are higher than weekdays. Check if HVAC runs on reduced schedule.\n"

            return result

        except InBiotAPIError as e:
            return create_data_unavailable_error(
                device_name=device_config.name,
                error_message=e.message,
            )
