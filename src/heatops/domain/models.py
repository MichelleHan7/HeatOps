from dataclasses import dataclass
from math import isfinite
from typing import TypedDict

from heatops.domain.time_utils import time_to_minutes


@dataclass(frozen=True)
class Job:
    id: str
    name: str
    latitude: float
    longitude: float
    duration_minutes: int
    earliest_start: str
    deadline: str
    priority: int
    required_skill: str | None = None
    physical_intensity: float = 1.0

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Job id cannot be empty.")

        if not self.name.strip():
            raise ValueError("Job name cannot be empty.")

        if not -90 <= self.latitude <= 90:
            raise ValueError(f"Invalid latitude for {self.id}.")

        if not -180 <= self.longitude <= 180:
            raise ValueError(f"Invalid longitude for {self.id}.")

        if (
            isinstance(self.duration_minutes, bool)
            or not isinstance(self.duration_minutes, int)
            or self.duration_minutes <= 0
        ):
            raise ValueError(f"{self.id} must have a positive duration.")

        earliest = time_to_minutes(self.earliest_start)
        deadline = time_to_minutes(self.deadline)

        if earliest >= deadline:
            raise ValueError(f"{self.id} earliest_start must be before its deadline.")

        if (
            isinstance(self.priority, bool)
            or not isinstance(self.priority, int)
            or self.priority <= 0
        ):
            raise ValueError(f"{self.id} priority must be positive.")

        if not isfinite(self.physical_intensity) or self.physical_intensity <= 0:
            raise ValueError(f"{self.id} physical_intensity must be a positive number.")

        if self.required_skill is not None and not self.required_skill.strip():
            raise ValueError(f"{self.id} required_skill cannot be blank.")


@dataclass(frozen=True)
class Worker:
    id: str
    name: str
    start_latitude: float
    start_longitude: float
    shift_start: str
    shift_end: str
    skills: tuple[str, ...]
    acclimatization: float = 1.0

    def __post_init__(self) -> None:
        if isinstance(self.skills, str):
            raise TypeError(f"{self.id} skills must be a collection of strings.")

        object.__setattr__(self, "skills", tuple(self.skills))

        if not self.id.strip():
            raise ValueError("Worker id cannot be empty.")

        if not self.name.strip():
            raise ValueError("Worker name cannot be empty.")

        if not -90 <= self.start_latitude <= 90:
            raise ValueError(f"Invalid latitude for {self.id}.")

        if not -180 <= self.start_longitude <= 180:
            raise ValueError(f"Invalid longitude for {self.id}.")

        if time_to_minutes(self.shift_start) >= time_to_minutes(self.shift_end):
            raise ValueError(f"{self.id} shift_start must be before shift_end.")

        if not isfinite(self.acclimatization) or self.acclimatization <= 0:
            raise ValueError(f"{self.id} acclimatization must be a positive number.")

        if any(not skill.strip() for skill in self.skills):
            raise ValueError(f"{self.id} skills cannot contain blank values.")


@dataclass(frozen=True)
class OptimizationWeights:
    heat: float = 0.5
    delay: float = 0.5

    def __post_init__(self) -> None:
        if not isinstance(self.heat, (int, float)) or not isinstance(
            self.delay, (int, float)
        ):
            raise TypeError("Optimization weights must be numeric.")

        if not isfinite(self.heat) or not isfinite(self.delay):
            raise ValueError("Optimization weights must be finite.")

        if self.heat < 0 or self.delay < 0:
            raise ValueError("Optimization weights cannot be negative.")

        if self.heat == 0 and self.delay == 0:
            raise ValueError("At least one optimization weight must be positive.")

    def normalized(self) -> tuple[float, float]:
        total = self.heat + self.delay
        return self.heat / total, self.delay / total


@dataclass(frozen=True)
class ScheduleAssignment:
    job_id: str
    worker_id: str
    start_minute: int
    end_minute: int
    temperature_c: float
    heat_load: float

    def __post_init__(self) -> None:
        if not isinstance(self.start_minute, int) or not isinstance(
            self.end_minute, int
        ):
            raise TypeError("Schedule assignment times must be integers.")

        if self.end_minute <= self.start_minute:
            raise ValueError("Schedule assignments must have positive duration.")

        if not isfinite(self.temperature_c):
            raise ValueError("Scheduled temperature must be finite.")

        if not isfinite(self.heat_load) or self.heat_load < 0:
            raise ValueError("Heat load must be a nonnegative finite number.")


@dataclass(frozen=True)
class OptimizationResult:
    assignments: tuple[ScheduleAssignment, ...]
    status: str
    objective_value: float
    total_heat_load: float
    total_delay_hours: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "assignments", tuple(self.assignments))

        if not self.status:
            raise ValueError("Optimization status cannot be empty.")

        for value, name in (
            (self.objective_value, "objective_value"),
            (self.total_heat_load, "total_heat_load"),
            (self.total_delay_hours, "total_delay_hours"),
        ):
            if not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a nonnegative finite number.")

    def __iter__(self):
        """Preserve iteration compatibility with the original schedule API."""

        return iter(self.assignments)

    def __len__(self) -> int:
        return len(self.assignments)

    def __getitem__(self, index):
        return self.assignments[index]


class TemperatureRecord(TypedDict):
    name: str
    temperatures: dict[str, float]


TemperatureMatrix = dict[str, TemperatureRecord]
