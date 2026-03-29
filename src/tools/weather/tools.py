"""Weather tools for outdoor conditions and indoor/outdoor comparison."""

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
                    "co_ugm3": conditions.co,
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
