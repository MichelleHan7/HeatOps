import pytest

from heatops.domain.config import SchedulerConfig
from heatops.domain.models import Job
from heatops.optimization.heat_risk import (
    calculate_heat_load,
    get_temperature,
)


def build_job(duration_minutes=60, physical_intensity=1.0):
    return Job(
        id="JOB-001",
        name="Inspection",
        latitude=33.45,
        longitude=-112.07,
        duration_minutes=duration_minutes,
        earliest_start="08:00",
        deadline="12:00",
        priority=1,
        physical_intensity=physical_intensity,
    )


def build_matrix(values):
    return {
        "JOB-001": {
            "name": "Inspection",
            "temperatures": values,
        }
    }


def test_get_temperature_returns_hourly_observation():
    matrix = build_matrix({"08:00": 30.0, "09:00": 34.0})

    assert get_temperature("JOB-001", 8 * 60, matrix) == 30.0


@pytest.mark.parametrize(
    ("minute", "expected"),
    [
        (8 * 60 + 15, 31.0),
        (8 * 60 + 30, 32.0),
        (8 * 60 + 45, 33.0),
    ],
)
def test_get_temperature_interpolates(minute, expected):
    matrix = build_matrix({"08:00": 30.0, "09:00": 34.0})

    assert get_temperature("JOB-001", minute, matrix) == expected


def test_calculate_heat_load_matches_hand_calculation():
    job = build_job(duration_minutes=75, physical_intensity=2.0)
    matrix = build_matrix(
        {
            "08:00": 30.0,
            "09:00": 34.0,
            "10:00": 38.0,
        }
    )

    result = calculate_heat_load(job, 8 * 60 + 30, matrix)

    assert result.heat_load == pytest.approx(5.0)
    assert result.average_temperature_c == pytest.approx(34.0)
    assert result.peak_temperature_c == pytest.approx(36.0)
    assert result.minutes_above_threshold == 60


def test_calculate_heat_load_handles_partial_final_slot():
    job = build_job(duration_minutes=20)
    matrix = build_matrix({"08:00": 34.0, "09:00": 34.0})

    result = calculate_heat_load(job, 8 * 60, matrix)

    assert result.heat_load == pytest.approx(2 * 20 / 60)
    assert result.average_temperature_c == 34.0
    assert result.minutes_above_threshold == 20


def test_calculate_heat_load_is_zero_below_threshold():
    job = build_job()
    matrix = build_matrix({"08:00": 30.0, "09:00": 30.0})

    result = calculate_heat_load(
        job,
        8 * 60,
        matrix,
        SchedulerConfig(heat_threshold_c=32.0),
    )

    assert result.heat_load == 0.0
    assert result.minutes_above_threshold == 0


def test_get_temperature_rejects_missing_hour():
    matrix = build_matrix({"08:00": 30.0})

    with pytest.raises(ValueError, match="09:00"):
        get_temperature("JOB-001", 8 * 60 + 30, matrix)


def test_get_temperature_rejects_none():
    matrix = build_matrix({"08:00": None})

    with pytest.raises(ValueError, match="finite"):
        get_temperature("JOB-001", 8 * 60, matrix)
