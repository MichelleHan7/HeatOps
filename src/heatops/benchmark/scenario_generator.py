"""Seeded synthetic fixtures with a constructive feasibility witness."""

import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path

from heatops.domain.models import Job, ScheduleAssignment, Worker
from heatops.domain.time_utils import minutes_to_time as label
from heatops.domain.time_utils import time_to_minutes
from heatops.optimization.heat_risk import calculate_heat_load

FAMILIES = ("mild", "hot", "variable", "flat", "spatial")


@dataclass(frozen=True)
class GeneratorSettings:
    """Optional controls; defaults preserve registered generator-v1 workloads."""

    shift_start: str = "07:00"
    shift_end: str = "19:00"
    duration_choices: tuple[int, ...] = (15, 30, 45, 60)
    max_priority: int = 3
    intensity_min: float = 0.8
    intensity_max: float = 2.0
    center_latitude: float = 33.45
    center_longitude: float = -112.07
    location_spread_degrees: float = 0.035
    early_slack_slots: int = 8
    late_slack_slots: int = 16
    skills: tuple[str, ...] = ("general", "electrical", "water")
    temperature_mean_c: float | None = None
    temperature_amplitude_c: float | None = None

    def __post_init__(self):
        start, end = time_to_minutes(self.shift_start), time_to_minutes(self.shift_end)
        if start >= end or start % 15 or end % 15:
            raise ValueError("Generator shifts must align to 15-minute slots")
        if not self.duration_choices or any(
            not isinstance(x, int) or x <= 0 or x % 15 for x in self.duration_choices
        ):
            raise ValueError("Durations must be positive multiples of 15 minutes")
        if (
            self.max_priority < 1
            or self.early_slack_slots < 0
            or self.late_slack_slots < 1
        ):
            raise ValueError("Invalid priority or window slack")
        if not 0 < self.intensity_min <= self.intensity_max or not math.isfinite(
            self.intensity_max
        ):
            raise ValueError("Invalid intensity range")
        if not 0 <= self.location_spread_degrees <= 1:
            raise ValueError("Location spread must be between 0 and 1 degree")
        if len(self.skills) < 2 or any(not x.strip() for x in self.skills):
            raise ValueError("Provide a general skill and at least one specialty")
        for value in (self.temperature_mean_c, self.temperature_amplitude_c):
            if value is not None and not math.isfinite(value):
                raise ValueError("Temperature controls must be finite")
        if (
            self.temperature_amplitude_c is not None
            and self.temperature_amplitude_c < 0
        ):
            raise ValueError("Temperature amplitude must be nonnegative")


