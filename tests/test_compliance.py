"""
GO IAQS Compliance Calculator tests.

Validates rolling averages, tier-appropriate limit selection,
dual limits (CO, NO2), CH2O conversion, context parameters,
and edge cases using synthetic measurement data.
"""

import pytest
from datetime import datetime, timedelta, timezone

from src.models.schemas import Measurement
from src.tools.scoring.compliance import (
    STARTER_LIMITS,
    ULTIMATE_LIMITS,
    CHART_HOURS,
    Limit,
    hourly_mean,
    rolling_average,
    determine_tier,
    compute_pollutant_series,
    compute_context_series,
    build_compliance_result,
)


# ---------------------------------------------------------------------------
# Helpers — generate synthetic measurements
# ---------------------------------------------------------------------------

def make_measurements(
    values_per_hour: list[list[float]],
    end_time: datetime,
    readings_per_hour: int = 6,
) -> list[Measurement]:
    """Create measurements working backwards from end_time.

    values_per_hour[0] is the oldest hour, values_per_hour[-1] is the
    most recent. Each inner list has `readings_per_hour` values evenly
    spaced within the hour.
    """
    measurements = []
    num_hours = len(values_per_hour)
    base = end_time - timedelta(hours=num_hours)

    for hour_idx, values in enumerate(values_per_hour):
        hour_start = base + timedelta(hours=hour_idx)
        interval = timedelta(minutes=60 / len(values)) if len(values) > 1 else timedelta(minutes=5)
        for i, v in enumerate(values):
            ts = hour_start + interval * i
            measurements.append(Measurement(
                value=v,
                date=ts.timestamp() * 1000,
            ))
    return measurements


def constant_measurements(
    value: float,
    hours: int,
    end_time: datetime,
    per_hour: int = 6,
) -> list[Measurement]:
    """Create constant-value measurements spanning `hours` before end_time."""
    return make_measurements(
        [[value] * per_hour for _ in range(hours)],
        end_time,
    )


NOW = datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# hourly_mean
# ---------------------------------------------------------------------------

class TestHourlyMean:
    def test_simple_mean(self):
        ms = constant_measurements(20.0, 2, NOW)
        hour_start = NOW - timedelta(hours=1)
        assert hourly_mean(ms, hour_start) == 20.0

    def test_varying_values(self):
        ms = make_measurements([[10, 20, 30]], NOW)
        hour_start = NOW - timedelta(hours=1)
        assert hourly_mean(ms, hour_start) == 20.0

    def test_empty_hour(self):
        ms = constant_measurements(20.0, 2, NOW)
        far_past = NOW - timedelta(hours=10)
        assert hourly_mean(ms, far_past) is None


# ---------------------------------------------------------------------------
# rolling_average
# ---------------------------------------------------------------------------

class TestRollingAverage:
    def test_1h_rolling(self):
        ms = constant_measurements(500.0, 3, NOW)
        assert rolling_average(ms, NOW, 1) == 500.0

    def test_8h_rolling(self):
        values = [[100] * 6] * 4 + [[200] * 6] * 4
        ms = make_measurements(values, NOW)
        avg = rolling_average(ms, NOW, 8)
        assert avg == pytest.approx(150, abs=2)

    def test_24h_rolling(self):
        ms = constant_measurements(12.0, 48, NOW)
        assert rolling_average(ms, NOW, 24) == 12.0

    def test_insufficient_data(self):
        ms = constant_measurements(10.0, 48, NOW)
        far_future = NOW + timedelta(hours=100)
        assert rolling_average(ms, far_future, 1) is None


# ---------------------------------------------------------------------------
# determine_tier
# ---------------------------------------------------------------------------

class TestDetermineTier:
    def test_starter(self):
        assert determine_tier({"pm25", "co2"}) == "starter"

    def test_starter_pm25_only(self):
        assert determine_tier({"pm25"}) == "starter"

    def test_ultimate(self):
        assert determine_tier({"pm25", "co2", "co"}) == "ultimate"

    def test_empty(self):
        assert determine_tier(set()) == "starter"


# ---------------------------------------------------------------------------
# compute_pollutant_series — Starter PM2.5 (24h avg, limit 25)
# ---------------------------------------------------------------------------

