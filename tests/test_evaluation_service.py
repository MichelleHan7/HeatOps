import pytest

from heatops.domain.config import SchedulerConfig
from heatops.domain.models import Job, OptimizationWeights, Worker
from heatops.evaluation.service import compare_schedules


def _worker() -> Worker:
    return Worker(
        id="CREW-1",
        name="Crew 1",
        start_latitude=33.45,
        start_longitude=-112.07,
        shift_start="08:00",
        shift_end="12:00",
        skills=(),
    )


def test_compare_schedules_returns_baseline_optimized_and_job_deltas():
    jobs = [
        Job(
            id="A",
            name="A",
            latitude=33.45,
            longitude=-112.07,
            duration_minutes=60,
            earliest_start="08:00",
            deadline="12:00",
            priority=1,
        )
    ]
    temperatures = {
        "A": {
            "name": "A",
            "temperatures": {
                "08:00": 36.0,
                "09:00": 35.0,
                "10:00": 32.0,
                "11:00": 31.0,
            },
        }
    }

    comparison = compare_schedules(
        jobs,
        temperatures,
        worker=_worker(),
        weights=OptimizationWeights(heat=1, delay=0),
        config=SchedulerConfig(heat_threshold_c=30.0, slot_minutes=60),
    )

    assert comparison.baseline_result.assignments[0].start_minute == 480
    assert comparison.optimized_result.assignments[0].start_minute == 660
    assert comparison.baseline_metrics.total_heat_load == 6.0
    assert comparison.optimized_metrics.total_heat_load == 1.0
    assert comparison.heat_load_reduction_percent == pytest.approx(83.333333)
    assert comparison.moved_jobs == 1
    assert comparison.job_changes[0].moved is True


def test_compare_schedules_handles_zero_heat_baseline():
    jobs = [
        Job(
            id="A",
            name="A",
            latitude=33.45,
            longitude=-112.07,
            duration_minutes=60,
            earliest_start="08:00",
            deadline="10:00",
            priority=1,
        )
    ]
    temperatures = {
        "A": {
            "name": "A",
            "temperatures": {"08:00": 20.0, "09:00": 20.0, "10:00": 20.0},
        }
    }

    comparison = compare_schedules(jobs, temperatures, worker=_worker())

    assert comparison.baseline_metrics.total_heat_load == 0
    assert comparison.heat_load_reduction_percent == 0
