from dataclasses import dataclass
from math import isfinite

from heatops.domain.time_utils import time_to_minutes


@dataclass(frozen=True)
class SchedulerConfig:
    """Operational configuration shared by all scheduling modes."""

    slot_minutes: int = 15
    heat_threshold_c: float = 32.0
    solver_time_limit_seconds: float = 10.0
    objective_scale: int = 10_000
    default_shift_start: str = "08:00"
    default_shift_end: str = "19:00"
    default_worker_id: str = "CREW-001"
    random_seed: int = 0

    def __post_init__(self) -> None:
        if (
            isinstance(self.slot_minutes, bool)
            or not isinstance(self.slot_minutes, int)
            or self.slot_minutes <= 0
        ):
            raise ValueError("slot_minutes must be a positive integer.")

        if not isfinite(self.heat_threshold_c):
            raise ValueError("heat_threshold_c must be finite.")

        if (
            not isfinite(self.solver_time_limit_seconds)
            or self.solver_time_limit_seconds <= 0
        ):
            raise ValueError("solver_time_limit_seconds must be positive.")

        if (
            isinstance(self.objective_scale, bool)
            or not isinstance(self.objective_scale, int)
            or self.objective_scale <= 0
        ):
            raise ValueError("objective_scale must be a positive integer.")

        if isinstance(self.random_seed, bool) or not isinstance(self.random_seed, int):
            raise TypeError("random_seed must be an integer.")

        if not self.default_worker_id.strip():
            raise ValueError("default_worker_id cannot be empty.")

        if time_to_minutes(self.default_shift_start) >= time_to_minutes(
            self.default_shift_end
        ):
            raise ValueError("default_shift_start must be before default_shift_end.")
