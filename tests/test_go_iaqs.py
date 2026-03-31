"""
GO IAQS Score calculator tests.

Validates against the worked example in GO AQS White Paper v1.0 and
additional edge cases covering synergistic reduction, boundary values,
tier detection, and CH2O unit conversion.
"""

import pytest

from src.tools.scoring.calculator import (
    GoIaqsCalculator,
    interpolate,
    PM25_ANCHORS,
    CO2_ANCHORS,
    CO_ANCHORS,
    CH2O_ANCHORS,
    O3_ANCHORS,
    NO2_ANCHORS,
    RADON_ANCHORS,
)

calc = GoIaqsCalculator()


# ---------------------------------------------------------------------------
# Interpolation unit tests
# ---------------------------------------------------------------------------

class TestInterpolation:
    def test_pm25_below_range(self):
        assert interpolate(0, PM25_ANCHORS) == 10

    def test_pm25_above_range(self):
        assert interpolate(100, PM25_ANCHORS) == 0

    def test_pm25_beyond_max(self):
        assert interpolate(200, PM25_ANCHORS) == 0

    def test_pm25_at_good_boundary(self):
        assert interpolate(10, PM25_ANCHORS) == 8

    def test_pm25_at_moderate_start(self):
        assert interpolate(11, PM25_ANCHORS) == 7

    def test_pm25_at_moderate_end(self):
        assert interpolate(25, PM25_ANCHORS) == 4

    def test_pm25_at_unhealthy_start(self):
        assert interpolate(26, PM25_ANCHORS) == 3

    def test_co2_below_range(self):
        assert interpolate(300, CO2_ANCHORS) == 10

    def test_co2_at_lower_bound(self):
        assert interpolate(400, CO2_ANCHORS) == 10

    def test_co2_at_good_boundary(self):
        assert interpolate(800, CO2_ANCHORS) == 8

    def test_co2_at_moderate_start(self):
        assert interpolate(801, CO2_ANCHORS) == 7


# ---------------------------------------------------------------------------
# White paper worked example (Section: Worked calculation example)
# PM2.5 = 12 µg/m³ → sub-score 7
# CO2 = 950 ppm → sub-score 6
# Overall = 6, no synergy (scores differ)
# ---------------------------------------------------------------------------

class TestWhitePaperExample:
    def test_pm25_subscore(self):
        assert calc.compute_sub_score("pm25", 12) == 7

    def test_co2_subscore(self):
        assert calc.compute_sub_score("co2", 950) == 6

    def test_overall_score(self):
        result = calc.calculate({"pm25": 12, "co2": 950})
        assert result.total_score == 6

    def test_no_synergy(self):
        result = calc.calculate({"pm25": 12, "co2": 950})
        assert result.synergistic_reduction is False

    def test_grade_b(self):
        result = calc.calculate({"pm25": 12, "co2": 950})
        assert result.grade == "B"
        assert result.category == "Moderate"
        assert result.color_hex == "#FFB000"

    def test_dominant_pollutant_co2(self):
        result = calc.calculate({"pm25": 12, "co2": 950})
        assert result.dominant_pollutant == ["co2"]

    def test_starter_tier(self):
        result = calc.calculate({"pm25": 12, "co2": 950})
        assert result.tier == "starter"


# ---------------------------------------------------------------------------
# Synergistic reduction
# ---------------------------------------------------------------------------

class TestSynergy:
    def test_synergy_applied_when_scores_equal_and_moderate(self):
        # Find values that both produce score 6
        # PM2.5 = 12 → 7, need score 6: PM2.5 ≈ 14.7 → ~6
        # CO2 = 950 → 6
        # Use exact values: PM2.5 in moderate band scoring 6
        # PM2.5 band 11-25 maps to 7-4. For score 6: (7-6)/(7-4)*(25-11)+11 = 15.67
        result = calc.calculate({"pm25": 15.67, "co2": 950})
        pm25_score = result.sub_scores["pm25"].score
        co2_score = result.sub_scores["co2"].score
        assert pm25_score == co2_score == 6
        assert result.synergistic_reduction is True
        assert result.total_score == 5

    def test_no_synergy_when_good_range(self):
        result = calc.calculate({"pm25": 0, "co2": 400})
        assert result.total_score == 10
        assert result.synergistic_reduction is False

    def test_no_synergy_when_scores_differ(self):
        result = calc.calculate({"pm25": 12, "co2": 950})
        assert result.synergistic_reduction is False

    def test_synergy_floor_at_zero(self):
        # Both at score 0 → synergy would give -1, floor at 0
        result = calc.calculate({"pm25": 100, "co2": 5000})
        assert result.total_score == 0
        assert result.synergistic_reduction is True


