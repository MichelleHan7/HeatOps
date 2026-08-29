from dataclasses import dataclass
from math import isfinite

from heatops.domain.config import SchedulerConfig
from heatops.domain.models import Job, TemperatureMatrix


@dataclass(frozen=True)
class HeatLoadResult:
    """Operational exposure statistics, not a medical risk assessment."""

    heat_load: float
    average_temperature_c: float
    peak_temperature_c: float
    minutes_above_threshold: int


def _validated_temperature(
    job_id: str,
    time_label: str,
    temperature_matrix: TemperatureMatrix,
) -> float:
    try:
        value = temperature_matrix[job_id]["temperatures"][time_label]
    except KeyError as error:
        raise ValueError(
            f"Temperature data is missing for {job_id} at {time_label}."
        ) from error

    if value is None or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"Temperature for {job_id} at {time_label} must be finite.")

    return float(value)


def get_temperature(
    job_id: str,
    minute: int,
    temperature_matrix: TemperatureMatrix,
) -> float:
    """Linearly interpolate a job's temperature between hourly observations."""

    if isinstance(minute, bool) or not isinstance(minute, int) or minute < 0:
        raise ValueError("minute must be a nonnegative integer.")

    hour, minute_in_hour = divmod(minute, 60)
    current_hour = f"{hour:02d}:00"
    current_temperature = _validated_temperature(
        job_id,
        current_hour,
        temperature_matrix,
    )

    if minute_in_hour == 0:
        return current_temperature

    next_hour = f"{hour + 1:02d}:00"
    next_temperature = _validated_temperature(
        job_id,
        next_hour,
        temperature_matrix,
    )
    fraction = minute_in_hour / 60

    return current_temperature + fraction * (next_temperature - current_temperature)


def calculate_heat_load(
    job: Job,
    start_minute: int,
    temperature_matrix: TemperatureMatrix,
    config: SchedulerConfig | None = None,
) -> HeatLoadResult:
    """Calculate HeatOps' operational Heat Load Score for one assignment."""

    if (
        isinstance(start_minute, bool)
        or not isinstance(start_minute, int)
        or start_minute < 0
    ):
        raise ValueError("start_minute must be a nonnegative integer.")

    config = config or SchedulerConfig()
    remaining_minutes = job.duration_minutes
    offset = 0
    total_load = 0.0
    weighted_temperature = 0.0
    peak_temperature = float("-inf")
    minutes_above_threshold = 0

    while remaining_minutes > 0:
        interval_minutes = min(config.slot_minutes, remaining_minutes)
        minute = start_minute + offset
        temperature = get_temperature(job.id, minute, temperature_matrix)
        heat_above_threshold = max(
            temperature - config.heat_threshold_c,
            0.0,
        )

        total_load += (
            heat_above_threshold * interval_minutes / 60 * job.physical_intensity
        )
        weighted_temperature += temperature * interval_minutes
        peak_temperature = max(peak_temperature, temperature)

        if temperature > config.heat_threshold_c:
            minutes_above_threshold += interval_minutes

        offset += interval_minutes
        remaining_minutes -= interval_minutes

    return HeatLoadResult(
        heat_load=total_load,
        average_temperature_c=(weighted_temperature / job.duration_minutes),
        peak_temperature_c=peak_temperature,
        minutes_above_threshold=minutes_above_threshold,
    )
