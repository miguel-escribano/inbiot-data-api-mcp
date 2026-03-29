"""Parameter name normalization for InBiot sensor data."""

PARAMETER_ALIASES = {
    "pm2.5": "pm25",
    "pm2_5": "pm25",
    "pm_25": "pm25",
    "pm_10": "pm10",
    "pm_4": "pm4",
    "pm_1": "pm1",
    "tvoc": "vocs",
    "tvocs": "vocs",
    "hcho": "formaldehyde",
    "temp": "temperature",
    "rh": "humidity",
    "relative_humidity": "humidity",
}


def normalize_parameter_name(name: str) -> str:
    """Normalize parameter name to standard form."""
    normalized = name.lower().strip()
    return PARAMETER_ALIASES.get(normalized, normalized)