class TestStarterPM25:
    def test_all_pass(self):
        ms = constant_measurements(12.0, 48, NOW)
        result = compute_pollutant_series(
            ms, STARTER_LIMITS["pm25"], NOW,
        )
        assert result["overall_status"] == "pass"
        assert all(s == "pass" for s in result["status"])
        assert result["latest_rolling_avg"] == 12.0
        assert len(result["rolling_avg"]) == CHART_HOURS

    def test_all_fail(self):
        ms = constant_measurements(30.0, 48, NOW)
        result = compute_pollutant_series(
            ms, STARTER_LIMITS["pm25"], NOW,
        )
        assert result["overall_status"] == "fail"
        assert all(s == "fail" for s in result["status"])

    def test_limit_boundary(self):
        ms = constant_measurements(25.0, 48, NOW)
        result = compute_pollutant_series(
            ms, STARTER_LIMITS["pm25"], NOW,
        )
        assert result["overall_status"] == "pass"

    def test_limit_value_in_output(self):
        ms = constant_measurements(10.0, 48, NOW)
        result = compute_pollutant_series(
            ms, STARTER_LIMITS["pm25"], NOW,
        )
        assert result["limits"][0]["value"] == 25
        assert result["limits"][0]["label"] == "24h avg"
        assert result["unit"] == "µg/m³"


# ---------------------------------------------------------------------------
# compute_pollutant_series — Ultimate PM2.5 (1h avg, limit 15)
# ---------------------------------------------------------------------------

class TestUltimatePM25:
    def test_pass_under_ultimate_but_fail_starter_never_happens(self):
        """Ultimate PM2.5 limit (15) is stricter than Starter (25)."""
        ms = constant_measurements(20.0, 48, NOW)
        starter = compute_pollutant_series(ms, STARTER_LIMITS["pm25"], NOW)
        ultimate = compute_pollutant_series(ms, ULTIMATE_LIMITS["pm25"], NOW)
        assert starter["overall_status"] == "pass"
        assert ultimate["overall_status"] == "fail"


# ---------------------------------------------------------------------------
# Threshold pollutants (CO2, CH2O) — no averaging period
# ---------------------------------------------------------------------------

class TestThresholdPollutants:
    def test_co2_starter_pass(self):
        ms = constant_measurements(900.0, 48, NOW)
        result = compute_pollutant_series(
            ms, STARTER_LIMITS["co2"], NOW,
        )
        assert result["overall_status"] == "pass"

    def test_co2_starter_fail(self):
        ms = constant_measurements(1100.0, 48, NOW)
        result = compute_pollutant_series(
            ms, STARTER_LIMITS["co2"], NOW,
        )
        assert result["overall_status"] == "fail"

    def test_co2_ultimate_stricter(self):
        ms = constant_measurements(900.0, 48, NOW)
        starter = compute_pollutant_series(ms, STARTER_LIMITS["co2"], NOW)
        ultimate = compute_pollutant_series(ms, ULTIMATE_LIMITS["co2"], NOW)
        assert starter["overall_status"] == "pass"
        assert ultimate["overall_status"] == "fail"


# ---------------------------------------------------------------------------
# Dual limits — CO (9 ppm 8h, 31 ppm 1h)
# ---------------------------------------------------------------------------

class TestDualLimits:
    def test_co_pass_both(self):
        ms = constant_measurements(5.0, 48, NOW)
        result = compute_pollutant_series(
            ms, ULTIMATE_LIMITS["co"], NOW,
        )
        assert result["overall_status"] == "pass"
        assert len(result["limits"]) == 2

    def test_co_fail_8h_pass_1h(self):
        ms = constant_measurements(15.0, 48, NOW)
        result = compute_pollutant_series(
            ms, ULTIMATE_LIMITS["co"], NOW,
        )
        assert result["overall_status"] == "fail"

    def test_co_spike_fails_1h_limit(self):
        """Sustained low + recent spike that exceeds 1h peak limit."""
        low = [[2.0] * 6] * 46
        spike = [[35.0] * 6] * 2
        ms = make_measurements(low + spike, NOW)
        result = compute_pollutant_series(
            ms, ULTIMATE_LIMITS["co"], NOW,
        )
        last_status = result["status"][-1]
        assert last_status == "fail"

    def test_no2_dual_limits_present(self):
        ms = constant_measurements(10.0, 48, NOW)
        result = compute_pollutant_series(
            ms, ULTIMATE_LIMITS["no2"], NOW,
        )
        assert result["overall_status"] == "pass"
        labels = [l["label"] for l in result["limits"]]
        assert "8h avg" in labels
        assert "1h peak" in labels


