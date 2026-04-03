"""HuggingFace Inference Endpoint client for CO2 forecasting via Chronos-2."""

import json
import os
import httpx
from typing import Optional

from src.utils.retry import retry_with_backoff, RetryConfig
from src.utils.cache import AsyncTTLCache


class ForecastingAPIError(Exception):
    """Exception raised when the forecasting endpoint call fails."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


FORECAST_TTL = 600  # 10 min — matches MICA sampling interval


HORIZON_STEPS = {
    "10min": 1,
    "1h": 6,
    "2h": 12,
    "4h": 24,
}

QUANTILE_LEVELS = [0.1, 0.5, 0.9]

CONTEXT_LENGTH = 144  # 24h at 10-min intervals (paper's validated window)


class ForecastingClient:
    """Client for a HuggingFace Inference Endpoint running Chronos-2-small."""

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 60.0,
        retry_config: Optional[RetryConfig] = None,
        cache: Optional[AsyncTTLCache] = None,
    ):
        self.endpoint_url = (
            endpoint_url
            or os.environ.get("HF_ENDPOINT_URL")
        )
        self.api_key = api_key or os.environ.get("HF_API_KEY")
        self.timeout = timeout
        self.retry_config = retry_config or RetryConfig(max_attempts=2, initial_delay=2.0)
        self.cache = cache or AsyncTTLCache()

        if not self.endpoint_url:
            raise ForecastingAPIError(
                "HuggingFace endpoint URL not provided. "
                "Set HF_ENDPOINT_URL environment variable or add "
                "huggingface_endpoint_url to inbiot-config.yaml."
            )

        self._is_gradio_space = ".hf.space" in self.endpoint_url

        # Normalize base URL (strip any trailing path for Gradio Spaces)
        if self._is_gradio_space:
            base = self.endpoint_url.rstrip("/")
            for suffix in ("/api/predict", "/gradio_api/call/predict"):
                if base.endswith(suffix):
                    base = base[: -len(suffix)]
            self._gradio_base = base
            self.endpoint_url = base + "/gradio_api/call/predict"
        else:
            self._gradio_base = None

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            limits=httpx.Limits(max_connections=5),
            headers=headers,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def forecast(
        self,
        co2_values: list[float],
        horizon: str = "2h",
    ) -> dict:
        """
        Send CO2 time series to the endpoint and return quantile predictions.

        Args:
            co2_values: Historical CO2 readings (10-min intervals, most recent last).
                        Truncated/padded to CONTEXT_LENGTH automatically.
            horizon: Prediction horizon — "10min", "1h", "2h", or "4h".

        Returns:
            Dict with quantile forecasts and metadata.
        """
        if horizon not in HORIZON_STEPS:
            raise ForecastingAPIError(
                f"Invalid horizon '{horizon}'. Use one of: {list(HORIZON_STEPS.keys())}"
            )

        prediction_length = HORIZON_STEPS[horizon]

        context = co2_values[-CONTEXT_LENGTH:]

        cache_key = (
            f"forecast:{hash(tuple(context[-12:]))}:"
            f"{prediction_length}"
        )
        cached = await self.cache.get(cache_key)
        if cached is not None:
            return cached

        inner_payload = {
            "inputs": context,
            "parameters": {
                "prediction_length": prediction_length,
                "quantile_levels": QUANTILE_LEVELS,
            },
        }

        if self._is_gradio_space:
            payload = {"data": [json.dumps(inner_payload)]}
        else:
            payload = inner_payload

        if self._is_gradio_space:
            result = await self._make_gradio_request(payload)
        else:
            result = await self._make_request(payload)

        quantiles = self._parse_response(result, prediction_length)

        await self.cache.set(cache_key, quantiles, FORECAST_TTL)
        return quantiles

    async def _make_gradio_request(self, payload: dict) -> dict:
        """Two-step Gradio 5 API: submit job, then poll SSE for result."""
        try:
            submit_resp = await self._client.post(self.endpoint_url, json=payload)
            if submit_resp.status_code != 200:
                raise ForecastingAPIError(
                    f"Gradio submit failed: {submit_resp.status_code}",
                    status_code=submit_resp.status_code,
                )
            event_id = submit_resp.json().get("event_id")
            if not event_id:
                raise ForecastingAPIError("Gradio submit returned no event_id")

            result_url = f"{self._gradio_base}/gradio_api/call/predict/{event_id}"
            result_resp = await self._client.get(result_url)

            for line in result_resp.text.strip().split("\n"):
                if line.startswith("data:"):
                    data = json.loads(line[5:].strip())
                    if isinstance(data, list) and data:
                        inner = data[0]
                        if isinstance(inner, str):
                            return json.loads(inner)
                        if isinstance(inner, dict):
                            return inner

            raise ForecastingAPIError(
                f"Could not parse Gradio SSE response: {result_resp.text[:200]}"
            )
        except httpx.TimeoutException:
            raise ForecastingAPIError("Gradio request timed out.")
        except httpx.RequestError as e:
            raise ForecastingAPIError(f"Gradio request failed: {str(e)}")

    def _parse_response(self, raw: dict, prediction_length: int) -> dict:
        """
        Normalize the endpoint response into a consistent format.

        Handles both HF Inference API format and custom handler formats.
        """
        if "quantiles" in raw:
            return raw

        if isinstance(raw, list) and len(raw) > 0:
            if isinstance(raw[0], dict) and "quantile" in raw[0]:
                quantiles = {}
                for entry in raw:
                    q = str(entry["quantile"])
                    quantiles[q] = entry["values"]
                return {"quantiles": quantiles}

            if isinstance(raw[0], list):
                median = raw[len(raw) // 2] if len(raw) > 1 else raw[0]
                return {
                    "quantiles": {
                        "0.5": median[:prediction_length],
                    }
                }

        if isinstance(raw, dict):
            for key in ("predictions", "forecast", "output"):
                if key in raw:
                    values = raw[key]
                    if isinstance(values, list):
                        return {
                            "quantiles": {
                                "0.5": values[:prediction_length],
                            }
                        }

        raise ForecastingAPIError(
            f"Unexpected response format from forecasting endpoint. "
            f"Keys: {list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__}"
        )

    async def _make_request(self, payload: dict) -> dict:
        """POST to the HF endpoint with retry logic."""

        @retry_with_backoff(config=self.retry_config)
        async def _request():
            try:
                response = await self._client.post(self.endpoint_url, json=payload)

                if response.status_code == 401:
                    raise ForecastingAPIError(
                        "Invalid HuggingFace API key.",
                        status_code=401,
                    )
                elif response.status_code == 503:
                    raise ForecastingAPIError(
                        "Forecasting endpoint is loading or unavailable. "
                        "HF Inference Endpoints may take a few minutes to warm up.",
                        status_code=503,
                    )
                elif response.status_code == 429:
                    response.raise_for_status()
                elif response.status_code >= 500:
                    response.raise_for_status()
                elif response.status_code != 200:
                    raise ForecastingAPIError(
                        f"Unexpected response: {response.status_code}",
                        status_code=response.status_code,
                    )

                return response.json()

            except httpx.TimeoutException:
                raise ForecastingAPIError(
                    "Forecasting request timed out. "
                    "Model inference may be slow on first call."
                )
            except httpx.RequestError as e:
                raise ForecastingAPIError(f"Request failed: {str(e)}")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    raise ForecastingAPIError(
                        "Forecasting endpoint rate limit exceeded.",
                        status_code=429,
                    )
                raise ForecastingAPIError(
                    f"Server error: {e.response.status_code}",
                    status_code=e.response.status_code,
                )

        return await _request()

    @property
    def endpoint_info(self) -> str:
        """Return the endpoint URL for provenance tracking."""
        return self.endpoint_url
