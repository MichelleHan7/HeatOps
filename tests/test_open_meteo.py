from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
import requests

from heatops.benchmark.scenario_generator import generate_scenario
from heatops.integrations.open_meteo import OpenMeteoProvider
from heatops.integrations.weather_provider import StaticProvider, fetch_with_fallback


class Session:
    def __init__(self):
        self.calls = 0
        self.fail = False
        self.missing = False

    def get(self, url, params, timeout):
        self.calls += 1
        if self.fail:
            raise requests.Timeout("test")
        start = datetime(2026, 7, 1, tzinfo=UTC)
        raw = {
            "hourly_units": {"temperature_2m": "°C"},
            "hourly": {
                "time": [
                    int((start + timedelta(hours=h)).timestamp()) for h in range(72)
                ],
                "temperature_2m": [30 + h / 100 for h in range(72)],
            },
        }
        if self.missing:
            raw["hourly"]["temperature_2m"][38] = None

        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return raw

        return Response()


def test_timezone_timestamps_and_cache():
    s = generate_scenario(1, 1)
    session = Session()
    clock = [0]
    p = OpenMeteoProvider(session=session, clock=lambda: clock[0], ttl_seconds=10)
    r = p.fetch(s.jobs, "2026-07-02", "America/Phoenix")
    assert r.matrix["J000"]["temperatures"]["07:00"] == pytest.approx(30.38)
    assert r.metadata["kind"] == "reanalysis"
    assert r.metadata["source_records"]["J000"]["records"][0][
        "timestamp_local"
    ].endswith("-07:00")
    assert p.fetch(s.jobs, "2026-07-02", "America/Phoenix").metadata["cache"]
    assert session.calls == 1
    clock[0] = 11
    p.fetch(s.jobs, "2026-07-02", "America/Phoenix")
    assert session.calls == 2


def test_timeout_missing_intervals_and_explicit_fallback():
    s = generate_scenario(1, 1)
    session = Session()
    session.fail = True
    provider = OpenMeteoProvider(session=session)
    fallback = StaticProvider(s.temperature_matrix, s.metadata)
    result = fetch_with_fallback(
        provider, s.jobs, "2026-07-02", "America/Phoenix", fallback=fallback
    )
    assert result.metadata["source"] == "synthetic"
    assert result.metadata["fallback_reason"]
    with pytest.raises(RuntimeError):
        provider.fetch(s.jobs, "2026-07-02")
    session.fail, session.missing = False, True
    with pytest.raises(RuntimeError):
        provider.fetch(s.jobs, "2026-07-02")


def test_invalid_coordinate_rejected():
    with pytest.raises(ValueError):
        replace(generate_scenario(1, 1).jobs[0], latitude=91)


def test_forecast_classification_and_http_failure(monkeypatch):
    import heatops.integrations.open_meteo as module

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 2, tzinfo=UTC)

    monkeypatch.setattr(module, "datetime", FixedDatetime)
    s = generate_scenario(1, 1)
    assert (
        OpenMeteoProvider(session=Session())
        .fetch(s.jobs, "2026-07-02")
        .metadata["kind"]
        == "forecast_model"
    )

    class BrokenSession:
        def get(self, *args, **kwargs):
            class Response:
                def raise_for_status(self):
                    raise requests.HTTPError("429 rate limited")

            return Response()

    with pytest.raises(RuntimeError):
        OpenMeteoProvider(session=BrokenSession()).fetch(s.jobs, "2026-07-02")


def test_dst_repeated_hour_is_rejected():
    class DSTSession:
        def get(self, *args, **kwargs):
            start = datetime(2026, 11, 1, tzinfo=UTC)

            class Response:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {
                        "hourly_units": {"temperature_2m": "°C"},
                        "hourly": {
                            "time": [
                                int((start + timedelta(hours=h)).timestamp())
                                for h in range(48)
                            ],
                            "temperature_2m": [30] * 48,
                        },
                    }

            return Response()

    with pytest.raises(RuntimeError):
        OpenMeteoProvider(session=DSTSession()).fetch(
            generate_scenario(1, 1).jobs, "2026-11-01", "America/New_York"
        )
