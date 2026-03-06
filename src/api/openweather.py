"""OpenWeather API client for outdoor conditions."""

import os
import httpx
from typing import Optional
from datetime import datetime, timezone

from src.models.schemas import OutdoorConditions
from src.utils.retry import retry_with_backoff, RetryConfig


class OpenWeatherAPIError(Exception):
    """Exception raised when OpenWeather API call fails."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class OpenWeatherClient:
    """Client for the OpenWeather API."""

    BASE_URL = "https://api.openweathermap.org"

    def __init__(self, api_key: Optional[str] = None, timeout: float = 30.0, retry_config: Optional[RetryConfig] = None):
        self.api_key = api_key or os.environ.get("OPENWEATHER_API_KEY")
        self.timeout = timeout
        self.retry_config = retry_config or RetryConfig()

        if not self.api_key:
            raise OpenWeatherAPIError(
                "OpenWeather API key not provided. Set OPENWEATHER_API_KEY environment variable."
            )

    async def get_outdoor_conditions(
        self, lat: float, lon: float, location_name: str = "Unknown"
    ) -> OutdoorConditions:
        """
        Get current outdoor weather and air quality.

        Args:
            lat: Latitude
            lon: Longitude
            location_name: Human-readable location name

        Returns:
            OutdoorConditions with weather and air quality data

        Raises:
            OpenWeatherAPIError: If any API call fails
        """
        weather_data = await self._get_weather(lat, lon)
        air_quality_data = await self._get_air_pollution(lat, lon)

        return OutdoorConditions(
            timestamp=datetime.now(timezone.utc),
            location=location_name,
            coordinates=(lat, lon),
            # Weather
            temperature=weather_data.get("main", {}).get("temp"),
            humidity=weather_data.get("main", {}).get("humidity"),
            pressure=weather_data.get("main", {}).get("pressure"),
            wind_speed=weather_data.get("wind", {}).get("speed"),
            wind_direction=weather_data.get("wind", {}).get("deg"),
            description=weather_data.get("weather", [{}])[0].get("description"),
            # Air Quality
            aqi=air_quality_data.get("list", [{}])[0].get("main", {}).get("aqi"),
            pm25=air_quality_data.get("list", [{}])[0]
            .get("components", {})
            .get("pm2_5"),
            pm10=air_quality_data.get("list", [{}])[0]
            .get("components", {})
            .get("pm10"),
            o3=air_quality_data.get("list", [{}])[0].get("components", {}).get("o3"),
            no2=air_quality_data.get("list", [{}])[0].get("components", {}).get("no2"),
            so2=air_quality_data.get("list", [{}])[0].get("components", {}).get("so2"),
            co=air_quality_data.get("list", [{}])[0].get("components", {}).get("co"),
        )

    async def _get_weather(self, lat: float, lon: float) -> dict:
        """Get current weather data."""
        endpoint = "/data/2.5/weather"
        params = {
            "lat": lat,
            "lon": lon,
            "units": "metric",
            "appid": self.api_key,
        }
        return await self._make_request(endpoint, params)

    async def _get_air_pollution(self, lat: float, lon: float) -> dict:
        """Get current air pollution data."""
        endpoint = "/data/2.5/air_pollution"
        params = {
            "lat": lat,
            "lon": lon,
            "appid": self.api_key,
        }
        return await self._make_request(endpoint, params)

    async def _make_request(self, endpoint: str, params: dict) -> dict:
        """
        Make an HTTP request to the OpenWeather API with automatic retries.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            JSON response data

        Raises:
            OpenWeatherAPIError: If the request fails after all retries
        """
        url = f"{self.BASE_URL}{endpoint}"

        @retry_with_backoff(config=self.retry_config)
        async def _request():
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                try:
                    response = await client.get(url, params=params)

                    if response.status_code == 401:
                        raise OpenWeatherAPIError(
                            f"Invalid OpenWeather API key. Endpoint: {endpoint}",
                            status_code=401,
                        )
                    elif response.status_code == 429:
                        retry_after = response.headers.get("Retry-After", "unknown")
                        # Raise HTTPStatusError so retry logic can handle it
                        response.raise_for_status()
                    elif response.status_code >= 500:
                        # Raise HTTPStatusError for retryable server errors
                        response.raise_for_status()
                    elif response.status_code != 200:
                        raise OpenWeatherAPIError(
                            f"Unexpected response: {response.status_code}. Endpoint: {endpoint}",
                            status_code=response.status_code,
                        )

                    return response.json()

                except httpx.TimeoutException:
                    raise OpenWeatherAPIError(f"Request timed out. Endpoint: {endpoint}")
                except httpx.RequestError as e:
                    raise OpenWeatherAPIError(f"Request failed: {str(e)}. Endpoint: {endpoint}")
                except httpx.HTTPStatusError as e:
                    # Convert HTTPStatusError to OpenWeatherAPIError with context
                    if e.response.status_code == 429:
                        retry_after = e.response.headers.get("Retry-After", "unknown")
                        raise OpenWeatherAPIError(
                            f"Rate limit exceeded. Retry after: {retry_after} seconds. Endpoint: {endpoint}",
                            status_code=429,
                        )
                    else:
                        raise OpenWeatherAPIError(
                            f"Server error: {e.response.status_code}. Endpoint: {endpoint}",
                            status_code=e.response.status_code,
                        )

        return await _request()

    @property
    def endpoint_info(self) -> str:
        """Return the base URL for provenance tracking."""
        return self.BASE_URL