@dataclass
class Scenario:
    jobs: list[Job]
    workers: list[Worker]
    temperature_matrix: dict
    metadata: dict
    witness: tuple[ScheduleAssignment, ...] = ()

    def to_dict(self):
        return asdict(self)

    def save(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n")


def scenario_from_dict(payload):
    from heatops.benchmark.scenario_validation import validate_scenario

    scenario = Scenario(
        jobs=[Job(**j) for j in payload["jobs"]],
        workers=[Worker(**w) for w in payload["workers"]],
        temperature_matrix=payload["temperature_matrix"],
        metadata=payload.get("metadata", {"source": "user_supplied_unverified"}),
        witness=tuple(ScheduleAssignment(**a) for a in payload.get("witness", [])),
    )
    validate_scenario(scenario)
    return scenario


def generate_scenario(
    n_jobs=10, n_crews=2, seed=0, family="hot", *, infeasible=False, settings=None
):
    custom_settings = settings is not None
    settings = settings or GeneratorSettings()
    shift_start, shift_end = (
        time_to_minutes(settings.shift_start),
        time_to_minutes(settings.shift_end),
    )
    if (
        not isinstance(n_jobs, int)
        or not isinstance(n_crews, int)
        or not 1 <= n_jobs <= 100
        or not 1 <= n_crews <= 10
    ):
        raise ValueError("Use 1–100 jobs and 1–10 crews")
    if family not in FAMILIES:
        raise ValueError("Unknown temperature family")
    rng = random.Random(seed)
    # Broadly distributed jobs, not optimized for a heat-reduction outcome.
    workers = [
        Worker(
            f"W{i:02d}",
            f"Crew {i + 1}",
            settings.center_latitude + rng.uniform(-0.015, 0.015),
            settings.center_longitude + rng.uniform(-0.015, 0.015),
            settings.shift_start,
            settings.shift_end,
            (settings.skills[0], settings.skills[1 + i % (len(settings.skills) - 1)]),
        )
        for i in range(n_crews)
    ]
    loads = [0] * n_crews
    jobs, witness_starts = [], []
    for i in range(n_jobs):
        wi = i % n_crews
        duration = rng.choice(settings.duration_choices)
        start = shift_start + loads[wi]
        loads[wi] += duration
        if start + duration > shift_end:
            raise ValueError("Workload cannot fit the constructive shifts; add crews")
        earliest = max(
            shift_start, start - rng.randrange(0, settings.early_slack_slots + 1) * 15
        )
        deadline = min(
            shift_end,
            start + duration + rng.randrange(1, settings.late_slack_slots + 1) * 15,
        )
        jobs.append(
            Job(
                f"J{i:03d}",
                f"Maintenance {i + 1}",
                settings.center_latitude
                + rng.uniform(
                    -settings.location_spread_degrees, settings.location_spread_degrees
                ),
                settings.center_longitude
                + rng.uniform(
                    -settings.location_spread_degrees, settings.location_spread_degrees
                ),
                duration,
                label(earliest),
                label(deadline),
                rng.randint(1, settings.max_priority),
                rng.choice(workers[wi].skills),
                round(rng.uniform(settings.intensity_min, settings.intensity_max), 3),
            )
        )
        witness_starts.append((workers[wi], start))
    # Each seed receives a common daily weather realization and spatial effects.
    parameters = {
        "mild": (24, 3),
        "hot": (35, 5),
        "variable": (31, 9),
        "flat": (36, 0.5),
        "spatial": (34, 5),
    }
    mean, amplitude = parameters[family]
    if settings.temperature_mean_c is not None:
        mean = settings.temperature_mean_c
    if settings.temperature_amplitude_c is not None:
        amplitude = settings.temperature_amplitude_c
    mean += rng.uniform(-1, 1)
    phase = rng.uniform(13.5, 15.5)
    matrix = {}
    for job in jobs:
        spatial = (
            (job.latitude - settings.center_latitude) * 50 if family == "spatial" else 0
        )
        offset = rng.uniform(-0.5, 0.5)
        matrix[job.id] = {
            "name": job.name,
            "temperatures": {
                f"{h:02d}:00": round(
                    mean
                    + spatial
                    + offset
                    + amplitude * math.cos((h - phase) * math.pi / 12),
                    4,
                )
                for h in range(25)
            },
        }
    witness = tuple(
        ScheduleAssignment(
            j.id,
            w.id,
            start,
            start + j.duration_minutes,
            calculate_heat_load(j, start, matrix).average_temperature_c,
            calculate_heat_load(j, start, matrix).heat_load,
        )
        for j, (w, start) in zip(jobs, witness_starts, strict=True)
    )
    if infeasible:
        from dataclasses import replace

        jobs[0] = replace(jobs[0], required_skill="unavailable_specialty")
        witness = ()
    return Scenario(
        jobs,
        workers,
        matrix,
        {
            "source": "synthetic",
            "generator_version": 1,
            "seed": seed,
            "family": family,
            "timezone": "America/Phoenix",
            "date": None,
            "intended_feasible": not infeasible,
            "feasibility_scope": "scheduling_only; travel may make workload infeasible",
            "weather_model": "Seeded sinusoidal daily profile; not observations or forecasts",
            "shift_minutes": shift_end - shift_start,
            **({"generator_settings": asdict(settings)} if custom_settings else {}),
        },
        witness,
    )
