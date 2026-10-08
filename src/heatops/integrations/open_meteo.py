"""Open-Meteo hourly 2m temperature, with explicit model provenance.

Official APIs: https://open-meteo.com/en/docs and /en/docs/historical-weather-api.
Historical output is reanalysis, NOT station observations or FortyGuard data.
"""

from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from math import isfinite
from time import monotonic
from zoneinfo import ZoneInfo

import requests

from heatops.integrations.weather_provider import WeatherData


class OpenMeteoProvider:
    def __init__(self, *, session=None, timeout=15, ttl_seconds=3600, clock=monotonic):
        if timeout <= 0 or ttl_seconds < 0:
            raise ValueError("Invalid HTTP timeout or cache TTL")
        self.session = session or requests.Session()
        self.timeout, self.ttl, self.clock = timeout, ttl_seconds, clock
        self.cache = {}

    def fetch(self, jobs, requested_date, timezone="America/Phoenix"):
        day, zone = date.fromisoformat(requested_date), ZoneInfo(timezone)
        if not jobs:
            return WeatherData(
                {}, {"source": "open_meteo", "data_date": requested_date}
            )
        if len(jobs) > 25:
            raise ValueError(
                "At most 25 locations per weather request; use offline data for larger workloads"
            )
        historical = day < datetime.now(UTC).date() - timedelta(days=5)
        endpoint = (
            "https://archive-api.open-meteo.com/v1/archive"
            if historical
            else "https://api.open-meteo.com/v1/forecast"
        )
        kind = "reanalysis" if historical else "forecast_model"
        matrix, source_records = {}, {}
        all_cached = True
        for job in jobs:
            key = (endpoint, job.latitude, job.longitude, requested_date, timezone)
            cached = self.cache.get(key)
            if cached and self.clock() - cached[0] < self.ttl:
                values, provenance = deepcopy(cached[1]), deepcopy(cached[2])
            else:
                all_cached = False
                params = {
                    "latitude": job.latitude,
                    "longitude": job.longitude,
                    "hourly": "temperature_2m",
                    "temperature_unit": "celsius",
                    "timeformat": "unixtime",
                    "timezone": "UTC",
                    "start_date": (day - timedelta(days=1)).isoformat(),
                    "end_date": (day + timedelta(days=1)).isoformat(),
                }
                try:
                    response = self.session.get(
                        endpoint, params=params, timeout=self.timeout
                    )
                    response.raise_for_status()
                    raw = response.json()
                    times, temps = (
                        raw["hourly"]["time"],
                        raw["hourly"]["temperature_2m"],
                    )
                    if (
                        len(times) != len(temps)
                        or raw.get("hourly_units", {}).get("temperature_2m") != "°C"
                    ):
                        raise ValueError("Invalid hourly weather response")
                    values, records = {}, []
                    for timestamp, temperature in zip(times, temps, strict=True):
                        local = datetime.fromtimestamp(timestamp, UTC).astimezone(zone)
                        if local.date() == day or (
                            local.date() == day + timedelta(days=1) and local.hour == 0
                        ):
                            label = (
                                local.strftime("%H:%M")
                                if local.date() == day
                                else "24:00"
                            )
                            if label in values:
                                raise ValueError(
                                    "Repeated DST hour cannot be represented by a single-day matrix"
                                )
                            if (
                                isinstance(temperature, bool)
                                or not isinstance(temperature, (int, float))
                                or not isfinite(temperature)
                            ):
                                raise ValueError(
                                    "Missing/nonfinite weather temperature"
                                )
                            values[label] = temperature
                            records.append(
                                {
                                    "timestamp_utc": datetime.fromtimestamp(
                                        timestamp, UTC
                                    ).isoformat(),
                                    "timestamp_local": local.isoformat(),
                                    "temperature_c": temperature,
                                }
                            )
                    # Require all hours needed by this job; do not fill missing weather.
                    from heatops.domain.time_utils import time_to_minutes

                    first, last = (
                        time_to_minutes(job.earliest_start),
                        time_to_minutes(job.deadline),
                    )
                    required = {
                        f"{h:02d}:00" for h in range(first // 60, (last + 59) // 60 + 1)
                    }
                    if not required.issubset(values):
                        raise ValueError(
                            "Weather response lacks requested hourly coverage"
                        )
                    provenance = {
                        "retrieved_at_utc": datetime.now(UTC).isoformat(),
                        "records": records,
                        "grid_latitude": raw.get("latitude"),
                        "grid_longitude": raw.get("longitude"),
                    }
                except (
                    requests.RequestException,
                    KeyError,
                    TypeError,
                    ValueError,
                    OverflowError,
                ) as exc:
                    raise RuntimeError(
                        "Open-Meteo response unavailable or invalid; use snapshot/synthetic mode"
                    ) from exc
                self.cache[key] = (self.clock(), deepcopy(values), deepcopy(provenance))
            # A cache entry may have been populated by a shorter-window job.
            from heatops.domain.time_utils import time_to_minutes

            required = {
                f"{h:02d}:00"
                for h in range(
                    time_to_minutes(job.earliest_start) // 60,
                    (time_to_minutes(job.deadline) + 59) // 60 + 1,
                )
            }
            if not required.issubset(values):
                raise ValueError("Cached weather lacks required hours")
            matrix[job.id] = {"name": job.name, "temperatures": values}
            source_records[job.id] = provenance
        return WeatherData(
            matrix,
            {
                "provider": "Open-Meteo",
                "source": "open_meteo",
                "kind": kind,
                "data_date": requested_date,
                "timezone": timezone,
                "cache": all_cached,
                "endpoint": endpoint,
                "source_records": source_records,
                "attribution": "Weather data by Open-Meteo.com (CC BY 4.0); model data, not direct observations",
                "interpolation": "Hourly values are interpolated by HeatOps for scheduling",
            },
        )
