"""WELL Building Standard thresholds and criteria.

This module defines thresholds from:
- WELL Building Standard v2 (Features A01-A08, T01-T07)
- ASHRAE 62.1 & 55 (ventilation & thermal comfort)
- WHO Indoor Air Quality Guidelines (2010 + 2021)

When multiple limits exist, the strictest value governs compliance.
"""

from typing import Optional

# WELL Building Standard thresholds
# For pollutants: lower is better (excellent < good < acceptable < poor)
# For indicators: higher is better (excellent > good > acceptable > poor)
WELL_THRESHOLDS = {
    # Particulate Matter (µg/m³)
    "pm25": {
        "excellent": 8,  # WELL annual target
        "good": 15,  # WELL 24h / WHO Indoor
        "acceptable": 25,
        "poor": 35,
        "unit": "µg/m³",
        "feature": "A01 - Fine Particulates",
        "feature_id": "A01",
    },
    "pm10": {
        "excellent": 20,  # WELL annual target
        "good": 45,  # WELL 24h / WHO Indoor
        "acceptable": 50,
        "poor": 150,
        "unit": "µg/m³",
        "feature": "A01 - Coarse Particles",
        "feature_id": "A01",
    },
    "pm4": {
        "excellent": 10,
        "good": 20,
        "acceptable": 30,
        "poor": 50,
        "unit": "µg/m³",
        "feature": "A01 - Particulates",
        "feature_id": "A01",
    },
    "pm1": {
        "excellent": 5,
        "good": 15,
        "acceptable": 25,
        "poor": 40,
        "unit": "µg/m³",
        "feature": "A01 - Ultrafine Particulates",
        "feature_id": "A01",
    },
    # Gases
    "co2": {
        "excellent": 600,
        "good": 800,  # WELL v2 limit
        "acceptable": 1000,  # ASHRAE 62.1
        "poor": 1500,
        "unit": "ppm",
        "feature": "A03 - Ventilation Effectiveness",
        "feature_id": "A03",
    },
    "co": {
        "excellent": 7,  # WHO Indoor 24h
        "good": 9,  # WELL 8h
        "acceptable": 30,
        "poor": 87,
        "unit": "ppm",
        "feature": "A06 - Combustion Control",
        "feature_id": "A06",
    },
    "no2": {
        "excellent": 21,
        "good": 40,  # WELL annual
        "acceptable": 100,
        "poor": 200,
        "unit": "ppb",
        "feature": "A05 - Combustion Sources",
        "feature_id": "A06",
    },
    "o3": {
        "excellent": 51,
        "good": 70,
        "acceptable": 100,  # WHO Indoor 8h
        "poor": 240,
        "unit": "ppb",
        "feature": "A05 - Ozone Control",
        "feature_id": "A05",
    },
    # VOCs and Formaldehyde
    "formaldehyde": {
        "excellent": 9,  # WELL v2
        "good": 16,
        "acceptable": 30,
        "poor": 100,  # WHO Indoor 30min
        "unit": "µg/m³",
        "feature": "A05 - Enhanced Air Quality",
        "feature_id": "A05",
    },
    "vocs": {
        "excellent": 200,
        "good": 300,  # WHO recommended
        "acceptable": 500,  # WELL v2
        "poor": 1000,
        "unit": "ppb",
        "feature": "A05 - Volatile Organics",
        "feature_id": "A05",
    },
    # Thermal Comfort (range-based)
    "temperature": {
        "optimal_min": 20,
        "optimal_max": 24,  # Winter range
        "acceptable_min": 18,
        "acceptable_max": 26,  # ASHRAE 55 operative range
        "unit": "°C",
        "feature": "T01/T06 - Thermal Performance",
        "feature_id": "T01",
    },
    "humidity": {
        "optimal_min": 30,
        "optimal_max": 60,  # WELL/ASHRAE 55
        "acceptable_min": 20,
        "acceptable_max": 70,
        "unit": "%",
        "feature": "T07 - Humidity Control",
        "feature_id": "T07",
    },
    # InBiot Composite Indicators (0-100 scale, higher is better)
    "iaq": {
        "excellent": 80,
        "good": 60,
        "acceptable": 40,
        "poor": 20,
        "unit": "index",
        "feature": "A08 - Air Quality Monitoring",
        "feature_id": "A08",
        "higher_is_better": True,
    },
    "covid19": {
        "excellent": 80,
        "good": 60,
        "acceptable": 40,
        "poor": 20,
        "unit": "index",
        "feature": "A08 - Virus Resistance",
        "feature_id": "A08",
        "higher_is_better": True,
    },
    "thermalindicator": {
        "excellent": 80,
        "good": 60,
        "acceptable": 40,
        "poor": 20,
        "unit": "index",
        "feature": "T01 - Thermal Comfort",
        "feature_id": "T01",
        "higher_is_better": True,
    },
    "ventilationindicator": {
        "excellent": 80,
        "good": 60,
        "acceptable": 40,
        "poor": 20,
        "unit": "index",
        "feature": "A03 - Ventilation Efficiency",
        "feature_id": "A03",
        "higher_is_better": True,
    },
}

# Parameter name normalization mapping
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


def get_threshold_for_parameter(parameter: str) -> Optional[dict]:
    """
    Get threshold configuration for a parameter.

    Args:
        parameter: Parameter name (will be normalized)

    Returns:
        Threshold configuration dict or None if not found
    """
    normalized = normalize_parameter_name(parameter)
    return WELL_THRESHOLDS.get(normalized)


def is_higher_better(parameter: str) -> bool:
    """Check if higher values are better for this parameter."""
    threshold = get_threshold_for_parameter(parameter)
    if threshold:
        return threshold.get("higher_is_better", False)
    return False


def is_range_based(parameter: str) -> bool:
    """Check if this parameter uses range-based thresholds."""
    threshold = get_threshold_for_parameter(parameter)
    if threshold:
        return "optimal_min" in threshold
    return False

