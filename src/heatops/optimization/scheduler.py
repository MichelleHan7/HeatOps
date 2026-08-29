from dataclasses import dataclass

from ortools.sat.python import cp_model

from heatops.domain.config import SchedulerConfig
from heatops.domain.models import (
    Job,
    OptimizationResult,
    OptimizationWeights,
    ScheduleAssignment,
    TemperatureMatrix,
    Worker,
)
from heatops.domain.time_utils import time_to_minutes
from heatops.optimization.heat_risk import HeatLoadResult, calculate_heat_load


@dataclass(frozen=True)
class _Candidate:
    job: Job
    start_minute: int
    start_index: int
    variable: cp_model.IntVar
    heat: HeatLoadResult
    delay_hours: float
    priority_weighted_delay: float


def _normalized_value(value: float, minimum: float, maximum: float) -> float:
    if maximum == minimum:
        return 0.0

    return (value - minimum) / (maximum - minimum)


def _validate_job_ids(jobs: list[Job]) -> None:
    job_ids = [job.id for job in jobs]

    if len(job_ids) != len(set(job_ids)):
        raise ValueError("Job ids must be unique.")


def _validate_worker_skills(jobs: list[Job], worker: Worker | None) -> None:
    if worker is None:
        return

    worker_skills = set(worker.skills)

    for job in jobs:
        if job.required_skill and job.required_skill not in worker_skills:
            raise RuntimeError(
                f"{worker.id} does not have the required skill "
                f"{job.required_skill!r} for {job.id}."
            )


def optimize_schedule(
    jobs: list[Job],
    temperature_matrix: TemperatureMatrix,
    weights: OptimizationWeights | None = None,
    worker: Worker | None = None,
    config: SchedulerConfig | None = None,
) -> OptimizationResult:
    """Build a deterministic, single-crew heat-aware schedule.

    The objective combines scenario-normalized heat exposure and
    priority-weighted operational delay. Raw metrics remain available on the
    returned result. Heat Load is an operational score, not a medical risk
    assessment.
    """

    config = config or SchedulerConfig()
    weights = weights or OptimizationWeights()

    if not jobs:
        return OptimizationResult(
            assignments=(),
            status="OPTIMAL",
            objective_value=0.0,
            total_heat_load=0.0,
            total_delay_hours=0.0,
        )

    _validate_job_ids(jobs)
    _validate_worker_skills(jobs, worker)

    shift_start = time_to_minutes(
        worker.shift_start if worker else config.default_shift_start
    )
    shift_end = time_to_minutes(
        worker.shift_end if worker else config.default_shift_end
    )
    worker_id = worker.id if worker else config.default_worker_id

    model = cp_model.CpModel()
    candidates: list[_Candidate] = []
    candidates_by_job: dict[str, list[_Candidate]] = {}
    optional_intervals = []

    for job in jobs:
        earliest_start = max(
            time_to_minutes(job.earliest_start),
            shift_start,
        )
        latest_end = min(
            time_to_minutes(job.deadline),
            shift_end,
        )
        latest_start = latest_end - job.duration_minutes

        if latest_start < earliest_start:
            raise RuntimeError(
                f"{job.id} cannot fit inside its time window and worker shift."
            )

        job_candidates = []

        for start_index, start in enumerate(
            range(
                earliest_start,
                latest_start + 1,
                config.slot_minutes,
            )
        ):
            variable = model.NewBoolVar(f"select_{job.id}_{start}")
            interval = model.NewOptionalFixedSizeIntervalVar(
                start,
                job.duration_minutes,
                variable,
                f"interval_{job.id}_{start}",
            )
            heat = calculate_heat_load(
                job,
                start,
                temperature_matrix,
                config,
            )
            delay_hours = (start - time_to_minutes(job.earliest_start)) / 60
            candidate = _Candidate(
                job=job,
                start_minute=start,
                start_index=start_index,
                variable=variable,
                heat=heat,
                delay_hours=delay_hours,
                priority_weighted_delay=delay_hours * job.priority,
            )

            candidates.append(candidate)
            job_candidates.append(candidate)
            optional_intervals.append(interval)

        model.Add(sum(item.variable for item in job_candidates) == 1)
        candidates_by_job[job.id] = job_candidates

    model.AddNoOverlap(optional_intervals)

    heat_values = [item.heat.heat_load for item in candidates]
    delay_values = [item.priority_weighted_delay for item in candidates]
    heat_minimum, heat_maximum = min(heat_values), max(heat_values)
    delay_minimum, delay_maximum = min(delay_values), max(delay_values)
    heat_weight, delay_weight = weights.normalized()

    max_total_start_index = sum(
        max(item.start_index for item in job_candidates)
        for job_candidates in candidates_by_job.values()
    )
    tie_break_scale = max_total_start_index + 1
    integer_costs: dict[tuple[str, int], int] = {}
    normalized_costs: dict[tuple[str, int], float] = {}

    for item in candidates:
        normalized_heat = _normalized_value(
            item.heat.heat_load,
            heat_minimum,
            heat_maximum,
        )
        normalized_delay = _normalized_value(
            item.priority_weighted_delay,
            delay_minimum,
            delay_maximum,
        )
        normalized_cost = (
            heat_weight * normalized_heat + delay_weight * normalized_delay
        )
        primary_cost = round(normalized_cost * config.objective_scale)
        key = (item.job.id, item.start_minute)

        normalized_costs[key] = normalized_cost
        integer_costs[key] = primary_cost * tie_break_scale + item.start_index

    model.Minimize(
        sum(
            integer_costs[(item.job.id, item.start_minute)] * item.variable
            for item in candidates
        )
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = config.solver_time_limit_seconds
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = config.random_seed
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError("No feasible schedule found.")

    assignments = []
    selected_candidates = []

    for item in candidates:
        if solver.Value(item.variable):
            assignments.append(
                ScheduleAssignment(
                    job_id=item.job.id,
                    worker_id=worker_id,
                    start_minute=item.start_minute,
                    end_minute=item.start_minute + item.job.duration_minutes,
                    temperature_c=item.heat.average_temperature_c,
                    heat_load=item.heat.heat_load,
                )
            )
            selected_candidates.append(item)

    assignments.sort(key=lambda assignment: assignment.start_minute)

    return OptimizationResult(
        assignments=tuple(assignments),
        status=solver.StatusName(status),
        objective_value=sum(
            normalized_costs[(item.job.id, item.start_minute)]
            for item in selected_candidates
        ),
        total_heat_load=sum(item.heat.heat_load for item in selected_candidates),
        total_delay_hours=sum(item.delay_hours for item in selected_candidates),
    )
