import json
from datetime import UTC, datetime

import pytest

from heatops.domain.models import Job
from heatops.integrations.fortyguard import FortyGuardAPIError
from heatops.integrations.temperature_service import (
    TemperatureDataValidationError,
    TemperatureUnavailableError,
    fetch_temperature_data,
    validate_temperature_matrix,
)

FIXED_TIME = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def _jobs():
    return [
        Job(
            id="JOB-1",
            name="Inspection",
            latitude=33.45,
            longitude=-112.07,
            duration_minutes=60,
            earliest_start="08:00",
            deadline="12:00",
            priority=1,
        )
    ]


def _feature(temperature):
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-112.08, 33.44],
                    [-112.06, 33.44],
                    [-112.06, 33.46],
                    [-112.08, 33.46],
                    [-112.08, 33.44],
                ]
            ],
        },
        "properties": {
            "average_temperature": temperature,
            "tile_id": f"tile-{temperature}",
        },
    }


class FakeLiveClient:
    def __init__(self):
        self.requests = []

    def create_heatmap(self, polygon_aoi, start_date, start_time, granularity):
        self.requests.append((polygon_aoi, start_date, start_time, granularity))
        return f"activity-{start_time}"

    def wait_for_result(self, activity_id, poll_interval, max_attempts):
        temperature = {"activity-08:00": 35.0, "activity-09:00": 36.0}[activity_id]
        return {"map_data": {"features": [_feature(temperature)]}}


class FailingClient:
    def create_heatmap(self, **kwargs):
        raise FortyGuardAPIError("service unavailable")

    def wait_for_result(self, *args, **kwargs):
        raise AssertionError("Polling should not occur after create failure.")


def test_fetch_temperature_data_returns_live_matrix_and_writes_cache(tmp_path):
    client = FakeLiveClient()

    result = fetch_temperature_data(
        _jobs(),
        "2026-08-24",
        ["08:00", "09:00"],
        client=client,
        cache_dir=tmp_path,
        clock=lambda: FIXED_TIME,
        poll_interval=0,
    )

    assert result.matrix["JOB-1"]["temperatures"] == {
        "08:00": 35.0,
        "09:00": 36.0,
    }
    assert result.metadata.source == "live"
    assert result.metadata.data_date == "2026-08-24"
    assert result.metadata.activity_ids == ("activity-08:00", "activity-09:00")
    assert len(client.requests) == 2

    cache_path = tmp_path / "temperature_matrix_2026-08-24_20260829T120000Z.json"
    assert result.metadata.cache_path == str(cache_path)
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert payload["temperature_matrix"] == result.matrix


def test_live_failure_falls_back_to_latest_valid_cache(tmp_path):
    live_result = fetch_temperature_data(
        _jobs(),
        "2026-08-24",
        ["08:00", "09:00"],
        client=FakeLiveClient(),
        cache_dir=tmp_path,
        clock=lambda: FIXED_TIME,
        poll_interval=0,
    )

    cached_result = fetch_temperature_data(
        _jobs(),
        "2026-08-30",
        ["08:00", "09:00"],
        client=FailingClient(),
        cache_dir=tmp_path,
    )

    assert cached_result.matrix == live_result.matrix
    assert cached_result.metadata.source == "cache"
    assert cached_result.metadata.requested_date == "2026-08-30"
    assert cached_result.metadata.data_date == "2026-08-24"
    assert "service unavailable" in cached_result.metadata.fallback_reason


def test_missing_api_key_uses_valid_cache(tmp_path, monkeypatch):
    fetch_temperature_data(
        _jobs(),
        "2026-08-24",
        ["08:00", "09:00"],
        client=FakeLiveClient(),
        cache_dir=tmp_path,
        clock=lambda: FIXED_TIME,
        poll_interval=0,
    )
    monkeypatch.delenv("FORTYGUARD_API_KEY", raising=False)

    cached_result = fetch_temperature_data(
        _jobs(),
        "2026-08-30",
        ["08:00", "09:00"],
        cache_dir=tmp_path,
    )

    assert cached_result.metadata.source == "cache"
    assert "FORTYGUARD_API_KEY" in cached_result.metadata.fallback_reason


def test_live_failure_without_cache_raises_clear_error(tmp_path):
    with pytest.raises(TemperatureUnavailableError, match="no valid cache"):
        fetch_temperature_data(
            _jobs(),
            "2026-08-24",
            ["08:00"],
            client=FailingClient(),
            cache_dir=tmp_path,
        )


def test_cache_fallback_can_be_disabled(tmp_path):
    with pytest.raises(TemperatureUnavailableError, match="Live FortyGuard"):
        fetch_temperature_data(
            _jobs(),
            "2026-08-24",
            ["08:00"],
            client=FailingClient(),
            cache_dir=tmp_path,
            allow_cache_fallback=False,
        )


def test_invalid_live_matrix_falls_back_or_fails_cleanly(tmp_path):
    class NoCoverageClient(FakeLiveClient):
        def wait_for_result(self, activity_id, poll_interval, max_attempts):
            return {"map_data": {"features": []}}

    with pytest.raises(TemperatureUnavailableError, match="No FortyGuard tile"):
        fetch_temperature_data(
            _jobs(),
            "2026-08-24",
            ["08:00"],
            client=NoCoverageClient(),
            cache_dir=tmp_path,
        )


def test_validate_temperature_matrix_rejects_missing_slot():
    matrix = {"JOB-1": {"name": "Inspection", "temperatures": {}}}

    with pytest.raises(TemperatureDataValidationError, match="08:00"):
        validate_temperature_matrix(matrix, _jobs(), ["08:00"])
