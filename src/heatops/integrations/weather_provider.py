"""Uniform provenance-bearing weather interface for v2 consumers."""

from dataclasses import dataclass, replace
from typing import Protocol

from heatops.domain.models import Job, TemperatureMatrix
from heatops.integrations.temperature_service import fetch_temperature_data


@dataclass(frozen=True)
class WeatherData:
    matrix: TemperatureMatrix
    metadata: dict


class WeatherProvider(Protocol):
    def fetch(
        self, jobs: list[Job], requested_date: str, timezone: str
    ) -> WeatherData: ...


@dataclass
class StaticProvider:
    matrix: TemperatureMatrix
    metadata: dict

    def fetch(self, jobs, requested_date, timezone):
        if not self.metadata.get("source"):
            raise ValueError("Static temperature data requires provenance")
        if any(j.id not in self.matrix for j in jobs):
            raise ValueError("Static data does not cover requested jobs")
        return WeatherData(self.matrix, dict(self.metadata))


@dataclass
class FortyGuardProvider:
    client: object = None

    def fetch(self, jobs, requested_date, timezone):
        from dataclasses import asdict

        result = fetch_temperature_data(
            jobs,
            requested_date,
            [f"{h:02d}:00" for h in range(7, 20)],
            client=self.client,
            allow_cache_fallback=False,
        )
        return WeatherData(
            result.matrix,
            {
                **asdict(result.metadata),
                "provider": "FortyGuard",
                "source": "fortyguard_api",
                "timezone": timezone,
                "kind": "provider_temperature_product",
            },
        )


def fetch_with_fallback(provider, jobs, requested_date, timezone, *, fallback=None):
    try:
        return provider.fetch(jobs, requested_date, timezone)
    except (RuntimeError, ValueError, OSError):
        if fallback is None:
            raise
        result = fallback.fetch(jobs, requested_date, timezone)
        # Do not expose provider exception text, URLs or credentials in UI metadata.
        return replace(
            result,
            metadata={
                **result.metadata,
                "fallback_reason": "Requested provider unavailable",
                "requested_date": requested_date,
            },
        )
