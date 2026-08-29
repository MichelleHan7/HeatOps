import pytest

from heatops.domain.models import Job, Worker
from heatops.optimization.presets import OPERATIONS_FIRST
from heatops.optimization.scheduler import (
    optimize_schedule,
)


def build_temperature_matrix(
    job_ids: list[str],
):
    hourly_temperatures = {f"{hour:02d}:00": 35.0 for hour in range(8, 20)}

    return {
        job_id: {
            "name": job_id,
            "temperatures": hourly_temperatures.copy(),
        }
        for job_id in job_ids
    }


def build_worker(
    *,
    shift_start="08:00",
    shift_end="19:00",
    skills=("inspection",),
):
    return Worker(
        id="CREW-001",
        name="Crew Alpha",
        start_latitude=33.45,
        start_longitude=-112.07,
        shift_start=shift_start,
        shift_end=shift_end,
        skills=skills,
    )


def test_optimizer_schedules_each_job_once():
    jobs = [
        Job(
            id="JOB-001",
            name="Inspection A",
            latitude=33.45,
            longitude=-112.07,
            duration_minutes=60,
            earliest_start="08:00",
            deadline="11:00",
            priority=1,
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
        ),
    ]

    temperature_matrix = build_temperature_matrix(["JOB-001", "JOB-002"])

    schedule = optimize_schedule(
        jobs,
        temperature_matrix,
    )

    scheduled_ids = {assignment.job_id for assignment in schedule}

    assert scheduled_ids == {
        "JOB-001",
        "JOB-002",
    }


def test_optimizer_prevents_overlap():
    jobs = [
        Job(
            id="JOB-001",
            name="Inspection A",
            latitude=33.45,
            longitude=-112.07,
            duration_minutes=60,
            earliest_start="08:00",
            deadline="11:00",
            priority=1,
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
        ),
    ]

    temperature_matrix = build_temperature_matrix(["JOB-001", "JOB-002"])

    schedule = sorted(
        optimize_schedule(
            jobs,
            temperature_matrix,
        ),
        key=lambda assignment: assignment.start_minute,
    )

    assert schedule[0].end_minute <= schedule[1].start_minute


def test_optimizer_respects_job_windows():
    jobs = [
        Job(
            id="JOB-001",
            name="Inspection A",
            latitude=33.45,
            longitude=-112.07,
            duration_minutes=60,
            earliest_start="09:00",
            deadline="12:00",
            priority=1,
        )
    ]

    temperature_matrix = build_temperature_matrix(["JOB-001"])

    schedule = optimize_schedule(
        jobs,
        temperature_matrix,
    )

    assignment = schedule[0]

    assert assignment.start_minute >= 9 * 60
    assert assignment.end_minute <= 12 * 60


def test_optimizer_respects_worker_shift():
    job = Job(
        id="JOB-001",
        name="Inspection",
        latitude=33.45,
        longitude=-112.07,
        duration_minutes=60,
        earliest_start="08:00",
        deadline="12:00",
        priority=1,
        required_skill="inspection",
    )
    matrix = build_temperature_matrix([job.id])
    worker = build_worker(shift_start="09:00", shift_end="10:00")

    result = optimize_schedule([job], matrix, worker=worker)
    assignment = result.assignments[0]

    assert assignment.worker_id == worker.id
    assert assignment.start_minute == 9 * 60
    assert assignment.end_minute == 10 * 60


def test_optimizer_rejects_missing_worker_skill():
    job = Job(
        id="JOB-001",
        name="Electrical Repair",
        latitude=33.45,
        longitude=-112.07,
        duration_minutes=60,
        earliest_start="08:00",
        deadline="12:00",
        priority=1,
        required_skill="electrical",
    )
    matrix = build_temperature_matrix([job.id])
    worker = build_worker(skills=("inspection",))

    with pytest.raises(RuntimeError, match="required skill"):
        optimize_schedule([job], matrix, worker=worker)


def test_optimizer_rejects_job_that_cannot_fit_window():
    job = Job(
        id="JOB-001",
        name="Inspection",
        latitude=33.45,
        longitude=-112.07,
        duration_minutes=90,
        earliest_start="08:00",
        deadline="09:00",
        priority=1,
    )
    matrix = build_temperature_matrix([job.id])

    with pytest.raises(RuntimeError, match="cannot fit"):
        optimize_schedule([job], matrix)


def test_optimizer_handles_non_aligned_start_grids_without_overlap():
    jobs = [
        Job(
            id="JOB-001",
            name="Inspection A",
            latitude=33.45,
            longitude=-112.07,
            duration_minutes=20,
            earliest_start="08:05",
            deadline="09:05",
            priority=1,
        ),
        Job(
            id="JOB-002",
            name="Inspection B",
            latitude=33.46,
            longitude=-112.06,
            duration_minutes=20,
            earliest_start="08:10",
            deadline="09:10",
            priority=1,
        ),
    ]
    matrix = build_temperature_matrix([job.id for job in jobs])

    assignments = sorted(
        optimize_schedule(jobs, matrix).assignments,
        key=lambda assignment: assignment.start_minute,
    )

    assert assignments[0].end_minute <= assignments[1].start_minute


def test_priority_weighted_delay_protects_high_priority_job():
    jobs = [
        Job(
            id="JOB-LOW",
            name="Low priority",
            latitude=33.45,
            longitude=-112.07,
            duration_minutes=60,
            earliest_start="08:00",
            deadline="11:00",
            priority=1,
        ),
        Job(
            id="JOB-HIGH",
            name="High priority",
            latitude=33.46,
            longitude=-112.06,
            duration_minutes=60,
            earliest_start="08:00",
            deadline="11:00",
            priority=3,
        ),
    ]
    matrix = build_temperature_matrix([job.id for job in jobs])

    result = optimize_schedule(
        jobs,
        matrix,
        weights=OPERATIONS_FIRST,
    )
    starts = {
        assignment.job_id: assignment.start_minute for assignment in result.assignments
    }

    assert starts["JOB-HIGH"] < starts["JOB-LOW"]


def test_optimizer_is_deterministic():
    jobs = [
        Job(
            id="JOB-001",
            name="Inspection A",
            latitude=33.45,
            longitude=-112.07,
            duration_minutes=60,
            earliest_start="08:00",
            deadline="11:00",
            priority=1,
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
        ),
    ]
    matrix = build_temperature_matrix([job.id for job in jobs])

    first = optimize_schedule(jobs, matrix)
    second = optimize_schedule(jobs, matrix)

    assert first.assignments == second.assignments


def test_optimizer_rejects_duplicate_job_ids():
    job = Job(
        id="JOB-001",
        name="Inspection",
        latitude=33.45,
        longitude=-112.07,
        duration_minutes=60,
        earliest_start="08:00",
        deadline="11:00",
        priority=1,
    )
    matrix = build_temperature_matrix([job.id])

    with pytest.raises(ValueError, match="unique"):
        optimize_schedule([job, job], matrix)


def test_optimizer_returns_empty_result_for_no_jobs():
    result = optimize_schedule([], {})

    assert result.status == "OPTIMAL"
    assert result.assignments == ()
    assert result.total_heat_load == 0.0
