from collections.abc import Mapping
from dataclasses import asdict
from math import isfinite
from typing import Any

from shapely.geometry import Point, shape

from heatops.domain.models import Job
from heatops.integrations.aoi import JobLocation


def _job_record(job: JobLocation) -> dict[str, Any]:
    return asdict(job) if isinstance(job, Job) else dict(job)


def match_jobs_to_temperatures(
    jobs: list[JobLocation],
    features: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Match each job location to the FortyGuard tile that covers it."""

    matched_jobs = []

    for job in jobs:
        record = _job_record(job)

        try:
            point = Point(record["longitude"], record["latitude"])
        except KeyError as error:
            raise ValueError(
                "Every job must include latitude and longitude."
            ) from error

        matched_feature = None

        for feature in features:
            try:
                polygon = shape(feature["geometry"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("FortyGuard feature has invalid geometry.") from error

            if polygon.covers(point):
                matched_feature = feature
                break

        if matched_feature is None:
            matched_jobs.append({**record, "temperature": None, "tile_id": None})
            continue

        try:
            properties = matched_feature["properties"]
            temperature = properties["average_temperature"]
            tile_id = properties["tile_id"]
        except (KeyError, TypeError) as error:
            raise ValueError(
                "Matched FortyGuard feature is missing temperature or tile id."
            ) from error

        if (
            isinstance(temperature, bool)
            or not isinstance(temperature, (int, float))
            or not isfinite(temperature)
        ):
            raise ValueError("FortyGuard average_temperature must be finite.")

        matched_jobs.append(
            {
                **record,
                "temperature": float(temperature),
                "tile_id": tile_id,
            }
        )

    return matched_jobs
