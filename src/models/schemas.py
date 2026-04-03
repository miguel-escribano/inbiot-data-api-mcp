"""Pydantic models for data validation and serialization."""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class DeviceConfig(BaseModel):
    """Configuration for an InBiot device."""

    name: str
    api_key: str
    system_id: str
    coordinates: tuple[float, float]
    building: Optional[str] = None


class Measurement(BaseModel):
    """A single measurement from a sensor."""

    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(default=None, alias="_id")
    value: float | str  # Accept both float and string
    date: float  # Unix timestamp in milliseconds

    @property
    def timestamp(self) -> datetime:
        """Convert Unix timestamp (ms) to datetime."""
        return datetime.fromtimestamp(self.date / 1000, tz=timezone.utc)

    @property
    def numeric_value(self) -> float:
        """Get the measurement value as a float."""
        if isinstance(self.value, (int, float)):
            return float(self.value)
        return float(self.value)


class ParameterData(BaseModel):
    """Data for a single parameter (e.g., temperature, CO2)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | int = Field(alias="_id")  # Accept both string and int
    type: str
    unit: str
    measurements: list[Measurement] = []

    @property
    def latest_value(self) -> Optional[float]:
        """Get the most recent measurement value."""
        if not self.measurements:
            return None
        return self.measurements[-1].numeric_value

    @property
    def latest_timestamp(self) -> Optional[datetime]:
        """Get the timestamp of the most recent measurement."""
        if not self.measurements:
            return None
        return self.measurements[-1].timestamp


class OutdoorConditions(BaseModel):
    """Outdoor weather and air quality conditions."""

    timestamp: datetime
    location: str
    coordinates: tuple[float, float]

    # Weather
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    wind_speed: Optional[float] = None
    wind_direction: Optional[float] = None
    uv_index: Optional[float] = None
    description: Optional[str] = None

    # Air Quality
    aqi: Optional[int] = None  # 1-5 scale
    pm25: Optional[float] = None
    pm10: Optional[float] = None
    o3: Optional[float] = None
    no2: Optional[float] = None
    no: Optional[float] = None
    so2: Optional[float] = None
    co: Optional[float] = None
    nh3: Optional[float] = None


class IndoorOutdoorComparison(BaseModel):
    """Comparison between indoor and outdoor conditions."""

    device_name: str
    timestamp: datetime
    indoor: dict[str, float]
    outdoor: dict[str, float]
    deltas: dict[str, float]  # Indoor - Outdoor differences
    filtration_effectiveness: dict[str, str]  # Assessment per parameter


class ThresholdCrossing(BaseModel):
    """Predicted time when a threshold will be crossed."""

    threshold_ppm: int
    minutes_until: Optional[int] = None
    predicted_value: Optional[float] = None
    confidence: str = "median"


class CO2Forecast(BaseModel):
    """Structured CO2 forecast result."""

    device_name: str
    horizon: str
    steps: int
    interval_minutes: int = 10
    current_co2: Optional[float] = None
    current_timestamp: Optional[str] = None
    median: list[float] = Field(default_factory=list)
    lower_bound: list[float] = Field(default_factory=list)
    upper_bound: list[float] = Field(default_factory=list)
    threshold_crossings: list[ThresholdCrossing] = Field(default_factory=list)
    context_points_used: int = 0
    model: str = "chronos-2-small"

