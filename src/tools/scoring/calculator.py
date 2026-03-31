"""
GO IAQS Score Calculator — deterministic scoring engine.

Scoring methodology: GO AQS (2025), Global Open Indoor Air Quality Standards:
A Unified Framework, White Paper v1.0, November 2025 (ISBN 9798274916158).
https://goaqs.org  |  License: CC BY-NC-SA 4.0.

Breakpoint tables: White Paper Appendix A (p. 79) and Appendix D (pp. 82-83).
Categories and health advice: GO IAQS Score specification, goaqs.org/go-iaqs-score.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

Anchor = tuple[float, float]

# ---------------------------------------------------------------------------
# Anchor tables  (concentration → score)
# Each list is sorted ascending by concentration. The y-values (scores) are
# descending: lower concentration = higher score = better air.
# ---------------------------------------------------------------------------

PM25_ANCHORS: list[Anchor] = [
    (0, 10), (10, 8), (11, 7), (25, 4), (26, 3), (100, 0),
]

CO2_ANCHORS: list[Anchor] = [
    (400, 10), (800, 8), (801, 7), (1400, 4), (1401, 3), (5000, 0),
]

CO_ANCHORS: list[Anchor] = [
    (0, 10), (1.7, 8), (1.8, 7), (9.0, 4), (9.1, 3), (31, 0),
]

CH2O_ANCHORS: list[Anchor] = [
    (0, 10), (27, 8), (28, 7), (100, 4), (101, 3), (500, 0),
]

O3_ANCHORS: list[Anchor] = [
    (0, 10), (25, 8), (26, 7), (100, 4), (101, 3), (300, 0),
]

NO2_ANCHORS: list[Anchor] = [
    (0, 10), (21, 8), (22, 7), (100, 4), (101, 3), (250, 0),
]

RADON_ANCHORS: list[Anchor] = [
    (0, 10), (100, 8), (101, 7), (150, 4), (151, 3), (300, 0),
]

POLLUTANT_ANCHORS: dict[str, list[Anchor]] = {
    "pm25": PM25_ANCHORS,
    "co2": CO2_ANCHORS,
    "co": CO_ANCHORS,
    "ch2o": CH2O_ANCHORS,
    "o3": O3_ANCHORS,
    "no2": NO2_ANCHORS,
    "radon": RADON_ANCHORS,
}

POLLUTANT_UNITS: dict[str, str] = {
    "pm25": "µg/m³",
    "co2": "ppm",
    "co": "ppm",
    "ch2o": "ppb",
    "o3": "ppb",
    "no2": "ppb",
    "radon": "Bq/m³",
}

ALL_POLLUTANTS = list(POLLUTANT_ANCHORS.keys())
STARTER_POLLUTANTS = {"pm25", "co2"}

CATEGORIES: list[tuple[int, int, str, str, str, str]] = [
    # (score_min, score_max, category, grade, color_hex, health_advice)
    (8, 10, "Good", "A", "#648EFF",
     "Air quality is satisfactory. Enjoy normal activities."),
    (4, 7, "Moderate", "B", "#FFB000",
     "Sensitive people should limit prolonged heavy exertion."),
    (0, 3, "Unhealthy", "Z", "#FF190C",
     "Everyone should reduce prolonged exertion. "
     "Sensitive groups should avoid heavy outdoor/indoor activity."),
]

# CH2O conversion factor: µg/m³ → ppb at 25 °C, 1 atm (MW = 30.03 g/mol)
CH2O_UG_TO_PPB = 1.228

# Mapping from InBiot normalized parameter names to GO IAQS pollutant keys
SENSOR_TO_GOIAQS: dict[str, str] = {
    "pm25": "pm25",
    "co2": "co2",
    "co": "co",
    "formaldehyde": "ch2o",
    "o3": "o3",
    "no2": "no2",
    "radon": "radon",
}

# Clamp ranges per pollutant (min, max concentration accepted)
POLLUTANT_CLAMP: dict[str, tuple[float, float]] = {
    "pm25": (0, 100),
    "co2": (400, 5000),
    "co": (0, 31),
    "ch2o": (0, 500),
    "o3": (0, 300),
    "no2": (0, 250),
    "radon": (0, 300),
}


def _round_half_up(value: float) -> int:
    """Round with half-up rule (0.5 rounds to 1, not to 0)."""
    return int(math.floor(value + 0.5))


def _clamp(value: float, lo: float, hi: float) -> float:
    return min(max(value, lo), hi)


# ---------------------------------------------------------------------------
# Core interpolation
# ---------------------------------------------------------------------------

def interpolate(value: float, anchors: list[Anchor]) -> int:
    """Piecewise linear interpolation over anchor pairs → integer score [0, 10]."""
    if value <= anchors[0][0]:
        return int(anchors[0][1])
    if value >= anchors[-1][0]:
        return int(anchors[-1][1])

    for i in range(len(anchors) - 1):
        left_x, left_y = anchors[i]
        right_x, right_y = anchors[i + 1]
        if value <= right_x:
            interpolated = left_y + ((value - left_x) / (right_x - left_x)) * (right_y - left_y)
            return _clamp(_round_half_up(interpolated), 0, 10)

    return int(anchors[-1][1])


# ---------------------------------------------------------------------------
# Result data structures
# ---------------------------------------------------------------------------

@dataclass
class PollutantScore:
    pollutant: str
    value: float
    unit: str
    score: int
    converted_ppb: float | None = None  # only for ch2o (sensor reports µg/m³)


@dataclass
class GoIaqsResult:
    tier: str
    pollutants_measured: int
    pollutants_total: int
    sub_scores: dict[str, PollutantScore]
    missing: list[str]
    total_score: int
    grade: str
    category: str
    color_hex: str
    dominant_pollutant: list[str]
    health_advice: str
    synergistic_reduction: bool


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------

class GoIaqsCalculator:
    """Deterministic GO IAQS Score calculator."""

    @staticmethod
    def compute_sub_score(pollutant: str, value: float) -> int:
        """Compute a single pollutant sub-score (0-10)."""
        anchors = POLLUTANT_ANCHORS[pollutant]
        lo, hi = POLLUTANT_CLAMP[pollutant]
        clamped = _clamp(value, lo, hi)
        return interpolate(clamped, anchors)

    @staticmethod
    def convert_ch2o(value_ug_m3: float) -> float:
        """Convert formaldehyde from µg/m³ to ppb."""
        return round(value_ug_m3 / CH2O_UG_TO_PPB, 1)

    @staticmethod
    def get_category_info(score: int) -> tuple[str, str, str, str]:
        """Return (category, grade, color_hex, health_advice) for a score."""
        for score_min, score_max, category, grade, color_hex, advice in CATEGORIES:
            if score_min <= score <= score_max:
                return category, grade, color_hex, advice
        return "Unhealthy", "Z", "#FF190C", CATEGORIES[-1][5]

    @staticmethod
    def determine_tier(measured_keys: set[str]) -> str:
        """Starter = only PM2.5 + CO2; Ultimate = 5+ pollutants."""
        if measured_keys <= STARTER_POLLUTANTS:
            return "starter"
        return "ultimate"

    def calculate(self, measurements: dict[str, float]) -> GoIaqsResult:
        """
        Calculate the full GO IAQS Score from a pollutant measurement dict.

        Parameters
        ----------
        measurements : dict mapping GO IAQS pollutant key to concentration value.
                       Keys: pm25, co2, co, ch2o (in ppb), o3, no2, radon.
                       For ch2o coming from sensor in µg/m³, convert first with
                       convert_ch2o() before calling, or use calculate_from_sensor().

        Returns
        -------
        GoIaqsResult with all scoring details.
        """
        sub_scores: dict[str, PollutantScore] = {}

        for pollutant, value in measurements.items():
            if pollutant not in POLLUTANT_ANCHORS:
                continue
            score = self.compute_sub_score(pollutant, value)
            sub_scores[pollutant] = PollutantScore(
                pollutant=pollutant,
                value=value,
                unit=POLLUTANT_UNITS[pollutant],
                score=score,
            )

        measured_keys = set(sub_scores.keys())
        missing = [p for p in ALL_POLLUTANTS if p not in measured_keys]
        tier = self.determine_tier(measured_keys)

        scores = [ps.score for ps in sub_scores.values()]
        if not scores:
            total_score = 0
        else:
            total_score = min(scores)

        # Synergistic reduction: when all sub-scores in Moderate/Unhealthy
        # (<=7) share the same integer value, deduct 1 (floor at 0).
        synergistic = False
        if len(scores) >= 2:
            low_scores = [s for s in scores if s <= 7]
            if len(low_scores) >= 2 and len(set(low_scores)) == 1:
                total_score = max(low_scores[0] - 1, 0)
                synergistic = True

        category, grade, color_hex, health_advice = self.get_category_info(total_score)

        # Dominant pollutant(s): those with the lowest sub-score
        if scores:
            min_score = min(scores)
            dominant = [p for p, ps in sub_scores.items() if ps.score == min_score]
        else:
            dominant = []

        return GoIaqsResult(
            tier=tier,
            pollutants_measured=len(sub_scores),
            pollutants_total=len(ALL_POLLUTANTS),
            sub_scores=sub_scores,
            missing=missing,
            total_score=total_score,
            grade=grade,
            category=category,
            color_hex=color_hex,
            dominant_pollutant=dominant,
            health_advice=health_advice,
            synergistic_reduction=synergistic,
        )

    def calculate_from_sensor(
        self,
        sensor_measurements: list[dict],
    ) -> GoIaqsResult:
        """
        Calculate GO IAQS Score from raw InBiot sensor measurement dicts.

        Parameters
        ----------
        sensor_measurements : list of dicts with keys 'parameter', 'value', 'unit'
                              as returned by get_latest_measurements.
        """
        from src.utils.normalization import normalize_parameter_name

        goiaqs_values: dict[str, float] = {}
        ch2o_original: float | None = None

        for m in sensor_measurements:
            param = normalize_parameter_name(m["parameter"])
            goiaqs_key = SENSOR_TO_GOIAQS.get(param)
            if goiaqs_key is None:
                continue

            value = m["value"]
            if not isinstance(value, (int, float)):
                continue

            if goiaqs_key == "ch2o":
                ch2o_original = float(value)
                value = self.convert_ch2o(float(value))

            goiaqs_values[goiaqs_key] = float(value)

        result = self.calculate(goiaqs_values)

        if ch2o_original is not None and "ch2o" in result.sub_scores:
            result.sub_scores["ch2o"].converted_ppb = result.sub_scores["ch2o"].value
            result.sub_scores["ch2o"].value = ch2o_original
            result.sub_scores["ch2o"].unit = "µg/m³"

        return result
