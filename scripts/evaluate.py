from heatops.optimization.baseline import build_baseline_schedule
from heatops.optimization.scheduler import optimize_schedule

baseline = build_baseline_schedule()
optimized = optimize_schedule()


baseline_heat_load = sum(
    item["heat_load"]
    for item in baseline
)

optimized_heat_load = sum(
    item["heat_load"]
    for item in optimized
)


reduction = (
    (baseline_heat_load - optimized_heat_load)
    / baseline_heat_load
    * 100
)


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
        f'{item["start"]}-{item["end"]} | '
        f'{item["id"]} | '
        f'{item["average_temperature"]:.2f}°C'
    )


print("\nHEATOPS SCHEDULE")

for item in optimized:
    print(
        f'{item["start"]}-{item["end"]} | '
        f'{item["id"]} | '
        f'{item["average_temperature"]:.2f}°C'
    )