import pytest

from heatops.domain.models import Job, Worker
from heatops.optimization.baseline import build_baseline_schedule
from heatops.optimization.presets import OPERATIONS_FIRST
from heatops.optimization.scheduler import optimize_schedule


def build_jobs():
    return [
        Job(
            id="JOB-001",
            name="Inspection A",
            latitude=33.45,
            longitude=-112.07,
            duration_minutes=60,
            earliest_start="08:00",
            deadline="11:00",
            priority=3,
            required_skill="inspection",
        ),
        Job(
            id="JOB-002",
            name="Inspection B",
            latitude=33.46,
            longitude=-112.06,
            duration_minutes=60,
            earliest_start="08:00",
            deadline="11:00",
            priority=1,
            required_skill="inspection",
        ),
    ]


def build_matrix(job_ids, first_temperature, second_temperature):
    temperatures = {
        "08:00": first_temperature,
        "09:00": second_temperature,
        "10:00": second_temperature,
        "11:00": second_temperature,
    }
    return {
        job_id: {
            "name": job_id,
            "temperatures": temperatures.copy(),
        }
        for job_id in job_ids
    }


def build_worker():
    return Worker(
        id="CREW-001",
        name="Crew Alpha",
        start_latitude=33.45,
        start_longitude=-112.07,
        shift_start="08:00",
        shift_end="11:00",
        skills=("inspection",),
    )


def schedule_identity(result):
    return [
        (assignment.job_id, assignment.start_minute, assignment.end_minute)
        for assignment in result.assignments
    ]


def test_baseline_matches_operations_first_optimizer():
    jobs = build_jobs()
    matrix = build_matrix([job.id for job in jobs], 35.0, 40.0)
    worker = build_worker()

    baseline = build_baseline_schedule(jobs, matrix, worker=worker)
    operations = optimize_schedule(
        jobs,
        matrix,
        weights=OPERATIONS_FIRST,
        worker=worker,
    )

    assert schedule_identity(baseline) == schedule_identity(operations)


def test_baseline_schedule_does_not_change_with_temperatures():
    jobs = build_jobs()
    job_ids = [job.id for job in jobs]
    hot_morning = build_matrix(job_ids, 45.0, 30.0)
    cool_morning = build_matrix(job_ids, 30.0, 45.0)

    first = build_baseline_schedule(jobs, hot_morning, worker=build_worker())
    second = build_baseline_schedule(jobs, cool_morning, worker=build_worker())

    assert schedule_identity(first) == schedule_identity(second)


def test_baseline_uses_same_worker_constraints():
    jobs = build_jobs()
    matrix = build_matrix([job.id for job in jobs], 35.0, 35.0)
    worker = Worker(
        id="CREW-001",
        name="Crew Alpha",
        start_latitude=33.45,
        start_longitude=-112.07,
        shift_start="08:00",
        shift_end="11:00",
        skills=("maintenance",),
    )

    with pytest.raises(RuntimeError, match="required skill"):
        build_baseline_schedule(jobs, matrix, worker=worker)
