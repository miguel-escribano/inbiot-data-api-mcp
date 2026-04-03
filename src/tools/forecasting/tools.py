"""MCP tools for CO2 forecasting via Chronos-2-small on HuggingFace."""

from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastmcp import FastMCP
from pydantic import Field

from src.api.inbiot import InBiotClient, InBiotAPIError
from src.api.forecasting import (
    ForecastingClient,
    ForecastingAPIError,
    HORIZON_STEPS,
    CONTEXT_LENGTH,
)
from src.models.schemas import DeviceConfig
from src.utils.validation import validate_device
from src.utils.normalization import normalize_parameter_name

ALERT_THRESHOLDS_PPM = [800, 1000, 1500]


def _extract_co2_series(parameters: list) -> tuple[list[float], Optional[str]]:
    """
    Extract CO2 values from InBiot historical data, sorted chronologically.

    Returns (values, latest_timestamp_iso).
    """
    for param in parameters:
        if normalize_parameter_name(param.type) == "co2" and param.measurements:
            sorted_m = sorted(param.measurements, key=lambda m: m.date)
            values = [m.numeric_value for m in sorted_m]
            ts = sorted_m[-1].timestamp.isoformat() if sorted_m else None
            return values, ts
    return [], None


def _detect_threshold_crossings(
    current: Optional[float],
    median: list[float],
    interval_minutes: int,
) -> list[dict]:
    """Find when predicted CO2 first exceeds each alert threshold."""
    crossings = []
    for threshold in ALERT_THRESHOLDS_PPM:
        if current is not None and current >= threshold:
            continue
        for i, val in enumerate(median):
            if val >= threshold:
                crossings.append({
                    "threshold_ppm": threshold,
                    "minutes_until": (i + 1) * interval_minutes,
                    "predicted_value": round(val, 0),
                    "confidence": "median",
                })
                break
    return crossings


def register_forecasting_tools(
    mcp: FastMCP,
    devices: dict[str, DeviceConfig],
    inbiot_client: InBiotClient,
    forecasting_client: Optional[ForecastingClient] = None,
):
    """Register CO2 forecasting tools with the MCP server."""

    @mcp.tool(annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    })
    async def forecast_co2(
        device: Annotated[str, Field(
            description="Device ID (use list_devices to see options)"
        )],
        horizon: Annotated[str, Field(
            description=(
                "Prediction horizon: '10min', '1h', '2h', or '4h'. "
                "Longer horizons use ensemble/foundation models best. "
                "Default '2h'."
            )
        )] = "2h",
    ) -> dict:
        """
        Forecast future CO2 concentration for a device.

        Uses the last 24 hours of CO2 data as context and predicts future
        values at 10-minute intervals via Chronos-2-small (foundation model).
        Returns median prediction with 80% confidence interval (10th and 90th
        percentiles) and alerts when thresholds (800, 1000, 1500 ppm) are
        predicted to be crossed.

        Designed for proactive ventilation: anticipate CO2 build-up before
        it happens rather than reacting after the fact.

        Note: forecasting endpoint must be configured. Without it, this tool
        returns a structured error explaining how to set it up.
        """
        if forecasting_client is None:
            return {
                "error": (
                    "CO2 forecasting not configured. "
                    "Set HF_ENDPOINT_URL (and optionally HF_API_KEY) to point "
                    "to a HuggingFace Inference Endpoint running chronos-2-small. "
                    "See README for setup instructions."
                ),
            }

        try:
            device_config = validate_device(devices, device)
        except ValueError as e:
            return {"error": str(e)}

        if horizon not in HORIZON_STEPS:
            return {
                "error": f"Invalid horizon '{horizon}'. Use: {list(HORIZON_STEPS.keys())}",
            }

        now = datetime.now(tz=timezone.utc)
        lookback_start = now - timedelta(hours=24)

        try:
            historical = await inbiot_client.get_historical_data(
                device_config, lookback_start, now,
            )
        except InBiotAPIError as e:
            return {"error": f"Cannot fetch CO2 history: {e.message}", "device": device_config.name}

        co2_values, latest_ts = _extract_co2_series(historical)

        if len(co2_values) < 6:
            return {
                "error": (
                    f"Insufficient CO2 data for forecasting. "
                    f"Found {len(co2_values)} points, need at least 6 "
                    f"(1 hour at 10-min intervals). "
                    f"Device may be offline or CO2 sensor unavailable."
                ),
                "device": device_config.name,
            }

        try:
            raw_forecast = await forecasting_client.forecast(
                co2_values=co2_values,
                horizon=horizon,
            )
        except ForecastingAPIError as e:
            return {"error": f"Forecasting failed: {e.message}", "device": device_config.name}

        quantiles = raw_forecast.get("quantiles", {})
        median = [round(v, 1) for v in quantiles.get("0.5", [])]
        lower = [round(v, 1) for v in quantiles.get("0.1", [])]
        upper = [round(v, 1) for v in quantiles.get("0.9", [])]

        current_co2 = round(co2_values[-1], 1) if co2_values else None

        crossings = _detect_threshold_crossings(current_co2, median, interval_minutes=10)

        steps = HORIZON_STEPS[horizon]
        forecast_timestamps = [
            (now + timedelta(minutes=10 * (i + 1))).isoformat()
            for i in range(steps)
        ]

        result = {
            "device": device_config.name,
            "horizon": horizon,
            "current_co2_ppm": current_co2,
            "current_timestamp": latest_ts,
            "forecast": {
                "timestamps": forecast_timestamps[:len(median)],
                "median_ppm": median,
                "lower_bound_ppm (p10)": lower,
                "upper_bound_ppm (p90)": upper,
                "interval_minutes": 10,
                "steps": len(median),
            },
            "threshold_alerts": crossings if crossings else "No threshold crossings predicted",
            "context": {
                "data_points_used": min(len(co2_values), CONTEXT_LENGTH),
                "model": "chronos-2-small",
                "source": "HuggingFace Inference Endpoint",
            },
        }

        return result
