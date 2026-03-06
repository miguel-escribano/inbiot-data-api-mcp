"""WELL Building Standard v2 Feature Definitions and Mappings."""

from typing import Dict, List
from pydantic import BaseModel


class WELLFeature(BaseModel):
    """WELL Building Standard v2 Feature Definition."""

    id: str  # e.g., "A01"
    name: str
    category: str  # "Air" or "Thermal"
    description: str
    parameters: List[str]  # Parameter types mapped to this feature
    minimum_score: int  # Minimum score for compliance (typically 2)
    health_impact: str
    mitigation_strategies: List[str]


# WELL v2 Feature Registry
WELL_FEATURES: Dict[str, WELLFeature] = {
    "A01": WELLFeature(
        id="A01",
        name="Fine Particulates",
        category="Air",
        description="Filtration and source control of particulate matter",
        parameters=["pm25", "pm10", "pm4", "pm1"],
        minimum_score=2,
        health_impact="Respiratory health, cardiovascular effects, premature mortality",
        mitigation_strategies=[
            "Install MERV 13+ or HEPA filtration systems",
            "Seal building envelope to reduce outdoor infiltration",
            "Control indoor emission sources (cooking, combustion)",
            "Monitor outdoor conditions and adjust fresh air intake accordingly",
            "Implement regular filter maintenance schedule",
        ],
    ),
    "A03": WELLFeature(
        id="A03",
        name="Ventilation Effectiveness",
        category="Air",
        description="Adequate outdoor air ventilation to dilute indoor pollutants",
        parameters=["co2", "ventilation_indicator"],
        minimum_score=2,
        health_impact="Cognitive performance, reduced sick building syndrome symptoms",
        mitigation_strategies=[
            "Increase outdoor air intake rate to meet ASHRAE 62.1 standards",
            "Verify HVAC system operation and damper positions",
            "Implement demand-controlled ventilation (DCV) systems",
            "Check and replace air filters regularly",
            "Verify occupancy levels match design capacity",
        ],
    ),
    "A05": WELLFeature(
        id="A05",
        name="Enhanced Air Quality",
        category="Air",
        description="Control of VOCs, formaldehyde, and ozone",
        parameters=["vocs", "formaldehyde", "o3"],
        minimum_score=2,
        health_impact="Respiratory irritation, carcinogenic risk (formaldehyde), eye and throat irritation",
        mitigation_strategies=[
            "Use low-VOC materials and furnishings",
            "Ensure adequate ventilation during and after renovations",
            "Monitor outdoor ozone levels and adjust ventilation",
            "Activate carbon filtration for VOC removal",
            "Implement source control measures for formaldehyde emissions",
        ],
    ),
    "A06": WELLFeature(
        id="A06",
        name="Combustion Minimization",
        category="Air",
        description="Control of combustion-generated pollutants",
        parameters=["co", "no2"],
        minimum_score=2,
        health_impact="Carbon monoxide poisoning, respiratory irritation, cardiovascular effects",
        mitigation_strategies=[
            "Eliminate indoor combustion sources where possible",
            "Inspect and maintain combustion appliances regularly",
            "Verify proper venting of combustion equipment",
            "Install CO detectors and alarms in appropriate locations",
            "Ensure adequate ventilation in areas with combustion equipment",
        ],
    ),
    "A08": WELLFeature(
        id="A08",
        name="Air Quality Monitoring",
        category="Air",
        description="Continuous monitoring of indoor air quality parameters",
        parameters=["iaq_indicator"],
        minimum_score=2,
        health_impact="Awareness and responsive management of air quality conditions",
        mitigation_strategies=[
            "Maintain continuous monitoring systems",
            "Display air quality data to occupants in real-time",
            "Implement automated responses to poor air quality conditions",
            "Establish protocols for addressing air quality issues",
        ],
    ),
    "T01": WELLFeature(
        id="T01",
        name="Thermal Performance",
        category="Thermal",
        description="Maintenance of comfortable temperature ranges",
        parameters=["temperature", "thermal_indicator"],
        minimum_score=2,
        health_impact="Occupant comfort, productivity, thermal stress prevention",
        mitigation_strategies=[
            "Adjust HVAC temperature setpoints to meet ASHRAE 55 standards",
            "Verify proper operation of heating/cooling equipment",
            "Address thermal bridging and insulation issues",
            "Provide local temperature control where possible",
            "Consider seasonal adjustments to temperature ranges",
        ],
    ),
    "T06": WELLFeature(
        id="T06",
        name="Adaptive Thermal Comfort",
        category="Thermal",
        description="Temperature and humidity control for occupant comfort",
        parameters=["temperature", "humidity"],
        minimum_score=2,
        health_impact="Occupant satisfaction, productivity, thermal comfort",
        mitigation_strategies=[
            "Adjust temperature based on occupant feedback",
            "Provide seasonal temperature adjustments",
            "Enable occupant control of local thermal conditions",
            "Consider clothing and metabolic rate in temperature settings",
        ],
    ),
    "T07": WELLFeature(
        id="T07",
        name="Humidity Control",
        category="Thermal",
        description="Maintenance of appropriate humidity levels (30-60% RH)",
        parameters=["humidity"],
        minimum_score=2,
        health_impact="Mold prevention, respiratory comfort, viral transmission reduction",
        mitigation_strategies=[
            "Activate humidification system if relative humidity < 30%",
            "Activate dehumidification system if relative humidity > 60%",
            "Check for water intrusion or leaks",
            "Verify HVAC humidity control operation",
            "Monitor seasonal humidity variations",
        ],
    ),
}


def get_feature_for_parameter(param: str) -> List[str]:
    """
    Get all WELL features that include this parameter.

    Args:
        param: Parameter name (e.g., "pm25", "temperature")

    Returns:
        List of WELL feature IDs that track this parameter
    """
    return [
        feature.id for feature in WELL_FEATURES.values() if param in feature.parameters
    ]


def get_feature_by_id(feature_id: str) -> WELLFeature:
    """
    Get WELL feature definition by ID.

    Args:
        feature_id: Feature ID (e.g., "A01")

    Returns:
        WELLFeature object or None if not found
    """
    return WELL_FEATURES.get(feature_id)
