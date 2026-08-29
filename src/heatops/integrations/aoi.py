from collections.abc import Mapping
from math import isfinite
from typing import Any

from heatops.domain.models import Job

JobLocation = Job | Mapping[str, Any]


def _coordinate(job: JobLocation, field: str) -> float:
    value = getattr(job, field) if isinstance(job, Job) else job.get(field)

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Job {field} must be numeric.")

    if not isfinite(value):
        raise ValueError(f"Job {field} must be finite.")

    return float(value)


def build_aoi_from_jobs(
    jobs: list[JobLocation],
    padding: float = 0.005,
) -> dict[str, Any]:
    """Build a rectangular GeoJSON FeatureCollection around job locations."""

    if not jobs:
        raise ValueError("At least one job is required to build an AOI.")

    if not isinstance(padding, (int, float)) or not isfinite(padding):
        raise TypeError("padding must be a finite number.")

    if padding <= 0:
        raise ValueError("padding must be positive.")

    latitudes = [_coordinate(job, "latitude") for job in jobs]
    longitudes = [_coordinate(job, "longitude") for job in jobs]
    min_lat = min(latitudes) - padding
    max_lat = max(latitudes) + padding
    min_lon = min(longitudes) - padding
    max_lon = max(longitudes) + padding
    coordinates = [
        [
            [min_lon, min_lat],
            [max_lon, min_lat],
            [max_lon, max_lat],
            [min_lon, max_lat],
            [min_lon, min_lat],
        ]
    ]

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "Polygon", "coordinates": coordinates},
            }
        ],
    }
