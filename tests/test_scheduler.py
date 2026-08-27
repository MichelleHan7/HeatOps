from heatops.domain.models import Job
from heatops.optimization.scheduler import (
    optimize_schedule,
)


def build_temperature_matrix(
    job_ids: list[str],
):
    hourly_temperatures = {
        f"{hour:02d}:00": 35.0
        for hour in range(8, 20)
    }

    return {
        job_id: {
            "name": job_id,
            "temperatures": (
                hourly_temperatures.copy()
            ),
        }
        for job_id in job_ids
    }


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

    temperature_matrix = (
        build_temperature_matrix(
            ["JOB-001", "JOB-002"]
        )
    )

    schedule = optimize_schedule(
        jobs,
        temperature_matrix,
    )

    scheduled_ids = {
        assignment.job_id
        for assignment in schedule
    }

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

    temperature_matrix = (
        build_temperature_matrix(
            ["JOB-001", "JOB-002"]
        )
    )

    schedule = sorted(
        optimize_schedule(
            jobs,
            temperature_matrix,
        ),
        key=lambda assignment: (
            assignment.start_minute
        ),
    )

    assert (
        schedule[0].end_minute
        <= schedule[1].start_minute
    )


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

    temperature_matrix = (
        build_temperature_matrix(
            ["JOB-001"]
        )
    )

    schedule = optimize_schedule(
        jobs,
        temperature_matrix,
    )

    assignment = schedule[0]

    assert assignment.start_minute >= 9 * 60
    assert assignment.end_minute <= 12 * 60