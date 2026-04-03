"""Parameter name normalization and unit metadata for InBiot sensor data."""

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

TVOC_ETHANOL_TO_MOLHAVE = 2.61
TVOC_PARAMETER_NAMES = {"vocs", "tvoc", "tvocs"}


def normalize_parameter_name(name: str) -> str:
    """Normalize parameter name to standard form."""
    normalized = name.lower().strip()
    return PARAMETER_ALIASES.get(normalized, normalized)


def enrich_measurement(param_type: str, value: float, unit: str) -> dict:
    """Build a measurement dict, adding conversion metadata for TVOC.

    TVOC from InBiot sensors is ethanol-calibrated ppb. Standards (WELL,
    WHO, ASHRAE) use Molhave µg/m³. This adds the converted value so
    consumers don't need to know the factor.
    """
    entry: dict = {"parameter": param_type, "value": value, "unit": unit}
    if param_type.lower() in TVOC_PARAMETER_NAMES and "ppb" in unit.lower():
        entry["well_value"] = round(value * TVOC_ETHANOL_TO_MOLHAVE, 1)
        entry["well_unit"] = "µg/m³ (Molhave)"
        entry["reference_gas"] = "ethanol"
        entry["conversion_factor"] = TVOC_ETHANOL_TO_MOLHAVE
    return entry
