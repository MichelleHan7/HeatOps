from dataclasses import dataclass

from heatops.domain.models import OptimizationResult


@dataclass(frozen=True)
class ScheduleMetrics:
    """Comparable operational metrics for one completed schedule."""

    total_heat_load: float
    peak_temperature_c: float | None
    minutes_above_threshold: int
    total_delay_hours: float
    priority_weighted_delay_hours: float
    idle_minutes: int
    scheduled_jobs: int


@dataclass(frozen=True)
class JobChange:
    """A deterministic before/after record for a single job."""

    job_id: str
    baseline_start_minute: int
    optimized_start_minute: int
    start_delta_minutes: int
    baseline_temperature_c: float
    optimized_temperature_c: float
    temperature_delta_c: float
    baseline_heat_load: float
    optimized_heat_load: float
    heat_load_delta: float
    moved: bool
    explanation: str


@dataclass(frozen=True)
class ScheduleComparison:
    """Baseline and optimized schedules plus presentation-neutral evidence."""

    baseline_result: OptimizationResult
    optimized_result: OptimizationResult
    baseline_metrics: ScheduleMetrics
    optimized_metrics: ScheduleMetrics
    heat_load_reduction_percent: float
    moved_jobs: int
    job_changes: tuple[JobChange, ...]
