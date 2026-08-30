from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite

from heatops.domain.models import (
    Job,
    OptimizationResult,
    OptimizationWeights,
    TemperatureMatrix,
)
from heatops.domain.time_utils import minutes_to_time, time_to_minutes
from heatops.evaluation.models import ScheduleComparison, ScheduleMetrics
from heatops.optimization.presets import PRESETS

MODE_LABELS = {
    "operations_first": "Operations-first",
    "balanced": "Balanced",
    "heat_first": "Heat-first",
}
MODE_ORDER = tuple(MODE_LABELS)


@dataclass(frozen=True)
class TimelineRecord:
    schedule: str
    job_id: str
    job_name: str
    worker_id: str
    start_minute: int
    end_minute: int
    start_time: str
    end_time: str
    duration_minutes: int
    temperature_c: float
    heat_load: float
    priority: int


@dataclass(frozen=True)
class MapMarkerRecord:
    schedule: str
    job_id: str
    job_name: str
    latitude: float
    longitude: float
    start_time: str
    temperature_c: float
    heat_load: float
    moved: bool


@dataclass(frozen=True)
class TemperatureCurveRecord:
    job_id: str
    job_name: str
    time_label: str
    minute: int
    temperature_c: float


@dataclass(frozen=True)
class MetricCardRecord:
    key: str
    label: str
    baseline_value: float | int | None
    optimized_value: float | int | None
    display_value: str
    display_delta: str
    unit: str
    help_text: str


@dataclass(frozen=True)
class JobChangeRecord:
    job_id: str
    job_name: str
    baseline_start: str
    optimized_start: str
    start_change: str
    temperature_change: str
    heat_load_change: str
    moved: bool
    explanation: str


@dataclass(frozen=True)
class TradeoffRecord:
    mode: str
    mode_label: str
    heat_weight_percent: float
    delay_weight_percent: float
    total_heat_load: float
    total_delay_hours: float
    priority_weighted_delay_hours: float
    moved_jobs: int


def _jobs_by_id(jobs: list[Job]) -> dict[str, Job]:
    jobs_by_id = {job.id: job for job in jobs}

    if len(jobs_by_id) != len(jobs):
        raise ValueError("Job ids must be unique.")

    return jobs_by_id


def _job_for(job_id: str, jobs_by_id: Mapping[str, Job]) -> Job:
    try:
        return jobs_by_id[job_id]
    except KeyError as error:
        raise ValueError(f"Schedule contains unknown job {job_id!r}.") from error


def build_timeline_records(
    result: OptimizationResult,
    jobs: list[Job],
    schedule_label: str,
) -> tuple[TimelineRecord, ...]:
    """Convert a schedule into deterministic, chart-library-neutral records."""

    if not result.assignments:
        return ()

    jobs_by_id = _jobs_by_id(jobs)
    records = []

    for assignment in sorted(
        result.assignments,
        key=lambda item: (item.start_minute, item.job_id),
    ):
        job = _job_for(assignment.job_id, jobs_by_id)
        records.append(
            TimelineRecord(
                schedule=schedule_label,
                job_id=job.id,
                job_name=job.name,
                worker_id=assignment.worker_id,
                start_minute=assignment.start_minute,
                end_minute=assignment.end_minute,
                start_time=minutes_to_time(assignment.start_minute),
                end_time=minutes_to_time(assignment.end_minute),
                duration_minutes=assignment.end_minute - assignment.start_minute,
                temperature_c=assignment.temperature_c,
                heat_load=assignment.heat_load,
                priority=job.priority,
            )
        )

    return tuple(records)


