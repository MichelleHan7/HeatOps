from dataclasses import dataclass
from typing import TypedDict


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


@dataclass(frozen=True)
class OptimizationWeights:
    heat: float = 1.0
    delay: float = 0.15
    travel: float = 0.0
    overtime: float = 10.0


@dataclass(frozen=True)
class ScheduleAssignment:
    job_id: str
    worker_id: str
    start_minute: int
    end_minute: int
    temperature_c: float
    heat_load: float

class TemperatureRecord(TypedDict):
    name: str
    temperatures: dict[str, float]


TemperatureMatrix = dict[str, TemperatureRecord]