"""
GO IAQS Compliance Calculator — rolling averages and limit checking.

Limits: GO AQS White Paper v1.0 (November 2025, ISBN 9798274916158).
Starter limits: Table p. 22 (PM2.5 24h, CO2 threshold).
Ultimate limits: Table p. 27 (7 pollutants, mixed averaging periods).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.models.schemas import Measurement
from src.tools.scoring.calculator import (
    CH2O_UG_TO_PPB,
    SENSOR_TO_GOIAQS,
    STARTER_POLLUTANTS,
)
from src.utils.normalization import normalize_parameter_name


@dataclass(frozen=True)
class Limit:
    value: float
    unit: str
    period_hours: int | None  # None = standing threshold
    label: str


STARTER_LIMITS: dict[str, list[Limit]] = {
    "pm25": [Limit(25, "µg/m³", 24, "24h avg")],
    "co2": [Limit(1000, "ppm", None, "threshold")],
}

ULTIMATE_LIMITS: dict[str, list[Limit]] = {
    "pm25": [Limit(15, "µg/m³", 1, "1h avg")],
    "co2": [Limit(800, "ppm", None, "threshold")],
    "o3": [Limit(51, "ppb", 8, "8h avg")],
    "ch2o": [Limit(27, "ppb", None, "threshold")],
    "co": [Limit(9, "ppm", 8, "8h avg"), Limit(31, "ppm", 1, "1h peak")],
    "no2": [Limit(21, "ppb", 8, "8h avg"), Limit(106, "ppb", 1, "1h peak")],
    "radon": [Limit(100, "Bq/m³", None, "threshold")],
}

CONTEXT_PARAMS = {"temperature", "humidity"}

CHART_HOURS = 24
MAX_LOOKBACK_HOURS = 48


def hourly_mean(
    measurements: list[Measurement],
    hour_start: datetime,
) -> float | None:
    """Mean of measurements within a 1-hour bucket [hour_start, hour_start+1h)."""
    hour_end = hour_start + timedelta(hours=1)
    values = [
        m.numeric_value for m in measurements
        if hour_start <= m.timestamp < hour_end
    ]
    if not values:
        return None
    return round(statistics.mean(values), 2)


def rolling_average(
    measurements: list[Measurement],
    window_end: datetime,
    period_hours: int,
) -> float | None:
    """Mean of measurements within (window_end - period_hours, window_end]."""
    window_start = window_end - timedelta(hours=period_hours)
    values = [
        m.numeric_value for m in measurements
        if window_start < m.timestamp <= window_end
    ]
    if not values:
        return None
    return round(statistics.mean(values), 2)


def determine_tier(available_keys: set[str]) -> str:
    """Starter = only PM2.5 and/or CO2; Ultimate = any pollutant beyond Starter set."""
    if available_keys <= STARTER_POLLUTANTS:
        return "starter"
    return "ultimate"


def _convert_ch2o(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value / CH2O_UG_TO_PPB, 1)


def compute_pollutant_series(
    measurements: list[Measurement],
    limits: list[Limit],
    chart_end: datetime,
    convert_from_ug: bool = False,
) -> dict:
    """Compute 24-point hourly compliance series for one pollutant.

    Returns dict with keys: limits, rolling_avg, hourly_mean, status,
    latest_rolling_avg, overall_status.
    """
    primary_limit = limits[0]
    rolling_avgs: list[float | None] = []
    hourly_means: list[float | None] = []
    statuses: list[str] = []

    for h in range(CHART_HOURS):
        hour_end = chart_end - timedelta(hours=CHART_HOURS - 1 - h)
        hour_start = hour_end - timedelta(hours=1)

        h_mean = hourly_mean(measurements, hour_start)
        if convert_from_ug:
            h_mean = _convert_ch2o(h_mean)

        if primary_limit.period_hours is not None:
            r_avg = rolling_average(measurements, hour_end, primary_limit.period_hours)
            if convert_from_ug:
                r_avg = _convert_ch2o(r_avg)
        else:
            r_avg = h_mean

        rolling_avgs.append(r_avg)
        hourly_means.append(h_mean)

        if r_avg is None:
            statuses.append("insufficient_data")
        else:
            point_pass = _check_all_limits(
                measurements, hour_end, limits, convert_from_ug,
            )
            statuses.append("pass" if point_pass else "fail")

    has_data = any(v is not None for v in rolling_avgs)
    has_fail = "fail" in statuses

    if not has_data:
        overall = "insufficient_data"
    elif has_fail:
        overall = "fail"
    else:
        overall = "pass"

    latest = next(
        (v for v in reversed(rolling_avgs) if v is not None), None
    )

    return {
        "limits": [
            {"value": lim.value, "label": lim.label, "period_hours": lim.period_hours}
            for lim in limits
        ],
        "unit": limits[0].unit,
        "rolling_avg": rolling_avgs,
        "hourly_mean": hourly_means,
        "status": statuses,
        "latest_rolling_avg": latest,
        "overall_status": overall,
    }


def _check_all_limits(
    measurements: list[Measurement],
    hour_end: datetime,
    limits: list[Limit],
    convert_from_ug: bool,
) -> bool:
    """Check all limits for a pollutant at a given hour. All must pass."""
    for lim in limits:
        if lim.period_hours is not None:
            avg = rolling_average(measurements, hour_end, lim.period_hours)
            if convert_from_ug:
                avg = _convert_ch2o(avg)
        else:
            hour_start = hour_end - timedelta(hours=1)
            avg = hourly_mean(measurements, hour_start)
            if convert_from_ug:
                avg = _convert_ch2o(avg)

        if avg is not None and avg > lim.value:
            return False
    return True


def compute_context_series(
    measurements: list[Measurement],
    unit: str,
    chart_end: datetime,
) -> dict:
    """Compute hourly mean series for temperature or humidity (no limits)."""
    values: list[float | None] = []
    for h in range(CHART_HOURS):
        hour_end = chart_end - timedelta(hours=CHART_HOURS - 1 - h)
        hour_start = hour_end - timedelta(hours=1)
        values.append(hourly_mean(measurements, hour_start))

    latest = next((v for v in reversed(values) if v is not None), None)

    return {
        "unit": unit,
        "values": values,
        "latest": latest,
    }


def build_compliance_result(
    param_data: dict[str, tuple[list[Measurement], str]],
    chart_end: datetime,
) -> dict:
    """Build the full compliance result from normalized parameter data.

    Parameters
    ----------
    param_data : dict mapping normalized parameter name to
                 (measurements, unit) tuples. Measurements must be sorted
                 by timestamp ascending and span up to MAX_LOOKBACK_HOURS
                 before chart_end.
    chart_end : the right edge of the chart (typically "now").

    Returns
    -------
    dict with tier, hours, starter, ultimate (or None), and available_pollutants.
    """
    goiaqs_keys: set[str] = set()
    goiaqs_data: dict[str, tuple[list[Measurement], str]] = {}
    context_data: dict[str, tuple[list[Measurement], str]] = {}

    for param_name, (measurements, unit) in param_data.items():
        if param_name in CONTEXT_PARAMS:
            context_data[param_name] = (measurements, unit)
            continue

        goiaqs_key = SENSOR_TO_GOIAQS.get(param_name)
        if goiaqs_key is not None:
            goiaqs_keys.add(goiaqs_key)
            goiaqs_data[goiaqs_key] = (measurements, unit)

    tier = determine_tier(goiaqs_keys)

    hour_labels = [
        (chart_end - timedelta(hours=CHART_HOURS - 1 - h)).isoformat()
        for h in range(CHART_HOURS)
    ]

    starter = _build_tier_section(
        goiaqs_data, context_data, STARTER_LIMITS, chart_end,
    )
    ultimate = None
    if tier == "ultimate":
        ultimate = _build_tier_section(
            goiaqs_data, context_data, ULTIMATE_LIMITS, chart_end,
        )

    return {
        "tier": tier,
        "hours": hour_labels,
        "starter": starter,
        "ultimate": ultimate,
        "available_pollutants": sorted(goiaqs_keys),
    }


def _build_tier_section(
    goiaqs_data: dict[str, tuple[list[Measurement], str]],
    context_data: dict[str, tuple[list[Measurement], str]],
    limits_table: dict[str, list[Limit]],
    chart_end: datetime,
) -> dict:
    """Build one tier's compliance data (starter or ultimate)."""
    section: dict = {}

    for pollutant, limits in limits_table.items():
        if pollutant not in goiaqs_data:
            section[pollutant] = {
                "limits": [
                    {"value": l.value, "label": l.label, "period_hours": l.period_hours}
                    for l in limits
                ],
                "unit": limits[0].unit,
                "rolling_avg": [None] * CHART_HOURS,
                "hourly_mean": [None] * CHART_HOURS,
                "status": ["insufficient_data"] * CHART_HOURS,
                "latest_rolling_avg": None,
                "overall_status": "insufficient_data",
            }
            continue

        measurements, sensor_unit = goiaqs_data[pollutant]
        convert = (pollutant == "ch2o" and "µg" in sensor_unit.lower())

        section[pollutant] = compute_pollutant_series(
            measurements, limits, chart_end, convert_from_ug=convert,
        )

    for param_name, (measurements, unit) in context_data.items():
        section[param_name] = compute_context_series(
            measurements, unit, chart_end,
        )

    return section