def build_map_marker_records(
    result: OptimizationResult,
    jobs: list[Job],
    schedule_label: str,
    moved_job_ids: set[str] | frozenset[str] | None = None,
) -> tuple[MapMarkerRecord, ...]:
    """Convert assignments into map markers with domain coordinates attached."""

    if not result.assignments:
        return ()

    jobs_by_id = _jobs_by_id(jobs)
    moved_job_ids = moved_job_ids or set()
    markers = []

    for assignment in sorted(
        result.assignments,
        key=lambda item: (item.start_minute, item.job_id),
    ):
        job = _job_for(assignment.job_id, jobs_by_id)
        markers.append(
            MapMarkerRecord(
                schedule=schedule_label,
                job_id=job.id,
                job_name=job.name,
                latitude=job.latitude,
                longitude=job.longitude,
                start_time=minutes_to_time(assignment.start_minute),
                temperature_c=assignment.temperature_c,
                heat_load=assignment.heat_load,
                moved=job.id in moved_job_ids,
            )
        )

    return tuple(markers)


def build_temperature_curve_records(
    jobs: list[Job],
    temperature_matrix: TemperatureMatrix,
) -> tuple[TemperatureCurveRecord, ...]:
    """Flatten the temperature matrix into stable job/time curve records."""

    if not jobs:
        return ()

    _jobs_by_id(jobs)
    records = []

    for job in sorted(jobs, key=lambda item: item.id):
        try:
            temperatures = temperature_matrix[job.id]["temperatures"]
        except (KeyError, TypeError) as error:
            raise ValueError(f"Temperature matrix is missing job {job.id}.") from error

        for time_label, temperature in sorted(
            temperatures.items(),
            key=lambda item: time_to_minutes(item[0]),
        ):
            if (
                isinstance(temperature, bool)
                or not isinstance(temperature, (int, float))
                or not isfinite(temperature)
            ):
                raise ValueError(
                    f"Temperature for {job.id} at {time_label} must be finite."
                )

            records.append(
                TemperatureCurveRecord(
                    job_id=job.id,
                    job_name=job.name,
                    time_label=time_label,
                    minute=time_to_minutes(time_label),
                    temperature_c=float(temperature),
                )
            )

    return tuple(records)


def _formatted_delta(
    baseline: float | None,
    optimized: float | None,
    unit: str,
    decimals: int,
) -> str:
    if baseline is None or optimized is None:
        return "N/A"

    delta = optimized - baseline
    suffix = f" {unit}" if unit else ""
    return f"{delta:+.{decimals}f}{suffix} vs baseline"


def _metric_card(
    *,
    key: str,
    label: str,
    baseline: float | None,
    optimized: float | None,
    unit: str,
    decimals: int,
    help_text: str,
) -> MetricCardRecord:
    if optimized is None:
        display_value = "N/A"
    else:
        suffix = f" {unit}" if unit else ""
        display_value = f"{optimized:.{decimals}f}{suffix}"

    return MetricCardRecord(
        key=key,
        label=label,
        baseline_value=baseline,
        optimized_value=optimized,
        display_value=display_value,
        display_delta=_formatted_delta(
            baseline,
            optimized,
            unit,
            decimals,
        ),
        unit=unit,
        help_text=help_text,
    )


