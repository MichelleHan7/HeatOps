"""Multi-crew CP-SAT engine; legacy scheduler remains unchanged."""

from dataclasses import dataclass
from math import isfinite
from time import perf_counter

from ortools.sat.python import cp_model

from heatops.domain.config import SchedulerConfig
from heatops.domain.models import Job, ScheduleAssignment, TemperatureMatrix, Worker
from heatops.domain.time_utils import time_to_minutes as minute
from heatops.optimization.heat_risk import calculate_heat_load
from heatops.optimization.travel import TravelConfig

POLICIES = ("operations_first", "heat_first", "balanced", "delay_budget")
SUCCESS = ("OPTIMAL", "FEASIBLE")


@dataclass(frozen=True)
class FleetResult:
    assignments: tuple[ScheduleAssignment, ...]
    status: str
    message: str
    policy: str
    total_heat_load: float | None = None
    total_delay_hours: float | None = None
    weighted_delay_minutes: int | None = None
    objective_value: float | None = None
    objective_bound: float | None = None
    relative_gap: float | None = None
    runtime_seconds: float = 0.0
    build_seconds: float = 0.0
    solve_seconds: float = 0.0
    candidate_count: int = 0
    variable_count: int = 0
    constraint_count: int = 0
    delay_limit_minutes: int | None = None


def _validate_inputs(jobs, workers):
    for collection, label in ((jobs, "Job"), (workers, "Worker")):
        ids = [x.id for x in collection]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{label} IDs must be unique")
    if jobs and not workers:
        raise ValueError("At least one worker is required")


