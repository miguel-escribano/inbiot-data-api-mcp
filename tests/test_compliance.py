"""Tests for WELL compliance engine."""

import pytest
from datetime import datetime

from src.well.compliance import WELLComplianceEngine
from src.well.thresholds import (
    get_threshold_for_parameter,
    normalize_parameter_name,
    is_higher_better,
    is_range_based,
)
from src.models.schemas import ParameterData, Measurement


@pytest.fixture
def compliance_engine():
    """Create a WELL compliance engine instance."""
    return WELLComplianceEngine()


@pytest.fixture
def sample_parameters():
    """Create sample parameter data for testing."""
    return [
        ParameterData(
            _id="temp_001",
            type="temperature",
            unit="°C",
            measurements=[
                Measurement(_id="m1", value="22", date=1702000000000)
            ],
        ),
        ParameterData(
            _id="hum_001",
            type="humidity",
            unit="%",
            measurements=[
                Measurement(_id="m2", value="45", date=1702000000000)
            ],
        ),
        ParameterData(
            _id="co2_001",
            type="co2",
            unit="ppm",
            measurements=[
                Measurement(_id="m3", value="600", date=1702000000000)
            ],
        ),
        ParameterData(
            _id="pm25_001",
            type="pm25",
            unit="µg/m³",
            measurements=[
                Measurement(_id="m4", value="8", date=1702000000000)
            ],
        ),
    ]


class TestThresholds:
    """Tests for threshold utilities."""

    def test_normalize_parameter_name(self):
        """Test parameter name normalization."""
        assert normalize_parameter_name("PM2.5") == "pm25"
        assert normalize_parameter_name("PM_25") == "pm25"
        assert normalize_parameter_name("TVOC") == "vocs"
        assert normalize_parameter_name("HCHO") == "formaldehyde"
        assert normalize_parameter_name("temp") == "temperature"
        assert normalize_parameter_name("RH") == "humidity"

    def test_get_threshold_for_parameter(self):
        """Test threshold retrieval."""
        co2_threshold = get_threshold_for_parameter("co2")
        assert co2_threshold is not None
        assert co2_threshold["excellent"] == 600
        assert co2_threshold["good"] == 800

        pm25_threshold = get_threshold_for_parameter("pm25")
        assert pm25_threshold is not None
        assert pm25_threshold["excellent"] == 8

    def test_get_threshold_unknown_parameter(self):
        """Test threshold retrieval for unknown parameter."""
        threshold = get_threshold_for_parameter("unknown_param")
        assert threshold is None

    def test_is_higher_better(self):
        """Test higher_is_better detection."""
        assert is_higher_better("iaq") is True
        assert is_higher_better("covid19") is True
        assert is_higher_better("co2") is False
        assert is_higher_better("pm25") is False

    def test_is_range_based(self):
        """Test range-based parameter detection."""
        assert is_range_based("temperature") is True
        assert is_range_based("humidity") is True
        assert is_range_based("co2") is False
        assert is_range_based("pm25") is False


class TestWELLComplianceEngine:
    """Tests for WELL compliance assessment."""

    def test_assess_excellent_conditions(self, compliance_engine, sample_parameters):
        """Test assessment with excellent conditions."""
        assessment = compliance_engine.assess("Test Device", sample_parameters)

        assert assessment.device_name == "Test Device"
        assert assessment.overall_score > 0
        assert assessment.max_score > 0
        assert assessment.percentage > 0
        assert len(assessment.parameters) > 0

    def test_assess_well_level_determination(self, compliance_engine):
        """Test WELL level determination based on percentage."""
        # Test with excellent CO2 (600 ppm = excellent)
        params = [
            ParameterData(
                _id="co2_001",
                type="co2",
                unit="ppm",
                measurements=[
                    Measurement(_id="m1", value="600", date=1702000000000)
                ],
            ),
        ]

        assessment = compliance_engine.assess("Test Device", params)
        # 600 ppm CO2 should score 4/4 = 100% = Platinum
        assert "Platinum" in assessment.well_level

    def test_assess_poor_conditions(self, compliance_engine):
        """Test assessment with poor conditions."""
        params = [
            ParameterData(
                _id="co2_001",
                type="co2",
                unit="ppm",
                measurements=[
                    Measurement(_id="m1", value="2000", date=1702000000000)
                ],
            ),
        ]

        assessment = compliance_engine.assess("Test Device", params)

        # Find CO2 assessment
        co2_assessment = next(
            (p for p in assessment.parameters if p.parameter == "co2"), None
        )
        assert co2_assessment is not None
        assert co2_assessment.well_compliant is False
        assert co2_assessment.score <= 1

    def test_assess_empty_parameters(self, compliance_engine):
        """Test assessment with no parameters."""
        assessment = compliance_engine.assess("Test Device", [])

        assert assessment.overall_score == 0
        assert assessment.max_score == 0
        assert len(assessment.parameters) == 0

    def test_assess_generates_recommendations(self, compliance_engine):
        """Test that recommendations are generated."""
        params = [
            ParameterData(
                _id="co2_001",
                type="co2",
                unit="ppm",
                measurements=[
                    Measurement(_id="m1", value="1500", date=1702000000000)
                ],
            ),
        ]

        assessment = compliance_engine.assess("Test Device", params)
        assert len(assessment.recommendations) > 0

    def test_assess_indicator_parameter(self, compliance_engine):
        """Test assessment of indicator parameters (higher is better)."""
        params = [
            ParameterData(
                _id="iaq_001",
                type="iaq",
                unit="index",
                measurements=[
                    Measurement(_id="m1", value="85", date=1702000000000)
                ],
            ),
        ]

        assessment = compliance_engine.assess("Test Device", params)

        iaq_assessment = next(
            (p for p in assessment.parameters if p.parameter == "iaq"), None
        )
        assert iaq_assessment is not None
        assert iaq_assessment.score == 4  # 85 >= 80 = Excellent
        assert iaq_assessment.well_compliant is True

    def test_assess_range_parameter(self, compliance_engine):
        """Test assessment of range-based parameters."""
        # Temperature in optimal range
        params = [
            ParameterData(
                _id="temp_001",
                type="temperature",
                unit="°C",
                measurements=[
                    Measurement(_id="m1", value="22", date=1702000000000)
                ],
            ),
        ]

        assessment = compliance_engine.assess("Test Device", params)

        temp_assessment = next(
            (p for p in assessment.parameters if p.parameter == "temperature"), None
        )
        assert temp_assessment is not None
        assert temp_assessment.score == 4  # 22°C is in optimal range (20-24)
        assert temp_assessment.well_compliant is True

