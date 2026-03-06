"""Tests for API clients."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from src.api.inbiot import InBiotClient, InBiotAPIError
from src.api.openweather import OpenWeatherClient, OpenWeatherAPIError
from src.models.schemas import DeviceConfig


@pytest.fixture
def device_config():
    """Create a test device configuration."""
    return DeviceConfig(
        name="Test Device",
        api_key="test-api-key",
        system_id="test-system-id",
        coordinates=(42.0, -1.6),
    )


@pytest.fixture
def mock_inbiot_response():
    """Mock InBiot API response."""
    return [
        {
            "_id": "temp_001",
            "type": "temperature",
            "unit": "°C",
            "measurements": [
                {"_id": "m1", "value": "22.5", "date": 1702000000000}
            ],
        },
        {
            "_id": "co2_001",
            "type": "co2",
            "unit": "ppm",
            "measurements": [
                {"_id": "m2", "value": "650", "date": 1702000000000}
            ],
        },
    ]


class TestInBiotClient:
    """Tests for InBiot API client."""

    @pytest.mark.asyncio
    async def test_get_latest_measurements_success(
        self, device_config, mock_inbiot_response
    ):
        """Test successful API call."""
        client = InBiotClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_inbiot_response

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            data = await client.get_latest_measurements(device_config)

            assert len(data) == 2
            assert data[0].type == "temperature"
            assert data[0].latest_value == 22.5
            assert data[1].type == "co2"
            assert data[1].latest_value == 650

    @pytest.mark.asyncio
    async def test_get_latest_measurements_not_found(self, device_config):
        """Test 404 response handling."""
        client = InBiotClient()

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(InBiotAPIError) as exc_info:
                await client.get_latest_measurements(device_config)

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_get_latest_measurements_rate_limited(self, device_config):
        """Test 429 response handling."""
        client = InBiotClient()

        mock_response = MagicMock()
        mock_response.status_code = 429

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(InBiotAPIError) as exc_info:
                await client.get_latest_measurements(device_config)

            assert exc_info.value.status_code == 429
            assert "rate limit" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_get_latest_measurements_timeout(self, device_config):
        """Test timeout handling."""
        client = InBiotClient()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.TimeoutException("Connection timed out")
            )

            with pytest.raises(InBiotAPIError) as exc_info:
                await client.get_latest_measurements(device_config)

            assert "timed out" in exc_info.value.message.lower()


class TestOpenWeatherClient:
    """Tests for OpenWeather API client."""

    def test_init_without_api_key(self):
        """Test initialization without API key raises error."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(OpenWeatherAPIError) as exc_info:
                OpenWeatherClient(api_key=None)

            assert "API key" in exc_info.value.message

    def test_init_with_api_key(self):
        """Test initialization with API key."""
        client = OpenWeatherClient(api_key="test-key")
        assert client.api_key == "test-key"

    @pytest.mark.asyncio
    async def test_get_outdoor_conditions_success(self):
        """Test successful outdoor conditions retrieval."""
        client = OpenWeatherClient(api_key="test-key")

        mock_weather = {
            "main": {"temp": 15.5, "humidity": 60, "pressure": 1013},
            "wind": {"speed": 5.0, "deg": 180},
            "weather": [{"description": "clear sky"}],
        }

        mock_air = {
            "list": [
                {
                    "main": {"aqi": 2},
                    "components": {
                        "pm2_5": 10.0,
                        "pm10": 20.0,
                        "o3": 50.0,
                        "no2": 15.0,
                        "so2": 5.0,
                        "co": 200.0,
                    },
                }
            ]
        }

        with patch.object(client, "_make_request") as mock_request:
            mock_request.side_effect = [mock_weather, mock_air]

            conditions = await client.get_outdoor_conditions(42.0, -1.6, "Test Location")

            assert conditions.temperature == 15.5
            assert conditions.humidity == 60
            assert conditions.aqi == 2
            assert conditions.pm25 == 10.0
            assert conditions.location == "Test Location"