def build_metric_card_records(
    comparison: ScheduleComparison,
) -> tuple[MetricCardRecord, ...]:
    """Format the central baseline/optimized evidence for UI metric cards."""

    baseline = comparison.baseline_metrics
    optimized = comparison.optimized_metrics

    return (
        MetricCardRecord(
            key="heat_load_reduction",
            label="Heat Load reduction",
            baseline_value=baseline.total_heat_load,
            optimized_value=optimized.total_heat_load,
            display_value=f"{comparison.heat_load_reduction_percent:.1f}%",
            display_delta=(
                f"{optimized.total_heat_load - baseline.total_heat_load:+.2f} Heat Load"
            ),
            unit="%",
            help_text="Relative change from the operations-first baseline.",
        ),
        _metric_card(
            key="heat_load",
            label="Operational Heat Load",
            baseline=baseline.total_heat_load,
            optimized=optimized.total_heat_load,
            unit="",
            decimals=2,
            help_text="Operational planning score; not a medical risk assessment.",
        ),
        _metric_card(
            key="peak_temperature",
            label="Peak scheduled temperature",
            baseline=baseline.peak_temperature_c,
            optimized=optimized.peak_temperature_c,
            unit="C",
            decimals=2,
            help_text="Highest modeled temperature encountered by a scheduled job.",
        ),
        _metric_card(
            key="minutes_above_threshold",
            label="Minutes above threshold",
            baseline=baseline.minutes_above_threshold,
            optimized=optimized.minutes_above_threshold,
            unit="min",
            decimals=0,
            help_text="Scheduled minutes above the configured heat threshold.",
        ),
        _metric_card(
            key="priority_weighted_delay",
            label="Priority-weighted delay",
            baseline=baseline.priority_weighted_delay_hours,
            optimized=optimized.priority_weighted_delay_hours,
            unit="h",
            decimals=2,
            help_text="Delay hours weighted by each job's operational priority.",
        ),
        _metric_card(
            key="idle_time",
            label="Crew idle time",
            baseline=baseline.idle_minutes,
            optimized=optimized.idle_minutes,
            unit="min",
            decimals=0,
            help_text="Unscheduled gaps between consecutive crew assignments.",
        ),
    )


def build_job_change_records(
    comparison: ScheduleComparison,
    jobs: list[Job],
) -> tuple[JobChangeRecord, ...]:
    """Format deterministic per-job explanations without changing their meaning."""

    jobs_by_id = _jobs_by_id(jobs)
    records = []

    for change in sorted(comparison.job_changes, key=lambda item: item.job_id):
        job = _job_for(change.job_id, jobs_by_id)
        records.append(
            JobChangeRecord(
                job_id=job.id,
                job_name=job.name,
                baseline_start=minutes_to_time(change.baseline_start_minute),
                optimized_start=minutes_to_time(change.optimized_start_minute),
                start_change=f"{change.start_delta_minutes:+d} min",
                temperature_change=f"{change.temperature_delta_c:+.2f} C",
                heat_load_change=f"{change.heat_load_delta:+.2f}",
                moved=change.moved,
                explanation=change.explanation,
            )
        )

    return tuple(records)


def _ordered_modes(comparisons: Mapping[str, ScheduleComparison]) -> list[str]:
    known = [mode for mode in MODE_ORDER if mode in comparisons]
    unknown = sorted(set(comparisons) - set(MODE_ORDER))
    return [*known, *unknown]


def build_tradeoff_records(
    comparisons: Mapping[str, ScheduleComparison],
    weights_by_mode: Mapping[str, OptimizationWeights] = PRESETS,
) -> tuple[TradeoffRecord, ...]:
    """Convert already-computed mode comparisons into tradeoff-chart records."""

    records = []

    for mode in _ordered_modes(comparisons):
        try:
            weights = weights_by_mode[mode]
        except KeyError as error:
            raise ValueError(
                f"Optimization weights are missing for mode {mode!r}."
            ) from error

        heat_weight, delay_weight = weights.normalized()
        comparison = comparisons[mode]
        metrics = comparison.optimized_metrics
        records.append(
            TradeoffRecord(
                mode=mode,
                mode_label=MODE_LABELS.get(mode, mode.replace("_", " ").title()),
                heat_weight_percent=heat_weight * 100,
                delay_weight_percent=delay_weight * 100,
                total_heat_load=metrics.total_heat_load,
                total_delay_hours=metrics.total_delay_hours,
                priority_weighted_delay_hours=metrics.priority_weighted_delay_hours,
                moved_jobs=comparison.moved_jobs,
            )
        )

    return tuple(records)


def empty_schedule_metrics() -> ScheduleMetrics:
    """Return a safe all-zero metric set for empty presentation states."""

    return ScheduleMetrics(
        total_heat_load=0.0,
        peak_temperature_c=None,
        minutes_above_threshold=0,
        total_delay_hours=0.0,
        priority_weighted_delay_hours=0.0,
        idle_minutes=0,
        scheduled_jobs=0,
    )
