"""Development-only paired heat-cache build-time measurement (not held-out)."""

import csv
from pathlib import Path

from heatops.benchmark.scenario_generator import generate_scenario
from heatops.domain.config import SchedulerConfig
from heatops.optimization.multi_crew import optimize_multi_crew


def main():
    s = generate_scenario(100, 10, 42)
    rows = []
    for repeat in range(5):
        # Alternate order to reduce warm-up/order bias.
        for cache in (False, True) if repeat % 2 == 0 else (True, False):
            r = optimize_multi_crew(
                s.jobs,
                s.workers,
                s.temperature_matrix,
                policy="balanced",
                config=SchedulerConfig(solver_time_limit_seconds=0.01),
                cache_heat=cache,
                hints=s.witness,
            )
            rows.append(
                {
                    "repeat": repeat,
                    "cache_heat": cache,
                    "seed": 42,
                    "jobs": 100,
                    "crews": 10,
                    "build_seconds": r.build_seconds,
                    "solve_seconds": r.solve_seconds,
                    "candidates": r.candidate_count,
                    "variables": r.variable_count,
                    "constraints": r.constraint_count,
                }
            )
    Path("reports").mkdir(exist_ok=True)
    with Path("reports/profiling.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(rows)


if __name__ == "__main__":
    main()
