"""Independent feasibility/metric evaluation; no dependency on CP-SAT variables."""

from collections import Counter
from dataclasses import asdict
from math import isclose

from heatops.domain.config import SchedulerConfig
from heatops.domain.time_utils import time_to_minutes as minute
from heatops.optimization.heat_risk import calculate_heat_load
from heatops.optimization.multi_crew import SUCCESS, optimize_multi_crew
from heatops.optimization.travel import TravelConfig


def validate_schedule(
    jobs,
    workers,
    matrix,
    assignments,
    *,
    config=None,
    travel=None,
    delay_limit_minutes=None,
):
    config, travel = config or SchedulerConfig(), travel or TravelConfig()
    errors = []
    jm, wm = {j.id: j for j in jobs}, {w.id: w for w in workers}
    counts = Counter(a.job_id for a in assignments)
    if counts != Counter(j.id for j in jobs):
        errors.append(
            "Jobs must appear exactly once; missing, duplicate or unknown jobs"
        )
    delay = 0
    for a in assignments:
        if a.job_id not in jm or a.worker_id not in wm:
            errors.append("Unknown job or worker")
            continue
        j, w = jm[a.job_id], wm[a.worker_id]
        if a.end_minute - a.start_minute != j.duration_minutes:
            errors.append(f"{j.id}: wrong duration")
        if a.start_minute < max(
            minute(j.earliest_start), minute(w.shift_start)
        ) or a.end_minute > min(minute(j.deadline), minute(w.shift_end)):
            errors.append(f"{j.id}: window or shift violation")
        origin = max(minute(j.earliest_start), minute(w.shift_start))
        if (a.start_minute - origin) % config.slot_minutes:
            errors.append(f"{j.id}: start is off grid")
        if j.required_skill and j.required_skill not in w.skills:
            errors.append(f"{j.id}: missing skill")
        if any(
            a.start_minute < minute(e) and a.end_minute > minute(s)
            for s, e in w.unavailable
        ):
            errors.append(f"{j.id}: worker unavailable")
        heat = calculate_heat_load(j, a.start_minute, matrix, config)
        if not isclose(a.heat_load, heat.heat_load, abs_tol=1e-7) or not isclose(
            a.temperature_c, heat.average_temperature_c, abs_tol=1e-7
        ):
            errors.append(f"{j.id}: inconsistent heat metrics")
        delay += (a.start_minute - minute(j.earliest_start)) * j.priority
    for w in workers:
        route = sorted(
            (a for a in assignments if a.worker_id == w.id and a.job_id in jm),
            key=lambda a: a.start_minute,
        )
        end, loc, previous = (
            minute(w.shift_start),
            (w.start_latitude, w.start_longitude),
            f"depot:{w.id}",
        )
        for a in route:
            j = jm[a.job_id]
            _, duration = (
                travel.leg(previous, j.id, loc, (j.latitude, j.longitude))
                if travel.enabled
                else (0, 0)
            )
            if a.start_minute < end + duration:
                errors.append(f"{w.id}/{j.id}: overlap or insufficient travel")
            end, loc, previous = a.end_minute, (j.latitude, j.longitude), j.id
    if delay_limit_minutes is not None and delay > delay_limit_minutes:
        errors.append("Weighted delay budget exceeded")
    return errors


def fleet_metrics(jobs, workers, matrix, result, *, config=None, travel=None):
    travel = travel or TravelConfig()
    errors = (
        validate_schedule(
            jobs,
            workers,
            matrix,
            result.assignments,
            config=config,
            travel=travel,
            delay_limit_minutes=result.delay_limit_minutes,
        )
        if result.status in SUCCESS
        else []
    )
    jm = {j.id: j for j in jobs}
    per_worker, distances, travel_times = {}, {}, {}
    for w in workers:
        route = sorted(
            (a for a in result.assignments if a.worker_id == w.id),
            key=lambda a: a.start_minute,
        )
        busy = sum(a.end_minute - a.start_minute for a in route)
        # Union unavailable blocks to avoid double-subtraction.
        blocked = set()
        for s, e in w.unavailable:
            blocked.update(
                range(
                    max(minute(s), minute(w.shift_start)),
                    min(minute(e), minute(w.shift_end)),
                )
            )
        available = minute(w.shift_end) - minute(w.shift_start) - len(blocked)
        per_worker[w.id] = busy / available if available else 0
        distance, duration = 0.0, 0
        loc, previous = (w.start_latitude, w.start_longitude), f"depot:{w.id}"
        if travel.enabled:
            for a in route:
                j = jm[a.job_id]
                d, t = travel.leg(previous, j.id, loc, (j.latitude, j.longitude))
                distance, duration = distance + d, duration + t
                loc, previous = (j.latitude, j.longitude), j.id
        distances[w.id], travel_times[w.id] = distance, duration
    successful = result.status in SUCCESS
    return {
        "scheduled_jobs": len(result.assignments),
        "constraint_violations": len(errors),
        "violations": errors,
        "deadline_satisfaction": (
            sum(
                a.end_minute <= minute(jm[a.job_id].deadline)
                for a in result.assignments
            )
            / len(jobs)
        )
        if successful and jobs
        else None,
        "crew_utilization": per_worker,
        "estimated_travel_km": sum(distances.values()) if travel.enabled else None,
        "estimated_travel_minutes": sum(travel_times.values())
        if travel.enabled
        else None,
        "travel_km_per_worker": distances if travel.enabled else {},
        "operational_span_minutes": max(
            (a.end_minute for a in result.assignments), default=0
        )
        - min(
            (
                minute(w.shift_start)
                for w in workers
                if any(a.worker_id == w.id for a in result.assignments)
            ),
            default=0,
        ),
    }


def compare_fleet(
    jobs,
    workers,
    matrix,
    *,
    policies=("heat_first", "balanced", "delay_budget"),
    config=None,
    travel=None,
    additional_delay_minutes=60,
    initial_schedule=(),
):
    if (
        isinstance(additional_delay_minutes, bool)
        or not isinstance(additional_delay_minutes, int)
        or additional_delay_minutes < 0
    ):
        raise ValueError("Additional weighted delay must be a nonnegative integer")
    baseline = optimize_multi_crew(
        jobs,
        workers,
        matrix,
        policy="operations_first",
        config=config,
        travel=travel,
        hints=initial_schedule,
    )
    results = {"operations_first": baseline}
    for policy in dict.fromkeys(policies):
        if policy == "operations_first":
            continue
        if policy == "delay_budget" and baseline.status not in SUCCESS:
            continue
        limit = (
            baseline.weighted_delay_minutes + additional_delay_minutes
            if policy == "delay_budget"
            else None
        )
        results[policy] = optimize_multi_crew(
            jobs,
            workers,
            matrix,
            policy=policy,
            config=config,
            travel=travel,
            delay_limit_minutes=limit,
            hints=baseline.assignments,
        )
    payload = {}
    for policy, result in results.items():
        reduction = None
        if (
            baseline.status in SUCCESS
            and result.status in SUCCESS
            and baseline.total_heat_load > 0
        ):
            reduction = (
                100
                * (baseline.total_heat_load - result.total_heat_load)
                / baseline.total_heat_load
            )
        payload[policy] = {
            "result": asdict(result),
            "metrics": fleet_metrics(
                jobs, workers, matrix, result, config=config, travel=travel
            ),
            "heat_reduction_percent": reduction,
            "baseline_proven_optimal": baseline.status == "OPTIMAL",
        }
    return payload
