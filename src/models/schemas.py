"""Pydantic models for data validation and serialization."""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class DeviceConfig(BaseModel):
    """Configuration for an InBiot device."""

    name: str
    api_key: str
    system_id: str
    coordinates: tuple[float, float]


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


class ParameterAssessment(BaseModel):
    """Assessment of a single parameter against WELL standards."""

    parameter: str
    value: float
    unit: str
    score: int  # 0-4 scale
    level: str  # "Excellent", "Good", "Acceptable", "Poor", "Very Poor"
    well_compliant: bool
    threshold_used: str  # Which standard was applied


class WELLAssessment(BaseModel):
    """Complete WELL Building Standard compliance assessment."""

    device_name: str
    timestamp: datetime
    overall_score: int
    max_score: int
    percentage: float
    well_level: str  # "Platinum", "Gold", "Silver", "Bronze", "Below Standards"
    parameters: list[ParameterAssessment]
    recommendations: list[str] = []


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
    so2: Optional[float] = None
    co: Optional[float] = None


class IndoorOutdoorComparison(BaseModel):
    """Comparison between indoor and outdoor conditions."""

    device_name: str
    timestamp: datetime
    indoor: dict[str, float]
    outdoor: dict[str, float]
    deltas: dict[str, float]  # Indoor - Outdoor differences
    filtration_effectiveness: dict[str, str]  # Assessment per parameter

