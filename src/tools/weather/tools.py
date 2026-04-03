"""Weather tools for outdoor conditions and indoor/outdoor comparison."""

from datetime import datetime, timezone, timedelta
from typing import Annotated, Optional

from fastmcp import FastMCP
from pydantic import Field

from src.api.inbiot import InBiotClient, InBiotAPIError
from src.api.openweather import OpenWeatherClient, OpenWeatherAPIError
from src.models.schemas import DeviceConfig
from src.utils.validation import validate_device


def register_weather_tools(
    mcp: FastMCP,
    devices: dict[str, DeviceConfig],
    inbiot_client: InBiotClient,
    openweather_client: Optional[OpenWeatherClient] = None,
):
    """Register weather tools with the MCP server."""

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
    async def outdoor_snapshot(
        device: Annotated[str, Field(description="Device ID (uses device coordinates for location)")]
    ) -> dict:
        """
        Get current outdoor weather and air quality conditions.

        Uses the device's configured coordinates to fetch outdoor data from OpenWeather.
        """
        try:
            device_config = validate_device(devices, device)
        except ValueError as e:
            return {"error": str(e)}

        if openweather_client is None:
            return {"error": "OpenWeather API key not configured. Set OPENWEATHER_API_KEY environment variable."}

        lat, lon = device_config.coordinates

        try:
            conditions = await openweather_client.get_outdoor_conditions(
                lat=lat, lon=lon, location_name=device_config.name,
            )

            aqi_labels = {1: "Good", 2: "Fair", 3: "Moderate", 4: "Poor", 5: "Very Poor"}
            return {
                "device": device_config.name,
                "coordinates": {"lat": lat, "lon": lon},
                "weather": {
                    "temperature_c": conditions.temperature,
                    "humidity_pct": conditions.humidity,
                    "pressure_hpa": conditions.pressure,
                    "wind_speed_ms": conditions.wind_speed,
                    "description": conditions.description,
                },
                "air_quality": {
                    "aqi": conditions.aqi,
                    "aqi_label": aqi_labels.get(conditions.aqi, "Unknown"),
                    "pm25_ugm3": conditions.pm25,
                    "pm10_ugm3": conditions.pm10,
                    "o3_ugm3": conditions.o3,
                    "no2_ugm3": conditions.no2,
                    "no_ugm3": conditions.no,
                    "so2_ugm3": conditions.so2,
                    "co_ugm3": conditions.co,
                    "nh3_ugm3": conditions.nh3,
                },
                "source": "OpenWeather API",
            }

        except OpenWeatherAPIError as e:
            return {"error": e.message}

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
    async def indoor_vs_outdoor(
        device: Annotated[str, Field(description="Device ID for comparison")]
    ) -> dict:
        """
        Compare indoor air quality with outdoor conditions.

        Shows side-by-side comparison of key parameters and calculates
        filtration effectiveness. Useful for understanding building envelope performance.
        """
        try:
            device_config = validate_device(devices, device)
        except ValueError as e:
            return {"error": str(e)}

        if openweather_client is None:
            return {"error": "OpenWeather API key not configured. Set OPENWEATHER_API_KEY environment variable."}

        lat, lon = device_config.coordinates

        try:
            indoor_data = await inbiot_client.get_latest_measurements(device_config)
        except InBiotAPIError as e:
            return {"error": f"Indoor data unavailable: {e.message}"}

        try:
            outdoor = await openweather_client.get_outdoor_conditions(lat, lon, device_config.name)
        except OpenWeatherAPIError as e:
            return {"error": f"Indoor data retrieved but outdoor data failed: {e.message}"}

        indoor_values = {}
        for param in indoor_data:
            if param.latest_value is not None:
                indoor_values[param.type.lower()] = {"value": param.latest_value, "unit": param.unit}

        comparisons = []

        def add_comparison(name, indoor_key, outdoor_val, unit):
            if indoor_key in indoor_values and outdoor_val is not None:
                iv = indoor_values[indoor_key]["value"]
                delta = iv - outdoor_val
                entry = {"parameter": name, "indoor": iv, "outdoor": outdoor_val, "delta": round(delta, 1), "unit": unit}
                if name in ("PM2.5", "PM10") and outdoor_val > 0:
                    reduction = ((outdoor_val - iv) / outdoor_val) * 100
                    entry["filtration_pct"] = round(reduction, 0)
                comparisons.append(entry)

        add_comparison("Temperature", "temperature", outdoor.temperature, "C")
        add_comparison("Humidity", "humidity", outdoor.humidity, "%")
        add_comparison("PM2.5", "pm25", outdoor.pm25, "ug/m3")
        add_comparison("PM10", "pm10", outdoor.pm10, "ug/m3")

        return {
            "device": device_config.name,
            "comparisons": comparisons,
        }

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
    async def outdoor_forecast(
        device: Annotated[str, Field(description="Device ID (uses device coordinates for location)")],
        hours: Annotated[int, Field(description="Number of hours to forecast (1-96, default 24)", ge=1, le=96)] = 24,
    ) -> dict:
        """
        Get outdoor air quality forecast for the next hours.

        Returns hourly AQI and pollutant concentrations for up to 4 days.
        Useful for planning ventilation windows — identify when outdoor air
        quality will be best or worst.
        """
        try:
            device_config = validate_device(devices, device)
        except ValueError as e:
            return {"error": str(e)}

        if openweather_client is None:
            return {"error": "OpenWeather API key not configured. Set OPENWEATHER_API_KEY environment variable."}

        lat, lon = device_config.coordinates

        try:
            forecast_data = await openweather_client.get_air_pollution_forecast(lat, lon)
        except OpenWeatherAPIError as e:
            return {"error": e.message}

        aqi_labels = {1: "Good", 2: "Fair", 3: "Moderate", 4: "Poor", 5: "Very Poor"}
        entries = forecast_data.get("list", [])[:hours]

        hourly = []
        aqi_values = []
        for entry in entries:
            aqi = entry.get("main", {}).get("aqi")
            components = entry.get("components", {})
            aqi_values.append(aqi)
            hourly.append({
                "timestamp": datetime.fromtimestamp(entry["dt"], tz=timezone.utc).isoformat(),
                "aqi": aqi,
                "aqi_label": aqi_labels.get(aqi, "Unknown"),
                "pm25_ugm3": components.get("pm2_5"),
                "pm10_ugm3": components.get("pm10"),
                "o3_ugm3": components.get("o3"),
                "no2_ugm3": components.get("no2"),
                "co_ugm3": components.get("co"),
            })

        # Find best and worst windows
        best_hour = min(hourly, key=lambda h: (h["aqi"] or 99)) if hourly else None
        worst_hour = max(hourly, key=lambda h: (h["aqi"] or 0)) if hourly else None

        return {
            "device": device_config.name,
            "coordinates": {"lat": lat, "lon": lon},
            "forecast_hours": len(hourly),
            "summary": {
                "best_window": {"timestamp": best_hour["timestamp"], "aqi": best_hour["aqi"], "aqi_label": best_hour["aqi_label"]} if best_hour else None,
                "worst_window": {"timestamp": worst_hour["timestamp"], "aqi": worst_hour["aqi"], "aqi_label": worst_hour["aqi_label"]} if worst_hour else None,
            },
            "hourly": hourly,
            "source": "OpenWeather Air Pollution Forecast API",
        }

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
    async def outdoor_history(
        device: Annotated[str, Field(description="Device ID (uses device coordinates for location)")],
        hours_back: Annotated[int, Field(description="Hours of history to retrieve (1-168, default 24)", ge=1, le=168)] = 24,
    ) -> dict:
        """
        Get historical outdoor air quality for a past time range.

        Returns hourly AQI and pollutant concentrations. Useful for correlating
        indoor air quality events with outdoor conditions — e.g., did an indoor
        PM2.5 spike coincide with poor outdoor air quality?
        """
        try:
            device_config = validate_device(devices, device)
        except ValueError as e:
            return {"error": str(e)}

        if openweather_client is None:
            return {"error": "OpenWeather API key not configured. Set OPENWEATHER_API_KEY environment variable."}

        lat, lon = device_config.coordinates
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=hours_back)

        try:
            history_data = await openweather_client.get_air_pollution_history(lat, lon, start, now)
        except OpenWeatherAPIError as e:
            return {"error": e.message}

        aqi_labels = {1: "Good", 2: "Fair", 3: "Moderate", 4: "Poor", 5: "Very Poor"}
        entries = history_data.get("list", [])

        hourly = []
        aqi_values = []
        for entry in entries:
            aqi = entry.get("main", {}).get("aqi")
            components = entry.get("components", {})
            aqi_values.append(aqi)
            hourly.append({
                "timestamp": datetime.fromtimestamp(entry["dt"], tz=timezone.utc).isoformat(),
                "aqi": aqi,
                "aqi_label": aqi_labels.get(aqi, "Unknown"),
                "pm25_ugm3": components.get("pm2_5"),
                "pm10_ugm3": components.get("pm10"),
                "o3_ugm3": components.get("o3"),
                "no2_ugm3": components.get("no2"),
                "co_ugm3": components.get("co"),
            })

        valid_aqi = [a for a in aqi_values if a is not None]
        return {
            "device": device_config.name,
            "coordinates": {"lat": lat, "lon": lon},
            "period": {
                "start": start.isoformat(),
                "end": now.isoformat(),
                "hours": hours_back,
                "data_points": len(hourly),
            },
            "summary": {
                "avg_aqi": round(sum(valid_aqi) / len(valid_aqi), 1) if valid_aqi else None,
                "worst_aqi": max(valid_aqi) if valid_aqi else None,
                "best_aqi": min(valid_aqi) if valid_aqi else None,
                "worst_aqi_label": aqi_labels.get(max(valid_aqi), "Unknown") if valid_aqi else None,
            },
            "hourly": hourly,
            "source": "OpenWeather Air Pollution History API",
        }
