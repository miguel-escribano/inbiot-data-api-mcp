"""Weather tools for outdoor conditions and indoor/outdoor comparison."""

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from src.api.inbiot import InBiotClient, InBiotAPIError
from src.api.openweather import OpenWeatherClient, OpenWeatherAPIError
from src.models.schemas import DeviceConfig
from src.utils.provenance import (
    generate_outdoor_provenance,
    create_data_unavailable_error,
)


def register_weather_tools(
    mcp: FastMCP,
    devices: dict[str, DeviceConfig],
    inbiot_client: InBiotClient,
):
    """Register weather tools with the MCP server."""

    @mcp.tool()
    async def outdoor_snapshot(
        device: Annotated[str, Field(description="Device ID (uses device coordinates for location)")]
    ) -> str:
        """
        Get current outdoor weather and air quality conditions.

        Uses the device's configured coordinates to fetch outdoor data from OpenWeather.
        This data is for contextual comparison only - NOT used for WELL indoor scoring.
        """
        if device not in devices:
            return f"Unknown device: {device}. Use list_devices to see available options."

        device_config = devices[device]
        lat, lon = device_config.coordinates

        try:
            openweather = OpenWeatherClient()
            conditions = await openweather.get_outdoor_conditions(
                lat=lat,
                lon=lon,
                location_name=device_config.name,
            )

            # Format results
            result = f"## Outdoor Conditions near {device_config.name}\n\n"

            result += "### Weather\n\n"
            result += f"- **Temperature**: {conditions.temperature}°C\n"
            result += f"- **Humidity**: {conditions.humidity}%\n"
            result += f"- **Pressure**: {conditions.pressure} hPa\n"
            result += f"- **Wind**: {conditions.wind_speed} m/s\n"
            result += f"- **Conditions**: {conditions.description}\n\n"

            result += "### Air Quality\n\n"
            aqi_labels = {1: "Good", 2: "Fair", 3: "Moderate", 4: "Poor", 5: "Very Poor"}
            result += f"- **AQI**: {conditions.aqi} ({aqi_labels.get(conditions.aqi, 'Unknown')})\n"
            result += f"- **PM2.5**: {conditions.pm25} µg/m³\n"
            result += f"- **PM10**: {conditions.pm10} µg/m³\n"
            result += f"- **O₃**: {conditions.o3} µg/m³\n"
            result += f"- **NO₂**: {conditions.no2} µg/m³\n"
            result += f"- **CO**: {conditions.co} µg/m³\n"

            result += generate_outdoor_provenance(
                location=device_config.name,
                coordinates=device_config.coordinates,
                endpoint="/data/2.5/weather + /data/2.5/air_pollution",
            )

            return result

        except OpenWeatherAPIError as e:
            return f"## Outdoor Data Unavailable\n\n**Error**: {e.message}\n\nSet OPENWEATHER_API_KEY environment variable to enable outdoor data."

    @mcp.tool()
    async def indoor_vs_outdoor(
        device: Annotated[str, Field(description="Device ID for comparison")]
    ) -> str:
        """
        Compare indoor air quality with outdoor conditions.

        Shows side-by-side comparison of key parameters and calculates
        filtration effectiveness. Useful for understanding building envelope performance.
        """
        if device not in devices:
            return f"Unknown device: {device}. Use list_devices to see available options."

        device_config = devices[device]
        lat, lon = device_config.coordinates

        # Get indoor data
        try:
            indoor_data = await inbiot_client.get_latest_measurements(device_config)
        except InBiotAPIError as e:
            return create_data_unavailable_error(
                device_name=device_config.name,
                error_message=e.message,
            )

        # Get outdoor data
        try:
            openweather = OpenWeatherClient()
            outdoor = await openweather.get_outdoor_conditions(lat, lon, device_config.name)
        except OpenWeatherAPIError as e:
            return f"## Comparison Unavailable\n\nIndoor data retrieved but outdoor data failed: {e.message}"

        # Build comparison
        result = f"## Indoor vs Outdoor Comparison: {device_config.name}\n\n"

        # Create lookup for indoor values
        indoor_values = {}
        for param in indoor_data:
            if param.latest_value is not None:
                indoor_values[param.type.lower()] = (param.latest_value, param.unit)

        result += "| Parameter | Indoor | Outdoor | Δ (Indoor-Outdoor) | Assessment |\n"
        result += "|-----------|--------|---------|-------------------|------------|\n"

        # Temperature
        if "temperature" in indoor_values and outdoor.temperature:
            indoor_temp, unit = indoor_values["temperature"]
            delta = indoor_temp - outdoor.temperature
            assessment = "Controlled" if abs(delta) > 2 else "Similar"
            result += f"| Temperature | {indoor_temp}°C | {outdoor.temperature}°C | {delta:+.1f}°C | {assessment} |\n"

        # Humidity
        if "humidity" in indoor_values and outdoor.humidity:
            indoor_hum, unit = indoor_values["humidity"]
            delta = indoor_hum - outdoor.humidity
            assessment = "Controlled" if abs(delta) > 10 else "Similar"
            result += f"| Humidity | {indoor_hum}% | {outdoor.humidity}% | {delta:+.1f}% | {assessment} |\n"

        # PM2.5
        if "pm25" in indoor_values and outdoor.pm25:
            indoor_pm, unit = indoor_values["pm25"]
            delta = indoor_pm - outdoor.pm25
            if outdoor.pm25 > 0:
                reduction = ((outdoor.pm25 - indoor_pm) / outdoor.pm25) * 100
                assessment = f"{reduction:.0f}% reduction" if reduction > 0 else "Higher indoors"
            else:
                assessment = "N/A"
            result += f"| PM2.5 | {indoor_pm} µg/m³ | {outdoor.pm25} µg/m³ | {delta:+.1f} | {assessment} |\n"

        # PM10
        if "pm10" in indoor_values and outdoor.pm10:
            indoor_pm, unit = indoor_values["pm10"]
            delta = indoor_pm - outdoor.pm10
            if outdoor.pm10 > 0:
                reduction = ((outdoor.pm10 - indoor_pm) / outdoor.pm10) * 100
                assessment = f"{reduction:.0f}% reduction" if reduction > 0 else "Higher indoors"
            else:
                assessment = "N/A"
            result += f"| PM10 | {indoor_pm} µg/m³ | {outdoor.pm10} µg/m³ | {delta:+.1f} | {assessment} |\n"

        result += "\n*Note: Outdoor data is for context only and is NOT used for WELL indoor scoring.*\n"

        return result