def optimize_multi_crew(
    jobs: list[Job],
    workers: list[Worker],
    temperature_matrix: TemperatureMatrix,
    *,
    policy: str = "balanced",
    config: SchedulerConfig | None = None,
    travel: TravelConfig | None = None,
    delay_limit_minutes: int | None = None,
    heat_weight: float = 0.5,
    hints: tuple[ScheduleAssignment, ...] = (),
    cache_heat: bool = True,
) -> FleetResult:
    """Assign every job exactly once or return an explicit non-success status.

    Objective units: integer costs after global candidate min-max normalization,
    with a bounded secondary assignment/start preference. Bound/gap refer to that
    exact integer objective, not directly to Heat Load. One search thread and a
    fixed seed are used; wall-clock cutoffs can still change FEASIBLE incumbents.
    """
    clock = perf_counter()
    config, travel = config or SchedulerConfig(), travel or TravelConfig()
    _validate_inputs(jobs, workers)
    if policy not in POLICIES:
        raise ValueError(f"Unknown policy: {policy}")
    if not isfinite(heat_weight) or not 0 <= heat_weight <= 1:
        raise ValueError("heat_weight must be in [0, 1]")
    if policy == "delay_budget" and delay_limit_minutes is None:
        raise ValueError("delay_budget requires an explicit weighted-minute limit")
    if delay_limit_minutes is not None and (
        isinstance(delay_limit_minutes, bool)
        or not isinstance(delay_limit_minutes, int)
        or delay_limit_minutes < 0
    ):
        raise ValueError("Delay limit must be a nonnegative integer")
    if travel.enabled and len(jobs) > travel.max_jobs:
        raise ValueError(
            f"Travel mode supports at most {travel.max_jobs} jobs; use scheduling-only"
        )
    jobs, workers = (
        sorted(jobs, key=lambda j: j.id),
        sorted(workers, key=lambda w: w.id),
    )
    if not jobs:
        return FleetResult((), "OPTIMAL", "Empty workload", policy, 0, 0, 0, 0, 0, 0)

    model = cp_model.CpModel()
    starts, presence, candidates = {}, {}, []
    intervals = {w.id: [] for w in workers}
    hint_keys = {(a.job_id, a.worker_id, a.start_minute) for a in hints}
    for job in jobs:
        choices = []
        cache = {}
        start = model.new_int_var(0, 1440, f"start_{job.id}")
        starts[job.id] = start
        for wi, worker in enumerate(workers):
            if job.required_skill and job.required_skill not in worker.skills:
                continue
            first = max(minute(job.earliest_start), minute(worker.shift_start))
            last = (
                min(minute(job.deadline), minute(worker.shift_end))
                - job.duration_minutes
            )
            worker_choices = []
            for t in range(first, last + 1, config.slot_minutes):
                if any(
                    t < minute(end) and t + job.duration_minutes > minute(begin)
                    for begin, end in worker.unavailable
                ):
                    continue
                key = (job.id, worker.id, t)
                x = model.new_bool_var(f"x_{job.id}_{worker.id}_{t}")
                if not cache_heat or t not in cache:
                    cache[t] = calculate_heat_load(job, t, temperature_matrix, config)
                heat = cache[t]
                delay = (t - minute(job.earliest_start)) * job.priority
                record = (job, worker, t, x, heat, delay, t * len(workers) + wi)
                candidates.append(record)
                choices.append(record)
                worker_choices.append(x)
                if hint_keys:
                    model.add_hint(x, int(key in hint_keys))
            if worker_choices:
                active = model.new_bool_var(f"assigned_{job.id}_{worker.id}")
                model.add(sum(worker_choices) == active)
                presence[job.id, worker.id] = active
                end = model.new_int_var(0, 1440, f"end_{job.id}_{worker.id}")
                intervals[worker.id].append(
                    model.new_optional_interval_var(
                        start,
                        job.duration_minutes,
                        end,
                        active,
                        f"work_{job.id}_{worker.id}",
                    )
                )
        if not choices:
            return FleetResult(
                (),
                "INFEASIBLE",
                f"No qualified, available start for {job.id}",
                policy,
                runtime_seconds=perf_counter() - clock,
            )
        model.add_exactly_one(c[3] for c in choices)
        model.add(start == sum(c[2] * c[3] for c in choices))
    for worker in workers:
        model.add_no_overlap(intervals[worker.id])

    if travel.enabled:
        for worker in workers:
            eligible = [j for j in jobs if (j.id, worker.id) in presence]
            empty = model.new_bool_var(f"empty_{worker.id}")
            active_vars = [presence[j.id, worker.id] for j in eligible]
            model.add(sum(active_vars) == 0).only_enforce_if(empty)
            model.add(sum(active_vars) >= 1).only_enforce_if(empty.Not())
            arcs = [(0, 0, empty)]
            depot = (worker.start_latitude, worker.start_longitude)
            for i, job in enumerate(eligible, 1):
                active = presence[job.id, worker.id]
                arcs.append((i, i, active.Not()))
                first = model.new_bool_var(f"first_{worker.id}_{job.id}")
                last = model.new_bool_var(f"last_{worker.id}_{job.id}")
                arcs.extend(((0, i, first), (i, 0, last)))
                _, duration = travel.leg(
                    f"depot:{worker.id}", job.id, depot, (job.latitude, job.longitude)
                )
                model.add(
                    starts[job.id] >= minute(worker.shift_start) + duration
                ).only_enforce_if(first)
                for k, other in enumerate(eligible, 1):
                    if i == k:
                        continue
                    arc = model.new_bool_var(f"arc_{worker.id}_{job.id}_{other.id}")
                    arcs.append((i, k, arc))
                    _, duration = travel.leg(
                        job.id,
                        other.id,
                        (job.latitude, job.longitude),
                        (other.latitude, other.longitude),
                    )
                    model.add(
                        starts[other.id]
                        >= starts[job.id] + job.duration_minutes + duration
                    ).only_enforce_if(arc)
            model.add_circuit(arcs)

    delay_expr = sum(c[5] * c[3] for c in candidates)
    if delay_limit_minutes is not None:
        model.add(delay_expr <= delay_limit_minutes)
    heat_values, delay_values = (
        [c[4].heat_load for c in candidates],
        [c[5] for c in candidates],
    )
    hmin, hmax, dmin, dmax = (
        min(heat_values),
        max(heat_values),
        min(delay_values),
        max(delay_values),
    )
    weight = {"operations_first": 0, "heat_first": 1, "delay_budget": 1}.get(
        policy, heat_weight
    )
    # Tie preference cannot outweigh one integer unit of the primary objective.
    tie_scale = len(jobs) * (1441 * len(workers)) + 1
    costs = []
    for c in candidates:
        h = (c[4].heat_load - hmin) / (hmax - hmin) if hmax > hmin else 0
        d = (c[5] - dmin) / (dmax - dmin) if dmax > dmin else 0
        # Operations baseline minimizes exact weighted delay, without rounding.
        primary = (
            c[5]
            if policy == "operations_first"
            else round(config.objective_scale * (weight * h + (1 - weight) * d))
        )
        costs.append((primary * tie_scale + c[6]) * c[3])
    model.minimize(sum(costs))
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = config.random_seed
    solver.parameters.max_time_in_seconds = config.solver_time_limit_seconds
    built = perf_counter()
    status = solver.solve(model)
    finished = perf_counter()
    diagnostics = {
        "runtime_seconds": finished - clock,
        "build_seconds": built - clock,
        "solve_seconds": finished - built,
        "candidate_count": len(candidates),
        "variable_count": len(model.Proto().variables),
        "constraint_count": len(model.Proto().constraints),
        "delay_limit_minutes": delay_limit_minutes,
    }
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return FleetResult(
            (),
            solver.status_name(status),
            "Proven infeasible"
            if status == cp_model.INFEASIBLE
            else "No incumbent; inspect status/time limit",
            policy,
            **diagnostics,
        )
    selected = [c for c in candidates if solver.value(c[3])]
    assignments = tuple(
        sorted(
            (
                ScheduleAssignment(
                    job_id=c[0].id,
                    worker_id=c[1].id,
                    start_minute=c[2],
                    end_minute=c[2] + c[0].duration_minutes,
                    temperature_c=c[4].average_temperature_c,
                    heat_load=c[4].heat_load,
                )
                for c in selected
            ),
            key=lambda a: (a.worker_id, a.start_minute, a.job_id),
        )
    )
    objective, bound = solver.objective_value, solver.best_objective_bound
    return FleetResult(
        assignments,
        solver.status_name(status),
        "Schedule found",
        policy,
        sum(a.heat_load for a in assignments),
        sum(
            a.start_minute
            - minute(next(j for j in jobs if j.id == a.job_id).earliest_start)
            for a in assignments
        )
        / 60,
        sum(c[5] for c in selected),
        objective,
        bound,
        max(0, objective - bound) / max(1, abs(objective)),
        **diagnostics,
    )
