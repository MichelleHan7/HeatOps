import pytest

from heatops.domain.models import Job
from heatops.integrations.aoi import build_aoi_from_jobs
from heatops.integrations.temperature_matcher import match_jobs_to_temperatures


def _job() -> Job:
    return Job(
        id="JOB-1",
        name="Inspection",
        latitude=33.45,
        longitude=-112.07,
        duration_minutes=60,
        earliest_start="08:00",
        deadline="12:00",
        priority=1,
    )


def test_build_aoi_accepts_domain_jobs_and_closes_polygon():
    aoi = build_aoi_from_jobs([_job()], padding=0.01)
    coordinates = aoi["features"][0]["geometry"]["coordinates"][0]

    assert coordinates[0] == pytest.approx([-112.08, 33.44])
    assert coordinates[-1] == coordinates[0]
    assert coordinates[2] == pytest.approx([-112.06, 33.46])


def test_build_aoi_rejects_empty_job_list():
    with pytest.raises(ValueError, match="At least one job"):
        build_aoi_from_jobs([])


def test_matcher_supports_domain_jobs_and_polygon_boundary():
    feature = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-112.07, 33.45],
                    [-112.06, 33.45],
                    [-112.06, 33.46],
                    [-112.07, 33.46],
                    [-112.07, 33.45],
                ]
            ],
        },
        "properties": {"average_temperature": 38.25, "tile_id": "tile-1"},
    }

    matched = match_jobs_to_temperatures([_job()], [feature])

    assert matched[0]["id"] == "JOB-1"
    assert matched[0]["temperature"] == 38.25
    assert matched[0]["tile_id"] == "tile-1"


def test_matcher_returns_none_when_no_tile_covers_job():
    assert match_jobs_to_temperatures([_job()], [])[0]["temperature"] is None
