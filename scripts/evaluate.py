from pathlib import Path

from heatops.domain.loaders import (
    load_jobs,
    load_temperature_matrix,
)
from heatops.domain.time_utils import (
    minutes_to_time,
)
from heatops.optimization.baseline import (
    build_baseline_schedule,
)
from heatops.optimization.scheduler import (
    optimize_schedule,
)

ROOT = Path(__file__).resolve().parents[1]

JOBS_PATH = (
    ROOT
    / "data"
    / "sample_jobs.json"
)

TEMPERATURE_PATH = (
    ROOT
    / "data"
    / "temperature_matrix.json"
)


jobs = load_jobs(JOBS_PATH)

temperature_matrix = (
    load_temperature_matrix(
        TEMPERATURE_PATH
    )
)


baseline = build_baseline_schedule(
    jobs,
    temperature_matrix,
)

optimized = optimize_schedule(
    jobs,
    temperature_matrix,
)


baseline_heat_load = sum(
    item.heat_load
    for item in baseline
)

optimized_heat_load = sum(
    item.heat_load
    for item in optimized
)


if baseline_heat_load > 0:
    reduction = (
        (
            baseline_heat_load
            - optimized_heat_load
        )
        / baseline_heat_load
        * 100
    )
else:
    reduction = 0.0


job_names = {
    job.id: job.name
    for job in jobs
}


print("\nHEATOPS EVALUATION")
print("=" * 60)

print(
    f"Baseline Heat Load : "
    f"{baseline_heat_load:.2f}"
)

print(
    f"HeatOps Heat Load  : "
    f"{optimized_heat_load:.2f}"
)

print(
    f"Heat Load Reduction: "
    f"{reduction:.1f}%"
)

print("=" * 60)


print("\nBASELINE SCHEDULE")

for item in baseline:
    print(
        f"{minutes_to_time(item.start_minute)}-"
        f"{minutes_to_time(item.end_minute)} | "
        f"{item.job_id} | "
        f"{job_names[item.job_id]:<25} | "
        f"{item.temperature_c:.2f}°C"
    )


print("\nHEATOPS SCHEDULE")

for item in optimized:
    print(
        f"{minutes_to_time(item.start_minute)}-"
        f"{minutes_to_time(item.end_minute)} | "
        f"{item.job_id} | "
        f"{job_names[item.job_id]:<25} | "
        f"{item.temperature_c:.2f}°C"
    )