"""Data export formatters for CSV and JSON output."""

import csv
import json
from io import StringIO
from typing import Dict, List

from src.models.schemas import ParameterData, WELLAssessment


class CSVExporter:
    """Export air quality data to CSV format."""

    @staticmethod
    def export_measurements(data: List[ParameterData]) -> str:
        """
        Export raw measurements to CSV format.

        Args:
            data: List of parameter data with measurements

        Returns:
            CSV-formatted string with all measurements
        """
        output = StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(["Timestamp", "Parameter", "Value", "Unit"])

        # Data rows
        for param in data:
            for measurement in param.measurements:
                writer.writerow(
                    [
                        measurement.timestamp.isoformat(),
                        param.type,
                        measurement.numeric_value,
                        param.unit,
                    ]
                )

        return output.getvalue()

    @staticmethod
    def export_statistics(
        param_type: str, stats: Dict, unit: str, trends: Dict = None
    ) -> str:
        """
        Export statistical summary to CSV format.

        Args:
            param_type: Parameter name (e.g., "temperature", "co2")
            stats: Statistical metrics dictionary
            unit: Unit of measurement
            trends: Optional trend analysis dictionary

        Returns:
            CSV-formatted string with statistics
        """
        output = StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(["Metric", "Value"])

        # Basic info
        writer.writerow(["Parameter", param_type])
        writer.writerow(["Unit", unit])
        writer.writerow([])

        # Statistics
        writer.writerow(["Statistics", ""])
        writer.writerow(["Count", stats.get("count", 0)])
        writer.writerow(["Min", stats.get("min")])
        writer.writerow(["Max", stats.get("max")])
        writer.writerow(["Mean", stats.get("mean")])
        writer.writerow(["Median", stats.get("median")])
        writer.writerow(["Std Dev", stats.get("std_dev")])
        writer.writerow(["Q1 (25th percentile)", stats.get("q1")])
        writer.writerow(["Q3 (75th percentile)", stats.get("q3")])

        # Trends if provided
        if trends:
            writer.writerow([])
            writer.writerow(["Trends", ""])
            writer.writerow(["Trend Direction", trends.get("trend")])
            writer.writerow(["Change %", trends.get("change_percentage")])
            writer.writerow(["First Half Avg", trends.get("first_half_avg")])
            writer.writerow(["Second Half Avg", trends.get("second_half_avg")])

        return output.getvalue()

    @staticmethod
    def export_aggregated_by_period(aggregated_data: Dict[str, Dict]) -> str:
        """
        Export time-period aggregated data to CSV.

        Args:
            aggregated_data: Dictionary mapping time periods to statistics

        Returns:
            CSV-formatted string with period-aggregated data
        """
        output = StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(["Period", "Count", "Min", "Max", "Mean", "Median"])

        # Data rows
        for period, stats in sorted(aggregated_data.items()):
            writer.writerow(
                [
                    period,
                    stats.get("count", 0),
                    stats.get("min"),
                    stats.get("max"),
                    stats.get("mean"),
                    stats.get("median"),
                ]
            )

        return output.getvalue()


class JSONExporter:
    """Export air quality data to JSON format."""

    @staticmethod
    def export_measurements(data: List[ParameterData]) -> str:
        """
        Export raw measurements to JSON format.

        Args:
            data: List of parameter data with measurements

        Returns:
            JSON-formatted string with all measurements
        """
        result = []

        for param in data:
            param_data = {
                "parameter": param.type,
                "unit": param.unit,
                "measurement_count": len(param.measurements),
                "measurements": [
                    {
                        "timestamp": m.timestamp.isoformat(),
                        "value": m.numeric_value,
                    }
                    for m in param.measurements
                ],
            }
            result.append(param_data)

        return json.dumps(result, indent=2)

    @staticmethod
    def export_statistics(
        param_type: str, stats: Dict, unit: str, trends: Dict = None
    ) -> str:
        """
        Export statistical summary to JSON format.

        Args:
            param_type: Parameter name
            stats: Statistical metrics dictionary
            unit: Unit of measurement
            trends: Optional trend analysis dictionary

        Returns:
            JSON-formatted string with statistics
        """
        result = {
            "parameter": param_type,
            "unit": unit,
            "statistics": stats,
        }

        if trends:
            result["trends"] = trends

        return json.dumps(result, indent=2)

    @staticmethod
    def export_aggregated_by_period(
        param_type: str, unit: str, period: str, aggregated_data: Dict[str, Dict]
    ) -> str:
        """
        Export time-period aggregated data to JSON.

        Args:
            param_type: Parameter name
            unit: Unit of measurement
            period: Period type (hourly, daily, weekly)
            aggregated_data: Dictionary mapping time periods to statistics

        Returns:
            JSON-formatted string with period-aggregated data
        """
        result = {
            "parameter": param_type,
            "unit": unit,
            "aggregation_period": period,
            "data": aggregated_data,
        }

        return json.dumps(result, indent=2)

    @staticmethod
    def export_well_assessment(assessment: WELLAssessment) -> str:
        """
        Export WELL assessment to structured JSON.

        Args:
            assessment: WELL compliance assessment object

        Returns:
            JSON-formatted string with WELL assessment
        """
        return assessment.model_dump_json(indent=2)

    @staticmethod
    def export_multi_parameter_statistics(
        device_name: str, stats_by_param: Dict[str, Dict]
    ) -> str:
        """
        Export statistics for multiple parameters to JSON.

        Args:
            device_name: Name of the device
            stats_by_param: Dictionary mapping parameter names to their statistics

        Returns:
            JSON-formatted string with multi-parameter statistics
        """
        result = {
            "device": device_name,
            "parameters": stats_by_param,
        }

        return json.dumps(result, indent=2)
