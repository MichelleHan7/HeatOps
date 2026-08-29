from itertools import pairwise

from heatops.domain.config import SchedulerConfig
from heatops.domain.models import (
    Job,
    OptimizationResult,
    ScheduleAssignment,
    TemperatureMatrix,
)
from heatops.domain.time_utils import minutes_to_time, time_to_minutes
from heatops.evaluation.models import JobChange, ScheduleMetrics
from heatops.optimization.heat_risk import calculate_heat_load


def _jobs_by_id(jobs: list[Job]) -> dict[str, Job]:
    jobs_by_id = {job.id: job for job in jobs}

    if len(jobs_by_id) != len(jobs):
        raise ValueError("Job ids must be unique.")

    return jobs_by_id


def _assignments_by_job(
    result: OptimizationResult,
) -> dict[str, ScheduleAssignment]:
    assignments = {assignment.job_id: assignment for assignment in result.assignments}

    if len(assignments) != len(result.assignments):
        raise ValueError("A schedule cannot contain duplicate job assignments.")

    return assignments


def calculate_schedule_metrics(
    result: OptimizationResult,
    jobs: list[Job],
    temperature_matrix: TemperatureMatrix,
    config: SchedulerConfig | None = None,
) -> ScheduleMetrics:
    """Calculate comparable metrics from a completed schedule."""

    config = config or SchedulerConfig()
    jobs_by_id = _jobs_by_id(jobs)
    _assignments_by_job(result)
    total_heat_load = 0.0
    peak_temperature_c: float | None = None
    minutes_above_threshold = 0
    total_delay_hours = 0.0
    priority_weighted_delay_hours = 0.0

    for assignment in result.assignments:
        try:
            job = jobs_by_id[assignment.job_id]
        except KeyError as error:
            raise ValueError(
                f"Schedule contains unknown job {assignment.job_id!r}."
            ) from error

        heat = calculate_heat_load(
            job,
            assignment.start_minute,
            temperature_matrix,
            config,
        )
        delay_hours = (
            assignment.start_minute - time_to_minutes(job.earliest_start)
        ) / 60

        total_heat_load += heat.heat_load
        minutes_above_threshold += heat.minutes_above_threshold
        total_delay_hours += delay_hours
        priority_weighted_delay_hours += delay_hours * job.priority
        peak_temperature_c = (
            heat.peak_temperature_c
            if peak_temperature_c is None
            else max(peak_temperature_c, heat.peak_temperature_c)
        )

    ordered = sorted(result.assignments, key=lambda assignment: assignment.start_minute)
    idle_minutes = sum(
        max(0, following.start_minute - current.end_minute)
        for current, following in pairwise(ordered)
    )

    return ScheduleMetrics(
        total_heat_load=total_heat_load,
        peak_temperature_c=peak_temperature_c,
        minutes_above_threshold=minutes_above_threshold,
        total_delay_hours=total_delay_hours,
        priority_weighted_delay_hours=priority_weighted_delay_hours,
        idle_minutes=idle_minutes,
        scheduled_jobs=len(result.assignments),
    )


def _change_explanation(
    job_id: str,
    baseline: ScheduleAssignment,
    optimized: ScheduleAssignment,
) -> str:
    if baseline.start_minute == optimized.start_minute:
        return (
            f"{job_id} stayed at {minutes_to_time(baseline.start_minute)}; "
            "the selected optimization mode did not move it."
        )

    direction = "later" if optimized.start_minute > baseline.start_minute else "earlier"
    heat_delta = optimized.heat_load - baseline.heat_load
    temperature_delta = optimized.temperature_c - baseline.temperature_c
    heat_effect = "reducing" if heat_delta < 0 else "increasing"

    return (
        f"{job_id} moved {direction} from {minutes_to_time(baseline.start_minute)} "
        f"to {minutes_to_time(optimized.start_minute)}, changing its scheduled "
        f"temperature by {temperature_delta:+.2f} C and {heat_effect} its "
        f"operational Heat Load by {abs(heat_delta):.2f}."
    )


def build_job_changes(
    baseline_result: OptimizationResult,
    optimized_result: OptimizationResult,
) -> tuple[JobChange, ...]:
    """Create stable, job-level comparison records for two schedules."""

    baseline = _assignments_by_job(baseline_result)
    optimized = _assignments_by_job(optimized_result)

    if baseline.keys() != optimized.keys():
        raise ValueError("Baseline and optimized schedules must contain the same jobs.")

    changes = []

    for job_id in sorted(baseline):
        before = baseline[job_id]
        after = optimized[job_id]
        start_delta = after.start_minute - before.start_minute

        changes.append(
            JobChange(
                job_id=job_id,
                baseline_start_minute=before.start_minute,
                optimized_start_minute=after.start_minute,
                start_delta_minutes=start_delta,
                baseline_temperature_c=before.temperature_c,
                optimized_temperature_c=after.temperature_c,
                temperature_delta_c=after.temperature_c - before.temperature_c,
                baseline_heat_load=before.heat_load,
                optimized_heat_load=after.heat_load,
                heat_load_delta=after.heat_load - before.heat_load,
                moved=start_delta != 0,
                explanation=_change_explanation(job_id, before, after),
            )
        )

    return tuple(changes)
