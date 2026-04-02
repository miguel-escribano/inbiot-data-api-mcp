"""
GO IAQS Score calculator tests.

Validates against the worked examples in GO AQS White Paper v1.0
(Appendix A experiments, Section worked example) and covers
synergistic reduction, all pollutant boundary values, tier detection,
CH2O unit conversion, and edge cases.
"""

import pytest

from src.tools.scoring.calculator import (
    GoIaqsCalculator,
    interpolate,
    POLLUTANT_ANCHORS,
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
# Parametrized boundary tests — all 7 pollutants at every anchor point
# Source: White Paper v1.0, Appendix D (pp. 82-83)
# ---------------------------------------------------------------------------

BOUNDARY_CASES = [
    # (pollutant, concentration, expected_score)
    # PM2.5 µg/m³: Good 0-10, Moderate 11-25, Unhealthy 26-100
    ("pm25", 0, 10), ("pm25", 10, 8), ("pm25", 11, 7),
    ("pm25", 25, 4), ("pm25", 26, 3), ("pm25", 100, 0),
    # CO2 ppm: Good 400-800, Moderate 801-1400, Unhealthy 1401-5000
    ("co2", 400, 10), ("co2", 800, 8), ("co2", 801, 7),
    ("co2", 1400, 4), ("co2", 1401, 3), ("co2", 5000, 0),
    # CO ppm: Good 0-1.7, Moderate 1.8-9.0, Unhealthy 9.1-31
    ("co", 0, 10), ("co", 1.7, 8), ("co", 1.8, 7),
    ("co", 9.0, 4), ("co", 9.1, 3), ("co", 31, 0),
    # CH2O ppb: Good 0-27, Moderate 28-100, Unhealthy 101-500
    ("ch2o", 0, 10), ("ch2o", 27, 8), ("ch2o", 28, 7),
    ("ch2o", 100, 4), ("ch2o", 101, 3), ("ch2o", 500, 0),
    # O3 ppb: Good 0-25, Moderate 26-100, Unhealthy 101-300
    ("o3", 0, 10), ("o3", 25, 8), ("o3", 26, 7),
    ("o3", 100, 4), ("o3", 101, 3), ("o3", 300, 0),
    # NO2 ppb: Good 0-21, Moderate 22-100, Unhealthy 101-250
    ("no2", 0, 10), ("no2", 21, 8), ("no2", 22, 7),
    ("no2", 100, 4), ("no2", 101, 3), ("no2", 250, 0),
    # Radon Bq/m³: Good 0-100, Moderate 101-150, Unhealthy 151-300
    ("radon", 0, 10), ("radon", 100, 8), ("radon", 101, 7),
    ("radon", 150, 4), ("radon", 151, 3), ("radon", 300, 0),
]


@pytest.mark.parametrize("pollutant,concentration,expected", BOUNDARY_CASES,
                         ids=[f"{p}-{c}" for p, c, _ in BOUNDARY_CASES])
def test_boundary_score(pollutant, concentration, expected):
    assert calc.compute_sub_score(pollutant, concentration) == expected


# Values beyond anchor range should clamp to nearest boundary score
CLAMP_CASES = [
    ("pm25", -5, 10), ("pm25", 200, 0),
    ("co2", 300, 10), ("co2", 8000, 0),
    ("co", -1, 10), ("co", 50, 0),
    ("ch2o", -1, 10), ("ch2o", 999, 0),
    ("o3", -1, 10), ("o3", 500, 0),
    ("no2", -1, 10), ("no2", 400, 0),
    ("radon", -1, 10), ("radon", 500, 0),
]


@pytest.mark.parametrize("pollutant,concentration,expected", CLAMP_CASES,
                         ids=[f"{p}-clamp-{c}" for p, c, _ in CLAMP_CASES])
def test_clamp_out_of_range(pollutant, concentration, expected):
    assert calc.compute_sub_score(pollutant, concentration) == expected


# ---------------------------------------------------------------------------
# Original interpolation unit tests (kept for continuity)
# ---------------------------------------------------------------------------

class TestInterpolation:
    def test_pm25_beyond_max(self):
        assert interpolate(200, PM25_ANCHORS) == 0

    def test_co2_below_range(self):
        assert interpolate(300, CO2_ANCHORS) == 10


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


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_measurements(self):
        result = calc.calculate({})
        assert result.total_score == 0
        assert result.pollutants_measured == 0
        assert result.tier == "starter"
        assert len(result.missing) == 7
        assert result.dominant_pollutant == []
        assert result.synergistic_reduction is False

    def test_single_pollutant(self):
        result = calc.calculate({"pm25": 5})
        assert result.total_score == 9  # 5 µg/m³ interpolates to 9 in Good band
        assert result.pollutants_measured == 1
        assert result.tier == "starter"
        assert result.synergistic_reduction is False
        assert result.dominant_pollutant == ["pm25"]

    def test_unknown_pollutant_ignored(self):
        result = calc.calculate({"pm25": 5, "tvoc": 300})
        assert result.pollutants_measured == 1
        assert "tvoc" not in result.sub_scores

    def test_hcho_alias_through_sensor_flow(self):
        """Verify the full alias chain: hcho → formaldehyde → ch2o."""
        sensor_data = [
            {"parameter": "hcho", "value": 33.0, "unit": "µg/m³"},
            {"parameter": "pm2.5", "value": 5.0, "unit": "µg/m³"},
            {"parameter": "co2", "value": 600, "unit": "ppm"},
        ]
        result = calc.calculate_from_sensor(sensor_data)
        assert "ch2o" in result.sub_scores
        ch2o_ps = result.sub_scores["ch2o"]
        assert ch2o_ps.value == 33.0
        assert ch2o_ps.unit == "µg/m³"
        assert abs(ch2o_ps.converted_ppb - 26.9) < 0.1

    def test_non_numeric_value_skipped(self):
        sensor_data = [
            {"parameter": "co2", "value": "N/A", "unit": "ppm"},
            {"parameter": "pm2.5", "value": 5.0, "unit": "µg/m³"},
        ]
        result = calc.calculate_from_sensor(sensor_data)
        assert "co2" not in result.sub_scores
        assert result.pollutants_measured == 1


# ---------------------------------------------------------------------------
# White Paper Appendix A — Playground experiments
# Source: GO AQS White Paper v1.0, Appendix A (p. 79)
# ---------------------------------------------------------------------------

class TestWhitePaperExperiments:
    def test_experiment_1_low_concentrations(self):
        """Exp 1: low concentrations across all pollutants → Score 8."""
        result = calc.calculate({
            "pm25": 6, "co2": 500, "co": 1.0,
            "ch2o": 25, "o3": 20, "no2": 20, "radon": 40,
        })
        assert result.total_score == 8
        assert result.category == "Good"

    def test_experiment_7_equal_moderate_synergy(self):
        """White Paper Appendix A, Experiment 7: "Equally moderate values
        to test the Dutch AQI and GO IAQS logic."

        All measured pollutants score 6 → synergy → GO IAQS Score = 5.
        Concentrations chosen to produce score 6 in each Moderate band.
        """
        result = calc.calculate({
            "pm25": 15.67, "co2": 1000, "co": 5.0, "ch2o": 60,
        })
        scores = [ps.score for ps in result.sub_scores.values()]
        assert all(s == 6 for s in scores)
        assert result.synergistic_reduction is True
        assert result.total_score == 5
