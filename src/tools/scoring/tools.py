"""MCP tools for GO IAQS Score and Compliance from live sensor data."""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from src.api.inbiot import InBiotClient, InBiotAPIError
from src.models.schemas import DeviceConfig
from src.utils.validation import validate_device
from src.utils.normalization import normalize_parameter_name
from src.tools.scoring.calculator import GoIaqsCalculator
from src.tools.scoring.compliance import (
    MAX_LOOKBACK_HOURS,
    build_compliance_result,
)


def register_scoring_tools(
    mcp: FastMCP,
    devices: dict[str, DeviceConfig],
    inbiot_client: InBiotClient,
):
    """Register GO IAQS scoring tools with the MCP server."""

    calculator = GoIaqsCalculator()

    @mcp.tool(annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    })
    async def calculate_go_iaqs_score(
        device: Annotated[str, Field(
            description="Device ID (use list_devices to see options)"
        )],
    ) -> dict:
        """
        Calculate the GO IAQS Score for a device using its latest sensor readings.

        Fetches the most recent measurements, computes per-pollutant sub-scores
        via piecewise linear interpolation (GO AQS White Paper v1.0), applies the
        synergistic reduction rule, and returns the full structured result including
        tier, grade, category, dominant pollutant, and health advice.

        The tier is auto-detected: Starter (PM2.5 + CO2 only) or Ultimate (5+
        pollutants). MICA Plus/WELL variants typically qualify for Ultimate (6 of 7;
        radon always requires a dedicated monitor).
        """
        try:
            device_config = validate_device(devices, device)
        except ValueError as e:
            return {"error": str(e)}

        try:
            data = await inbiot_client.get_latest_measurements(device_config)

            measurements = []
            reading_timestamp = None
            for param in data:
                if param.latest_value is not None:
                    measurements.append({
                        "parameter": param.type,
                        "value": param.latest_value,
                        "unit": param.unit,
                    })
                    if reading_timestamp is None and param.latest_timestamp is not None:
                        reading_timestamp = param.latest_timestamp.isoformat()

            result = calculator.calculate_from_sensor(measurements)

            go_iaqs = {
                "tier": result.tier,
                "pollutants_measured": result.pollutants_measured,
                "pollutants_total": result.pollutants_total,
                "sub_scores": {
                    key: _pollutant_score_to_dict(ps)
                    for key, ps in result.sub_scores.items()
                },
                "missing": result.missing,
                "total_score": result.total_score,
                "grade": result.grade,
                "category": result.category,
                "color_hex": result.color_hex,
                "dominant_pollutant": result.dominant_pollutant,
                "health_advice": result.health_advice,
                "synergistic_reduction": result.synergistic_reduction,
            }

            response: dict = {
                "device": device_config.name,
                "go_iaqs": go_iaqs,
            }
            if reading_timestamp:
                response["timestamp"] = reading_timestamp

            return response

        except InBiotAPIError as e:
            return {"error": e.message, "device": device_config.name}


    @mcp.tool(annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    })
    async def check_go_iaqs_compliance(
        device: Annotated[str, Field(
            description="Device ID (use list_devices to see options)"
        )],
    ) -> dict:
        """
        Check GO IAQS compliance for a device over the last 24 hours.

        Returns hourly time series data for both Starter and Ultimate tiers,
        with rolling averages computed at the correct averaging period for
        each pollutant (24h for Starter PM2.5, 1h for Ultimate PM2.5,
        8h for O3/CO/NO2, etc.). Threshold pollutants (CO2, CH2O, Radon)
        use hourly means directly.

        The tier is auto-detected from available pollutants. Starter data is
        always returned. Ultimate data is returned only when the sensor
        measures pollutants beyond PM2.5 and CO2.

        Temperature and humidity are included as context (no limits).

        Designed for chart rendering: the response contains flat arrays
        (hours, rolling_avg, hourly_mean, status) that map directly to
        time series chart data points.

        Fetches 48 hours of historical data (1 API call, cached 60 min)
        to ensure rolling averages are computable at the start of the
        24-hour chart window.
        """
        try:
            device_config = validate_device(devices, device)
        except ValueError as e:
            return {"error": str(e)}

        try:
            now = datetime.now(tz=timezone.utc)
            start = now - timedelta(hours=MAX_LOOKBACK_HOURS)

            historical = await inbiot_client.get_historical_data(
                device_config, start, now,
            )

            param_data: dict[str, tuple[list, str]] = {}
            for param in historical:
                if param.measurements:
                    normalized = normalize_parameter_name(param.type)
                    param_data[normalized] = (param.measurements, param.unit)

            result = build_compliance_result(param_data, now)

            return {
                "device": device_config.name,
                "compliance": result,
            }

        except InBiotAPIError as e:
            return {"error": e.message, "device": device_config.name}


def _pollutant_score_to_dict(ps) -> dict:
    d: dict = {"value": ps.value, "unit": ps.unit, "score": ps.score}
    if ps.converted_ppb is not None:
        d["converted_ppb"] = ps.converted_ppb
    return d
