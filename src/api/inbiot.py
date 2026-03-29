"""InBiot API client for fetching air quality measurements."""

import httpx
from typing import Optional
from datetime import datetime

from src.models.schemas import ParameterData, DeviceConfig
from src.utils.retry import retry_with_backoff, RetryConfig
from src.utils.cache import AsyncTTLCache


class InBiotAPIError(Exception):
    """Exception raised when InBiot API call fails."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


# TTL constants (seconds)
LATEST_TTL = 600  # 10 min for latest measurements
HISTORICAL_TTL = 3600  # 60 min for historical data


class InBiotClient:
    """Client for the InBiot Public API."""

    BASE_URL = "https://myinbiotpublicapi.com"

    def __init__(
        self,
        timeout: float = 30.0,
        retry_config: Optional[RetryConfig] = None,
        cache: Optional[AsyncTTLCache] = None,
    ):
        self.timeout = timeout
        self.retry_config = retry_config or RetryConfig()
        self.cache = cache or AsyncTTLCache()
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            limits=httpx.Limits(max_connections=10),
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def get_latest_measurements(
        self, device: DeviceConfig
    ) -> list[ParameterData]:
        """Get the latest measurements from an InBiot device."""
        endpoint = f"/last-measurements/{device.api_key}/{device.system_id}"
        cache_key = f"inbiot:latest:{device.system_id}"
        return await self._cached_request(endpoint, cache_key, LATEST_TTL)

    async def get_historical_data(
        self,
        device: DeviceConfig,
        start_date: datetime,
        end_date: datetime,
    ) -> list[ParameterData]:
        """Get historical measurements from an InBiot device."""
        start_str = start_date.strftime("%Y-%m-%dT%H:%M:%S.000")
        end_str = end_date.strftime("%Y-%m-%dT%H:%M:%S.999")
        endpoint = f"/measurements-by-time/{device.api_key}/{device.system_id}/{start_str}/{end_str}"
        cache_key = f"inbiot:hist:{device.system_id}:{start_str}:{end_str}"
        return await self._cached_request(endpoint, cache_key, HISTORICAL_TTL)

    async def _cached_request(
        self, endpoint: str, cache_key: str, ttl: float
    ) -> list[ParameterData]:
        """Check cache, then make HTTP request if needed."""
        cached = await self.cache.get(cache_key)
        if cached is not None:
            return cached
        result = await self._make_request(endpoint)
        await self.cache.set(cache_key, result, ttl)
        return result

    async def _make_request(self, endpoint: str) -> list[ParameterData]:
        """Make an HTTP request to the InBiot API with automatic retries."""
        url = f"{self.BASE_URL}{endpoint}"

        @retry_with_backoff(config=self.retry_config)
        async def _request():
            try:
                response = await self._client.get(url)

                if response.status_code == 404:
                    raise InBiotAPIError(
                        f"Device not found. Endpoint: {endpoint}",
                        status_code=404,
                    )
                elif response.status_code == 429:
                    response.raise_for_status()
                elif response.status_code >= 500:
                    response.raise_for_status()
                elif response.status_code != 200:
                    raise InBiotAPIError(
                        f"Unexpected response: {response.status_code}. Endpoint: {endpoint}",
                        status_code=response.status_code,
                    )

                data = response.json()

                if isinstance(data, dict) and "systemData" in data:
                    data = data["systemData"]

                return [ParameterData.model_validate(item) for item in data]

            except httpx.TimeoutException:
                raise InBiotAPIError(f"Request timed out. Endpoint: {endpoint}")
            except httpx.RequestError as e:
                raise InBiotAPIError(f"Request failed: {str(e)}. Endpoint: {endpoint}")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    retry_after = e.response.headers.get("Retry-After", "unknown")
                    raise InBiotAPIError(
                        f"Rate limit exceeded (6 requests per device per hour). "
                        f"Retry after: {retry_after} seconds. Endpoint: {endpoint}",
                        status_code=429,
                    )
                else:
                    raise InBiotAPIError(
                        f"Server error: {e.response.status_code}. Endpoint: {endpoint}",
                        status_code=e.response.status_code,
                    )

        return await _request()

    @property
    def endpoint_info(self) -> str:
        """Return the base URL for provenance tracking."""
        return self.BASE_URL
