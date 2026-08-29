import pytest

from heatops.domain.config import SchedulerConfig
from heatops.domain.models import Job, OptimizationResult, ScheduleAssignment
from heatops.evaluation.metrics import build_job_changes, calculate_schedule_metrics


def _job(job_id: str, priority: int = 1) -> Job:
    return Job(
        id=job_id,
        name=job_id,
        latitude=33.45,
        longitude=-112.07,
        duration_minutes=60,
        earliest_start="08:00",
        deadline="12:00",
        priority=priority,
    )


def _result(*assignments: ScheduleAssignment) -> OptimizationResult:
    return OptimizationResult(
        assignments=assignments,
        status="OPTIMAL",
        objective_value=0,
        total_heat_load=sum(item.heat_load for item in assignments),
        total_delay_hours=0,
    )


def _assignment(job_id: str, start: int, temperature: float, heat: float):
    return ScheduleAssignment(
        job_id=job_id,
        worker_id="CREW-1",
        start_minute=start,
        end_minute=start + 60,
        temperature_c=temperature,
        heat_load=heat,
    )


def test_calculate_schedule_metrics_includes_heat_delay_and_idle_time():
    jobs = [_job("A", priority=2), _job("B", priority=3)]
    temperatures = {
        "A": {"name": "A", "temperatures": {"08:00": 35.0}},
        "B": {"name": "B", "temperatures": {"10:00": 34.0}},
    }
    result = _result(
        _assignment("A", 8 * 60, 35.0, 5.0),
        _assignment("B", 10 * 60, 34.0, 4.0),
    )

    metrics = calculate_schedule_metrics(
        result,
        jobs,
        temperatures,
        SchedulerConfig(heat_threshold_c=30.0, slot_minutes=60),
    )

    assert metrics.total_heat_load == pytest.approx(9.0)
    assert metrics.peak_temperature_c == 35.0
    assert metrics.minutes_above_threshold == 120
    assert metrics.total_delay_hours == 2.0
    assert metrics.priority_weighted_delay_hours == 6.0
    assert metrics.idle_minutes == 60
    assert metrics.scheduled_jobs == 2


def test_build_job_changes_reports_moved_and_unchanged_jobs():
    baseline = _result(
        _assignment("A", 8 * 60, 35.0, 5.0),
        _assignment("B", 9 * 60, 34.0, 4.0),
    )
    optimized = _result(
        _assignment("A", 10 * 60, 32.0, 2.0),
        _assignment("B", 9 * 60, 34.0, 4.0),
    )

    changes = build_job_changes(baseline, optimized)

    assert [change.job_id for change in changes] == ["A", "B"]
    assert changes[0].moved is True
    assert changes[0].start_delta_minutes == 120
    assert changes[0].temperature_delta_c == -3.0
    assert changes[0].heat_load_delta == -3.0
    assert "operational Heat Load" in changes[0].explanation
    assert changes[1].moved is False
    assert "stayed at 09:00" in changes[1].explanation


def test_build_job_changes_requires_identical_job_sets():
    with pytest.raises(ValueError, match="same jobs"):
        build_job_changes(
            _result(_assignment("A", 480, 35.0, 5.0)),
            _result(_assignment("B", 480, 35.0, 5.0)),
        )