# ---------------------------------------------------------------------------
# Category mapping
# ---------------------------------------------------------------------------

class TestCategories:
    def test_good(self):
        cat, grade, color, _ = calc.get_category_info(9)
        assert cat == "Good"
        assert grade == "A"
        assert color == "#648EFF"

    def test_moderate(self):
        cat, grade, color, _ = calc.get_category_info(5)
        assert cat == "Moderate"
        assert grade == "B"
        assert color == "#FFB000"

    def test_unhealthy(self):
        cat, grade, color, _ = calc.get_category_info(2)
        assert cat == "Unhealthy"
        assert grade == "Z"
        assert color == "#FF190C"

    def test_boundary_8(self):
        cat, _, _, _ = calc.get_category_info(8)
        assert cat == "Good"

    def test_boundary_7(self):
        cat, _, _, _ = calc.get_category_info(7)
        assert cat == "Moderate"

    def test_boundary_4(self):
        cat, _, _, _ = calc.get_category_info(4)
        assert cat == "Moderate"

    def test_boundary_3(self):
        cat, _, _, _ = calc.get_category_info(3)
        assert cat == "Unhealthy"


# ---------------------------------------------------------------------------
# Tier detection
# ---------------------------------------------------------------------------

class TestTierDetection:
    def test_starter(self):
        result = calc.calculate({"pm25": 5, "co2": 600})
        assert result.tier == "starter"

    def test_ultimate_6_pollutants(self):
        result = calc.calculate({
            "pm25": 5, "co2": 600, "co": 0.5,
            "ch2o": 10, "o3": 15, "no2": 10,
        })
        assert result.tier == "ultimate"
        assert result.pollutants_measured == 6
        assert "radon" in result.missing

    def test_ultimate_all_7(self):
        result = calc.calculate({
            "pm25": 5, "co2": 600, "co": 0.5,
            "ch2o": 10, "o3": 15, "no2": 10, "radon": 50,
        })
        assert result.tier == "ultimate"
        assert result.pollutants_measured == 7
        assert result.missing == []


# ---------------------------------------------------------------------------
# CH2O unit conversion
# ---------------------------------------------------------------------------

class TestCH2OConversion:
    def test_conversion_factor(self):
        ppb = calc.convert_ch2o(1.228)
        assert ppb == 1.0

    def test_conversion_accuracy(self):
        ppb = calc.convert_ch2o(33.0)
        assert abs(ppb - 26.9) < 0.1

    def test_sensor_measurement_flow(self):
        sensor_data = [
            {"parameter": "pm2.5", "value": 5.0, "unit": "µg/m³"},
            {"parameter": "co2", "value": 600, "unit": "ppm"},
            {"parameter": "formaldehyde", "value": 12.28, "unit": "µg/m³"},
        ]
        result = calc.calculate_from_sensor(sensor_data)
        ch2o_ps = result.sub_scores["ch2o"]
        assert ch2o_ps.value == 12.28  # original µg/m³
        assert ch2o_ps.unit == "µg/m³"
        assert ch2o_ps.converted_ppb == 10.0  # 12.28 / 1.228 = 10.0


# ---------------------------------------------------------------------------
# Dominant pollutant
# ---------------------------------------------------------------------------

class TestDominantPollutant:
    def test_single_dominant(self):
        result = calc.calculate({"pm25": 5, "co2": 950})
        assert result.dominant_pollutant == ["co2"]

    def test_multiple_dominant(self):
        result = calc.calculate({"pm25": 0, "co2": 400})
        assert set(result.dominant_pollutant) == {"pm25", "co2"}

    def test_ultimate_dominant(self):
        result = calc.calculate({
            "pm25": 2, "co2": 500, "co": 0.1,
            "ch2o": 5, "o3": 20, "no2": 5,
        })
        # O3 at 20 ppb → score 9 (closest to boundary), others score 10
        assert result.dominant_pollutant == ["o3"]
