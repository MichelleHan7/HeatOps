from dataclasses import replace

import pytest

from heatops.benchmark.scenario_generator import generate_scenario
from heatops.domain.config import SchedulerConfig
from heatops.evaluation.fleet import compare_fleet, validate_schedule
from heatops.optimization.multi_crew import optimize_multi_crew
from heatops.optimization.travel import TravelConfig, haversine_km


def solve(s, **kwargs):
    return optimize_multi_crew(s.jobs, s.workers, s.temperature_matrix, **kwargs)


def check(s, r, **kwargs):
    assert r.status in ("OPTIMAL", "FEASIBLE")
    assert not validate_schedule(
        s.jobs, s.workers, s.temperature_matrix, r.assignments, **kwargs
    )


def test_parallel_skilled_crews_and_unique_jobs():
    s = generate_scenario(2, 2)
    s.jobs = [
        replace(
            j,
            earliest_start="07:00",
            deadline="08:00",
            duration_minutes=60,
            required_skill=s.workers[i].skills[1],
        )
        for i, j in enumerate(s.jobs)
    ]
    r = solve(s)
    check(s, r)
    assert len({a.worker_id for a in r.assignments}) == 2
    assert {a.start_minute for a in r.assignments} == {420}


def test_availability_shifts_deadlines_deterministic():
    s = generate_scenario(5, 2)
    s.workers = [replace(w, unavailable=(("07:00", "08:00"),)) for w in s.workers]
    s.jobs = [replace(j, deadline="19:00") for j in s.jobs]
    a, b = solve(s), solve(s)
    check(s, a)
    assert a.assignments == b.assignments
    assert min(x.start_minute for x in a.assignments) >= 480


def test_infeasible_and_invalid_ids():
    s = generate_scenario(5, 2, infeasible=True)
    assert solve(s).status == "INFEASIBLE"
    s.jobs.append(s.jobs[0])
    with pytest.raises(ValueError, match="unique"):
        solve(s)


def test_delay_budget_and_fair_baseline():
    s = generate_scenario(10, 2, seed=12)
    p = compare_fleet(
        s.jobs, s.workers, s.temperature_matrix, additional_delay_minutes=30
    )
    assert (
        p["delay_budget"]["result"]["weighted_delay_minutes"]
        <= p["operations_first"]["result"]["weighted_delay_minutes"] + 30
    )
    assert all(v["metrics"]["constraint_violations"] == 0 for v in p.values())
    assert (
        p["heat_first"]["result"]["total_heat_load"]
        <= p["operations_first"]["result"]["total_heat_load"] + 0.01
    )


def test_validator_detects_missing_duplicate_wrong_worker_and_heat():
    s = generate_scenario(5, 2)
    r = solve(s)
    for rows in (
        r.assignments[:-1],
        r.assignments + r.assignments[:1],
        (replace(r.assignments[0], worker_id="bad"),) + r.assignments[1:],
        (replace(r.assignments[0], heat_load=999),) + r.assignments[1:],
    ):
        assert validate_schedule(s.jobs, s.workers, s.temperature_matrix, rows)


def test_timeout_not_infeasible_and_zero_heat():
    s = generate_scenario(25, 5, family="mild")
    r = solve(s, config=SchedulerConfig(solver_time_limit_seconds=1e-6))
    assert r.status == "UNKNOWN"
    assert r.total_heat_load is None
    s = generate_scenario(5, 2, family="mild")
    assert all(
        x["heat_reduction_percent"] is None
        for x in compare_fleet(s.jobs, s.workers, s.temperature_matrix).values()
    )


def test_empty_and_single_job():
    assert optimize_multi_crew([], [], {}).status == "OPTIMAL"
    s = generate_scenario(1, 1)
    check(s, solve(s))


def test_travel_distance_and_depot_constraint():
    assert haversine_km((0, 0), (0, 1)) == pytest.approx(111.195, abs=0.01)
    assert haversine_km((1, 2), (1, 2)) == 0
    s = generate_scenario(1, 1)
    travel = TravelConfig(enabled=True, minutes_matrix={("depot:W00", "J000"): 60})
    r = solve(s, travel=travel)
    check(s, r, travel=travel)
    assert r.assignments[0].start_minute >= 480


def test_directed_nonmetric_travel_only_consecutive_legs():
    s = generate_scenario(3, 1)
    # A->C is deliberately impossible directly; route A->B->C remains feasible.
    s.jobs = [
        replace(
            j,
            required_skill="general",
            earliest_start=t,
            deadline=e,
            duration_minutes=15,
        )
        for j, t, e in zip(
            s.jobs, ("08:00", "09:00", "10:00"), ("08:15", "09:15", "10:15")
        )
    ]
    travel = TravelConfig(enabled=True, minutes_matrix={("J000", "J002"): 600})
    r = solve(s, travel=travel)
    check(s, r, travel=travel)
    assert [a.job_id for a in r.assignments] == ["J000", "J001", "J002"]


def test_impossible_travel_and_safeguard():
    s = generate_scenario(1, 1)
    assert (
        solve(
            s,
            travel=TravelConfig(
                enabled=True, minutes_matrix={("depot:W00", "J000"): 1000}
            ),
        ).status
        == "INFEASIBLE"
    )
    s = generate_scenario(50, 5)
    with pytest.raises(ValueError, match="at most"):
        solve(s, travel=TravelConfig(enabled=True))


def test_legacy_single_worker_honors_new_availability_field():
    from heatops.optimization.scheduler import optimize_schedule

    s = generate_scenario(1, 1)
    s.jobs = [replace(s.jobs[0], deadline="19:00")]
    w = replace(s.workers[0], unavailable=(("07:00", "08:00"),))
    r = optimize_schedule(s.jobs, s.temperature_matrix, worker=w)
    assert r.assignments[0].start_minute >= 480
