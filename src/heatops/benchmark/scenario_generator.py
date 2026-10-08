"""Seeded synthetic fixtures with a constructive feasibility witness."""

import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path

from heatops.domain.models import Job, ScheduleAssignment, Worker
from heatops.domain.time_utils import minutes_to_time as label
from heatops.optimization.heat_risk import calculate_heat_load

FAMILIES = ("mild", "hot", "variable", "flat", "spatial")


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


def generate_scenario(n_jobs=10, n_crews=2, seed=0, family="hot", *, infeasible=False):
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
            33.45 + rng.uniform(-0.015, 0.015),
            -112.07 + rng.uniform(-0.015, 0.015),
            "07:00",
            "19:00",
            ("general", "electrical" if i % 2 == 0 else "water"),
        )
        for i in range(n_crews)
    ]
    loads = [0] * n_crews
    jobs, witness_starts = [], []
    for i in range(n_jobs):
        wi = i % n_crews
        duration = rng.choice((15, 30, 45, 60))
        start = 420 + loads[wi]
        loads[wi] += duration
        if start + duration > 1140:
            raise ValueError(
                "Workload cannot fit the constructive 12-hour shifts; add crews"
            )
        earliest = max(420, start - rng.randrange(0, 9) * 15)
        deadline = min(1140, start + duration + rng.randrange(1, 17) * 15)
        jobs.append(
            Job(
                f"J{i:03d}",
                f"Maintenance {i + 1}",
                33.45 + rng.uniform(-0.035, 0.035),
                -112.07 + rng.uniform(-0.035, 0.035),
                duration,
                label(earliest),
                label(deadline),
                rng.randint(1, 3),
                rng.choice(workers[wi].skills),
                round(rng.uniform(0.8, 2), 3),
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
    mean += rng.uniform(-1, 1)
    phase = rng.uniform(13.5, 15.5)
    matrix = {}
    for job in jobs:
        spatial = (job.latitude - 33.45) * 50 if family == "spatial" else 0
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
            "shift_minutes": 720,
        },
        witness,
    )
