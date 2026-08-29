from heatops.domain.config import SchedulerConfig
from heatops.domain.models import (
    Job,
    OptimizationResult,
    TemperatureMatrix,
    Worker,
)
from heatops.optimization.presets import OPERATIONS_FIRST
from heatops.optimization.scheduler import optimize_schedule


def build_baseline_schedule(
    jobs: list[Job],
    temperature_matrix: TemperatureMatrix,
    worker: Worker | None = None,
    config: SchedulerConfig | None = None,
) -> OptimizationResult:
    """Build a fair temperature-unaware, operations-first baseline.

    The baseline uses the same feasibility model as HeatOps but assigns zero
    weight to heat exposure. Temperature is evaluated only after the schedule
    is chosen so the before/after comparison changes one decision factor.
    """

    return optimize_schedule(
        jobs,
        temperature_matrix,
        weights=OPERATIONS_FIRST,
        worker=worker,
        config=config,
    )
