from heatops.domain.models import (
    Job,
    ScheduleAssignment,
    TemperatureMatrix,
)
from heatops.domain.time_utils import time_to_minutes
from heatops.optimization.scheduler import calculate_heat_load


def build_baseline_schedule(
    jobs: list[Job],
    temperature_matrix: TemperatureMatrix,
    worker_id: str = "CREW-001",
) -> list[ScheduleAssignment]:
    """
    Temperature-unaware Earliest Deadline First (EDF).

    At each point in time:
    1. Find all jobs currently available.
    2. Choose the job with the earliest deadline.
    3. Break deadline ties using priority.
    4. If nothing is available, advance to the next release time.

    Temperature is used only after scheduling to evaluate
    the resulting heat exposure. It does not influence
    scheduling decisions.
    """

    if not jobs:
        return []

    unscheduled = list(jobs)

    current_time = min(
        time_to_minutes(job.earliest_start)
        for job in unscheduled
    )

    schedule = []

    while unscheduled:
        available_jobs = [
            job
            for job in unscheduled
            if (
                time_to_minutes(
                    job.earliest_start
                )
                <= current_time
            )
        ]

        if not available_jobs:
            current_time = min(
                time_to_minutes(
                    job.earliest_start
                )
                for job in unscheduled
            )
            continue

        job = min(
            available_jobs,
            key=lambda candidate: (
                time_to_minutes(
                    candidate.deadline
                ),
                -candidate.priority,
            ),
        )

        start = current_time
        end = (
            start
            + job.duration_minutes
        )

        deadline = time_to_minutes(
            job.deadline
        )

        if end > deadline:
            raise RuntimeError(
                f"Baseline cannot schedule "
                f"{job.id} before its deadline."
            )

        heat_load, average_temperature = (
            calculate_heat_load(
                job,
                start,
                temperature_matrix,
            )
        )

        schedule.append(
            ScheduleAssignment(
                job_id=job.id,
                worker_id=worker_id,
                start_minute=start,
                end_minute=end,
                temperature_c=average_temperature,
                heat_load=heat_load,
            )
        )

        current_time = end
        unscheduled.remove(job)

    return schedule