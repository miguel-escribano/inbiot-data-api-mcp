"""Statistical aggregation for air quality measurement data."""

import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Literal, Optional
from collections import defaultdict

from src.models.schemas import Measurement, ParameterData


class DataAggregator:
    """Statistical aggregation and analysis for measurement data."""

    @staticmethod
    def calculate_statistics(measurements: List[Measurement]) -> Dict:
        """
        Calculate comprehensive statistics for a list of measurements.

        Args:
            measurements: List of measurement data points

        Returns:
            Dictionary with statistical metrics (count, min, max, mean, median, etc.)
        """
        if not measurements:
            return {
                "count": 0,
                "min": None,
                "max": None,
                "mean": None,
                "median": None,
                "std_dev": None,
                "q1": None,
                "q3": None,
            }

        values = [m.numeric_value for m in measurements]

        stats = {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
        }

        # Standard deviation (requires at least 2 values)
        if len(values) > 1:
            stats["std_dev"] = statistics.stdev(values)
        else:
            stats["std_dev"] = 0.0

        # Quartiles (requires at least 2 values)
        if len(values) >= 2:
            quantiles = statistics.quantiles(values, n=4)
            stats["q1"] = quantiles[0]
            stats["q3"] = quantiles[2]
        else:
            stats["q1"] = None
            stats["q3"] = None

        return stats

    @staticmethod
    def detect_trends(measurements: List[Measurement]) -> Dict:
        """
        Detect trends in measurement data (increasing/decreasing/stable).

        Compares the mean of the first half vs second half of data.

        Args:
            measurements: List of measurement data points

        Returns:
            Dictionary with trend information
        """
        if len(measurements) < 2:
            return {
                "trend": "insufficient_data",
                "change_percentage": 0.0,
                "first_half_avg": None,
                "second_half_avg": None,
            }

        values = [m.numeric_value for m in measurements]
        midpoint = len(values) // 2

        first_half = values[:midpoint]
        second_half = values[midpoint:]

        first_avg = statistics.mean(first_half)
        second_avg = statistics.mean(second_half)

        # Calculate percentage change
        if first_avg != 0:
            change = ((second_avg - first_avg) / abs(first_avg)) * 100
        else:
            change = 0.0 if second_avg == 0 else 100.0

        # Classify trend
        if change > 5:
            trend = "increasing"
        elif change < -5:
            trend = "decreasing"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "change_percentage": round(change, 2),
            "first_half_avg": round(first_avg, 2),
            "second_half_avg": round(second_avg, 2),
        }

    @staticmethod
    def aggregate_by_period(
        measurements: List[Measurement],
        period: Literal["hourly", "daily", "weekly"],
    ) -> Dict[str, Dict]:
        """
        Group measurements by time period and calculate aggregates for each bucket.

        Args:
            measurements: List of measurement data points
            period: Time period for grouping (hourly, daily, weekly)

        Returns:
            Dictionary mapping time bucket keys to statistics
        """
        if not measurements:
            return {}

        # Define bucket size
        if period == "hourly":
            bucket_size = timedelta(hours=1)
            format_str = "%Y-%m-%d %H:00"
        elif period == "daily":
            bucket_size = timedelta(days=1)
            format_str = "%Y-%m-%d"
        else:  # weekly
            bucket_size = timedelta(weeks=1)
            format_str = "%Y-W%U"

        # Group measurements into buckets
        buckets: Dict[str, List[float]] = defaultdict(list)

        for m in measurements:
            timestamp = m.timestamp

            # Floor timestamp to bucket boundary
            if period == "hourly":
                bucket_key = timestamp.strftime(format_str)
            elif period == "daily":
                bucket_key = timestamp.strftime(format_str)
            else:  # weekly
                bucket_key = timestamp.strftime(format_str)

            buckets[bucket_key].append(m.numeric_value)

        # Calculate statistics for each bucket
        aggregated = {}
        for bucket_key, values in sorted(buckets.items()):
            aggregated[bucket_key] = {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "mean": round(statistics.mean(values), 2),
                "median": round(statistics.median(values), 2),
            }

        return aggregated

    @staticmethod
    def identify_exceedances(
        measurements: List[Measurement], threshold: float, above: bool = True
    ) -> List[Dict]:
        """
        Identify measurements that exceed a threshold.

        Args:
            measurements: List of measurement data points
            threshold: Threshold value to compare against
            above: If True, find values above threshold; if False, find values below

        Returns:
            List of exceedance events with timestamp and value
        """
        exceedances = []

        for m in measurements:
            value = m.numeric_value

            if (above and value > threshold) or (not above and value < threshold):
                exceedances.append(
                    {
                        "timestamp": m.timestamp.isoformat(),
                        "value": value,
                        "threshold": threshold,
                        "difference": round(value - threshold, 2),
                    }
                )

        return exceedances

    @staticmethod
    def calculate_time_weighted_average(measurements: List[Measurement]) -> Optional[float]:
        """
        Calculate time-weighted average (accounts for irregular sampling intervals).

        Args:
            measurements: List of measurement data points (must be time-ordered)

        Returns:
            Time-weighted average or None if insufficient data
        """
        if len(measurements) < 2:
            return None

        total_weighted_value = 0.0
        total_time = 0.0

        for i in range(len(measurements) - 1):
            current = measurements[i]
            next_m = measurements[i + 1]

            # Time interval in seconds
            interval = (next_m.timestamp - current.timestamp).total_seconds()

            # Weight the current value by the time interval
            total_weighted_value += current.numeric_value * interval
            total_time += interval

        if total_time > 0:
            return round(total_weighted_value / total_time, 2)

        return None

    @staticmethod
    def calculate_moving_average(
        measurements: List[Measurement], window_size: int = 5
    ) -> List[Dict]:
        """
        Calculate moving average with specified window size.

        Args:
            measurements: List of measurement data points
            window_size: Number of points to include in each average

        Returns:
            List of dictionaries with timestamp and moving average value
        """
        if len(measurements) < window_size:
            return []

        moving_averages = []

        for i in range(len(measurements) - window_size + 1):
            window = measurements[i : i + window_size]
            values = [m.numeric_value for m in window]
            avg_value = statistics.mean(values)

            # Use the timestamp of the last point in the window
            moving_averages.append(
                {
                    "timestamp": window[-1].timestamp.isoformat(),
                    "moving_average": round(avg_value, 2),
                    "window_size": window_size,
                }
            )

        return moving_averages