# ---------------------------------------------------------------------------
# CH2O conversion (sensor µg/m³ → GO IAQS ppb)
# ---------------------------------------------------------------------------

class TestCH2OConversion:
    def test_conversion_applied(self):
        ms = constant_measurements(33.0, 48, NOW)
        result = compute_pollutant_series(
            ms, ULTIMATE_LIMITS["ch2o"], NOW, convert_from_ug=True,
        )
        latest = result["latest_rolling_avg"]
        assert latest is not None
        assert abs(latest - 26.9) < 0.2
        assert result["overall_status"] == "pass"

    def test_over_limit_after_conversion(self):
        ms = constant_measurements(40.0, 48, NOW)
        result = compute_pollutant_series(
            ms, ULTIMATE_LIMITS["ch2o"], NOW, convert_from_ug=True,
        )
        latest = result["latest_rolling_avg"]
        assert latest is not None
        assert latest > 27
        assert result["overall_status"] == "fail"


# ---------------------------------------------------------------------------
# Context parameters (temperature, humidity)
# ---------------------------------------------------------------------------

class TestContextSeries:
    def test_temperature(self):
        ms = constant_measurements(22.5, 30, NOW)
        result = compute_context_series(ms, "°C", NOW)
        assert result["unit"] == "°C"
        assert result["latest"] == 22.5
        assert len(result["values"]) == CHART_HOURS

    def test_empty_data(self):
        result = compute_context_series([], "°C", NOW)
        assert result["latest"] is None
        assert all(v is None for v in result["values"])


# ---------------------------------------------------------------------------
# build_compliance_result — full integration
# ---------------------------------------------------------------------------

class TestBuildComplianceResult:
    def test_starter_only_sensor(self):
        pm25_ms = constant_measurements(10.0, 48, NOW)
        co2_ms = constant_measurements(800.0, 48, NOW)
        temp_ms = constant_measurements(22.0, 48, NOW)

        param_data = {
            "pm25": (pm25_ms, "µg/m³"),
            "co2": (co2_ms, "ppm"),
            "temperature": (temp_ms, "°C"),
        }
        result = build_compliance_result(param_data, NOW)

        assert result["tier"] == "starter"
        assert result["ultimate"] is None
        assert "pm25" in result["starter"]
        assert "co2" in result["starter"]
        assert "temperature" in result["starter"]
        assert len(result["hours"]) == CHART_HOURS

    def test_ultimate_sensor(self):
        base = {
            "pm25": (constant_measurements(10.0, 48, NOW), "µg/m³"),
            "co2": (constant_measurements(600.0, 48, NOW), "ppm"),
            "co": (constant_measurements(1.0, 48, NOW), "ppm"),
            "formaldehyde": (constant_measurements(20.0, 48, NOW), "µg/m³"),
            "o3": (constant_measurements(30.0, 48, NOW), "ppb"),
            "no2": (constant_measurements(15.0, 48, NOW), "ppb"),
            "temperature": (constant_measurements(22.0, 48, NOW), "°C"),
            "humidity": (constant_measurements(45.0, 48, NOW), "%"),
        }
        result = build_compliance_result(base, NOW)

        assert result["tier"] == "ultimate"
        assert result["ultimate"] is not None
        assert "ch2o" in result["ultimate"]
        assert result["starter"]["pm25"]["limits"][0]["value"] == 25
        assert result["ultimate"]["pm25"]["limits"][0]["value"] == 15
        assert "temperature" in result["starter"]
        assert "temperature" in result["ultimate"]

    def test_missing_pollutant_marked_insufficient(self):
        param_data = {
            "pm25": (constant_measurements(10.0, 48, NOW), "µg/m³"),
            "co2": (constant_measurements(600.0, 48, NOW), "ppm"),
            "co": (constant_measurements(1.0, 48, NOW), "ppm"),
        }
        result = build_compliance_result(param_data, NOW)
        assert result["tier"] == "ultimate"
        assert result["ultimate"]["ch2o"]["overall_status"] == "insufficient_data"
        assert result["ultimate"]["radon"]["overall_status"] == "insufficient_data"

    def test_hours_labels_correct_count(self):
        param_data = {
            "pm25": (constant_measurements(10.0, 48, NOW), "µg/m³"),
            "co2": (constant_measurements(600.0, 48, NOW), "ppm"),
        }
        result = build_compliance_result(param_data, NOW)
        assert len(result["hours"]) == 24
