from heatops.domain.config import SchedulerConfig
from heatops.domain.models import (
    Job,
    OptimizationWeights,
    TemperatureMatrix,
    Worker,
)
from heatops.evaluation.metrics import build_job_changes, calculate_schedule_metrics
from heatops.evaluation.models import ScheduleComparison
from heatops.optimization.baseline import build_baseline_schedule
from heatops.optimization.scheduler import optimize_schedule


def compare_schedules(
    jobs: list[Job],
    temperature_matrix: TemperatureMatrix,
    worker: Worker | None = None,
    weights: OptimizationWeights | None = None,
    config: SchedulerConfig | None = None,
) -> ScheduleComparison:
    """Run a fair baseline/optimized comparison through the shared scheduler."""

    config = config or SchedulerConfig()
    baseline_result = build_baseline_schedule(
        jobs,
        temperature_matrix,
        worker=worker,
        config=config,
    )
    optimized_result = optimize_schedule(
        jobs,
        temperature_matrix,
        weights=weights,
        worker=worker,
        config=config,
    )
    baseline_metrics = calculate_schedule_metrics(
        baseline_result,
        jobs,
        temperature_matrix,
        config,
    )
    optimized_metrics = calculate_schedule_metrics(
        optimized_result,
        jobs,
        temperature_matrix,
        config,
    )
    job_changes = build_job_changes(baseline_result, optimized_result)
    reduction_percent = 0.0

    if baseline_metrics.total_heat_load > 0:
        reduction_percent = (
            (baseline_metrics.total_heat_load - optimized_metrics.total_heat_load)
            / baseline_metrics.total_heat_load
            * 100
        )

    return ScheduleComparison(
        baseline_result=baseline_result,
        optimized_result=optimized_result,
        baseline_metrics=baseline_metrics,
        optimized_metrics=optimized_metrics,
        heat_load_reduction_percent=reduction_percent,
        moved_jobs=sum(change.moved for change in job_changes),
        job_changes=job_changes,
    )
