import pytest

from heatops.domain.models import Job
from heatops.optimization.presets import (
    BALANCED,
    HEAT_FIRST,
    OPERATIONS_FIRST,
    get_preset,
    weights_from_heat_priority,
)
from heatops.optimization.scheduler import optimize_schedule


def build_scenario():
    job = Job(
        id="JOB-001",
        name="Flexible inspection",
        latitude=33.45,
        longitude=-112.07,
        duration_minutes=60,
        earliest_start="08:00",
        deadline="10:00",
        priority=1,
    )
    matrix = {
        job.id: {
            "name": job.name,
            "temperatures": {
                "08:00": 40.0,
                "09:00": 30.0,
                "10:00": 30.0,
            },
        }
    }
    return [job], matrix


def test_named_presets_are_available():
    assert get_preset("operations_first") is OPERATIONS_FIRST
    assert get_preset("balanced") is BALANCED
    assert get_preset("heat_first") is HEAT_FIRST


def test_unknown_preset_is_rejected():
    with pytest.raises(ValueError, match="Unknown"):
        get_preset("fastest")


@pytest.mark.parametrize(
    ("priority", "expected"),
    [(0, (0.0, 1.0)), (50, (0.5, 0.5)), (100, (1.0, 0.0))],
)
def test_heat_priority_conversion(priority, expected):
    weights = weights_from_heat_priority(priority)

    assert weights.normalized() == expected


@pytest.mark.parametrize("priority", [-1, 101])
def test_heat_priority_rejects_out_of_range_values(priority):
    with pytest.raises(ValueError, match="between 0 and 100"):
        weights_from_heat_priority(priority)


def test_presets_form_an_honest_heat_delay_tradeoff():
    jobs, matrix = build_scenario()

    operations = optimize_schedule(jobs, matrix, OPERATIONS_FIRST)
    balanced = optimize_schedule(jobs, matrix, BALANCED)
    heat_first = optimize_schedule(jobs, matrix, HEAT_FIRST)

    assert operations.total_delay_hours <= balanced.total_delay_hours
    assert balanced.total_delay_hours <= heat_first.total_delay_hours
    assert operations.total_heat_load >= balanced.total_heat_load
    assert balanced.total_heat_load >= heat_first.total_heat_load


def test_heat_first_improves_heat_at_an_explicit_delay_cost():
    jobs, matrix = build_scenario()

    operations = optimize_schedule(jobs, matrix, OPERATIONS_FIRST)
    heat_first = optimize_schedule(jobs, matrix, HEAT_FIRST)

    assert heat_first.total_heat_load < operations.total_heat_load
    assert heat_first.total_delay_hours > operations.total_delay_hours
