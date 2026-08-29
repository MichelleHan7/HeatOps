from dataclasses import FrozenInstanceError

import pytest

from heatops.domain.config import SchedulerConfig
from heatops.domain.models import Job, OptimizationWeights, Worker


def test_scheduler_config_accepts_valid_values():
    config = SchedulerConfig(
        slot_minutes=10,
        heat_threshold_c=31.5,
        default_shift_start="07:00",
        default_shift_end="17:00",
    )

    assert config.slot_minutes == 10
    assert config.heat_threshold_c == 31.5


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("slot_minutes", 0),
        ("solver_time_limit_seconds", 0),
        ("objective_scale", 0),
    ],
)
def test_scheduler_config_rejects_nonpositive_values(field, value):
    with pytest.raises(ValueError):
        SchedulerConfig(**{field: value})


def test_scheduler_config_rejects_invalid_shift():
    with pytest.raises(ValueError, match="shift_start"):
        SchedulerConfig(
            default_shift_start="18:00",
            default_shift_end="08:00",
        )


@pytest.mark.parametrize(
    "weights",
    [
        {"heat": -1.0, "delay": 1.0},
        {"heat": 1.0, "delay": -1.0},
        {"heat": 0.0, "delay": 0.0},
    ],
)
def test_optimization_weights_reject_invalid_values(weights):
    with pytest.raises(ValueError):
        OptimizationWeights(**weights)


def test_optimization_weights_normalize():
    weights = OptimizationWeights(heat=3.0, delay=1.0)

    assert weights.normalized() == (0.75, 0.25)


def test_job_rejects_invalid_duration():
    with pytest.raises(ValueError, match="positive duration"):
        Job(
            id="JOB-001",
            name="Inspection",
            latitude=33.45,
            longitude=-112.07,
            duration_minutes=0,
            earliest_start="08:00",
            deadline="09:00",
            priority=1,
        )


def test_job_rejects_invalid_time_window():
    with pytest.raises(ValueError, match="earliest_start"):
        Job(
            id="JOB-001",
            name="Inspection",
            latitude=33.45,
            longitude=-112.07,
            duration_minutes=30,
            earliest_start="09:00",
            deadline="08:00",
            priority=1,
        )


def test_job_rejects_invalid_physical_intensity():
    with pytest.raises(ValueError, match="physical_intensity"):
        Job(
            id="JOB-001",
            name="Inspection",
            latitude=33.45,
            longitude=-112.07,
            duration_minutes=30,
            earliest_start="08:00",
            deadline="09:00",
            priority=1,
            physical_intensity=0,
        )


def test_worker_is_immutable_and_normalizes_skills():
    worker = Worker(
        id="CREW-001",
        name="Crew Alpha",
        start_latitude=33.45,
        start_longitude=-112.07,
        shift_start="08:00",
        shift_end="17:00",
        skills=["inspection"],
    )

    assert worker.skills == ("inspection",)

    with pytest.raises(FrozenInstanceError):
        worker.name = "Changed"
