from pathlib import Path

from heatops.domain.loaders import (
    load_jobs,
    load_temperature_matrix,
    load_workers,
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

JOBS_PATH = ROOT / "data" / "sample_jobs.json"

TEMPERATURE_PATH = ROOT / "data" / "temperature_matrix.json"

WORKERS_PATH = ROOT / "data" / "sample_workers.json"


jobs = load_jobs(JOBS_PATH)

temperature_matrix = load_temperature_matrix(TEMPERATURE_PATH)

worker = load_workers(WORKERS_PATH)[0]


baseline_result = build_baseline_schedule(
    jobs,
    temperature_matrix,
    worker=worker,
)

optimized_result = optimize_schedule(
    jobs,
    temperature_matrix,
    worker=worker,
)

baseline = baseline_result.assignments
optimized = optimized_result.assignments


baseline_heat_load = baseline_result.total_heat_load
optimized_heat_load = optimized_result.total_heat_load


if baseline_heat_load > 0:
    reduction = (baseline_heat_load - optimized_heat_load) / baseline_heat_load * 100
else:
    reduction = 0.0


job_names = {job.id: job.name for job in jobs}


print("\nHEATOPS EVALUATION")
print("=" * 60)

print(f"Baseline Heat Load : {baseline_heat_load:.2f}")

print(f"HeatOps Heat Load  : {optimized_heat_load:.2f}")

print(f"Heat Load Reduction: {reduction:.1f}%")

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
