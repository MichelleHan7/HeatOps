from heatops.domain.config import SchedulerConfig
from heatops.domain.time_utils import time_to_minutes
from heatops.evaluation.fleet import validate_schedule
from heatops.optimization.heat_risk import calculate_heat_load
from heatops.optimization.multi_crew import _validate_inputs


def validate_scenario(scenario):
    _validate_inputs(scenario.jobs, scenario.workers)
    if not scenario.metadata.get("source"):
        raise ValueError("Scenario must declare its temperature source")
    for job in scenario.jobs:
        first, last = time_to_minutes(job.earliest_start), time_to_minutes(job.deadline)
        if first + job.duration_minutes > last:
            raise ValueError(f"{job.id}: duration exceeds time window")
        # Check every minute to cover all potential worker-specific start offsets.
        # Hourly records covering the full window suffice for interpolation.
        temps = scenario.temperature_matrix[job.id]["temperatures"]
        from math import isfinite

        for hour in range(first // 60, (last + 59) // 60 + 1):
            value = temps.get(f"{hour:02d}:00")
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError(f"Missing/nonfinite hourly temperature for {job.id}")
        calculate_heat_load(job, first, scenario.temperature_matrix, SchedulerConfig())
    if scenario.witness:
        errors = validate_schedule(
            scenario.jobs,
            scenario.workers,
            scenario.temperature_matrix,
            scenario.witness,
        )
        if errors:
            raise ValueError(f"Invalid feasibility witness: {errors}")
