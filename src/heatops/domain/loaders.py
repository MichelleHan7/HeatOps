import json
from pathlib import Path

from heatops.domain.models import Job, TemperatureMatrix, Worker


def load_jobs(path: str | Path) -> list[Job]:
    path = Path(path)

    with path.open("r", encoding="utf-8") as file:
        raw_jobs = json.load(file)

    return [
        Job(
            id=item["id"],
            name=item["name"],
            latitude=item["latitude"],
            longitude=item["longitude"],
            duration_minutes=item["duration_minutes"],
            earliest_start=item["earliest_start"],
            deadline=item["deadline"],
            priority=item["priority"],
            required_skill=item.get("required_skill"),
            physical_intensity=item.get("physical_intensity", 1.0),
        )
        for item in raw_jobs
    ]


def load_workers(path: str | Path) -> list[Worker]:
    path = Path(path)

    with path.open("r", encoding="utf-8") as file:
        raw_workers = json.load(file)

    return [
        Worker(
            id=item["id"],
            name=item["name"],
            start_latitude=item["start_latitude"],
            start_longitude=item["start_longitude"],
            shift_start=item["shift_start"],
            shift_end=item["shift_end"],
            skills=tuple(item.get("skills", [])),
            acclimatization=item.get("acclimatization", 1.0),
        )
        for item in raw_workers
    ]


def load_temperature_matrix(path: str | Path) -> TemperatureMatrix:
    path = Path(path)

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)
